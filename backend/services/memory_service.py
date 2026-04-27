"""
Episodic memory service — Phase 2.

Two public functions:

  extract_and_store_memories(user_id, call_id, transcript, db)
      Called after every call.  Prompts Ollama to extract key facts from the
      transcript, embeds each fact with sentence-transformers, and stores them
      in the memories table.

  get_relevant_memories(user_id, context, db, top_k=5)
      Called before every call.  Embeds the context string, runs a cosine
      similarity search against the user's memories via pgvector, and returns
      the top-k facts as a formatted bullet string ready for the system prompt.

The sentence-transformer model is loaded lazily on first use and cached.
Use _get_embedder() directly during startup pre-warm.
"""

import asyncio
import logging
import time
import uuid
from functools import lru_cache

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.user import Memory
from services.metrics import MEMORIES_RETRIEVED, MEMORY_RETRIEVAL_LATENCY

logger = logging.getLogger(__name__)
settings = get_settings()

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


# ---------------------------------------------------------------------------
# Embedding model singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_embedder():
    from sentence_transformers import SentenceTransformer

    logger.info(f"Loading sentence-transformer model ({EMBEDDING_MODEL})…")
    model = SentenceTransformer(EMBEDDING_MODEL)
    logger.info("Embedding model ready.")
    return model


def _embed(text_input: str) -> list[float]:
    """Synchronous embedding — call via asyncio.to_thread."""
    model = _get_embedder()
    vec = model.encode(text_input, normalize_embeddings=True)
    return vec.tolist()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract_and_store_memories(
    user_id: uuid.UUID,
    call_id: uuid.UUID,
    transcript: str,
    db: AsyncSession,
) -> int:
    """
    Extract key facts from a call transcript and persist them as embeddings.
    Returns the number of memories stored.
    """
    if not transcript.strip():
        logger.info(f"Empty transcript for call={call_id}, skipping memory extraction.")
        return 0

    facts = await _extract_facts(transcript)
    if not facts:
        logger.info(f"No facts extracted from call={call_id}.")
        return 0

    count = 0
    for fact in facts:
        fact = fact.strip()
        if not fact:
            continue
        embedding = await asyncio.to_thread(_embed, fact)

        # Skip near-duplicates (cosine distance < 0.1 means similarity > 0.9)
        embedding_str = "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"
        dup = await db.execute(
            text("""
                SELECT id FROM memories
                WHERE user_id = :user_id
                  AND active = TRUE
                  AND embedding IS NOT NULL
                  AND (embedding <=> CAST(:embedding AS vector)) < 0.1
                LIMIT 1
            """),
            {"user_id": str(user_id), "embedding": embedding_str},
        )
        if dup.fetchone():
            logger.info(f"Skipping near-duplicate memory: '{fact[:60]}'")
            continue

        db.add(Memory(
            user_id=user_id,
            source_call_id=call_id,
            content=fact,
            embedding=embedding,
        ))
        count += 1

    await db.commit()
    logger.info(f"Stored {count} memories for user={user_id} from call={call_id}.")
    return count


async def get_recent_memories(
    user_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = 8,
) -> str:
    """
    Retrieve the most recently stored memories for a user, ordered by creation
    time. Used for opening greetings so Aria follows up on the last call's
    topics rather than whatever scores highest in cosine similarity.
    """
    result = await db.execute(
        text("""
            SELECT content
            FROM memories
            WHERE user_id = :user_id
              AND active = TRUE
            ORDER BY created_at DESC
            LIMIT :top_k
        """),
        {"user_id": str(user_id), "top_k": top_k},
    )
    rows = result.fetchall()
    if not rows:
        return ""

    formatted = "\n".join(f"- {row[0]}" for row in rows)
    logger.info(f"Retrieved {len(rows)} recent memories for user={user_id}.")
    return formatted


async def get_relevant_memories(
    user_id: uuid.UUID,
    context: str,
    db: AsyncSession,
    top_k: int = 5,
) -> str:
    """
    Retrieve the top-k most relevant memories for the given context string.
    Returns a formatted bullet string, or empty string if no memories exist.
    """
    embedding = await asyncio.to_thread(_embed, context)
    embedding_str = "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"

    t0 = time.perf_counter()
    result = await db.execute(
        text("""
            SELECT content
            FROM memories
            WHERE user_id = :user_id
              AND active = TRUE
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """),
        {
            "user_id": str(user_id),
            "embedding": embedding_str,
            "top_k": top_k,
        },
    )
    MEMORY_RETRIEVAL_LATENCY.observe(time.perf_counter() - t0)
    rows = result.fetchall()
    if not rows:
        return ""

    MEMORIES_RETRIEVED.observe(len(rows))
    formatted = "\n".join(f"- {row[0]}" for row in rows)
    logger.info(f"Retrieved {len(rows)} memories for user={user_id}.")
    return formatted


# ---------------------------------------------------------------------------
# Fact extraction via Ollama
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """\
You are analyzing a phone call transcript to extract key facts about the user \
(the person Aria is calling — not Aria herself).

Extract a concise bullet list of facts. Include:
- Names of family members or friends mentioned
- Names of pets
- Health mentions (symptoms, medications, appointments, pain)
- Recent events or activities the user described
- Hobbies, preferences, or personal interests
- Any upcoming plans or events the user mentioned

Rules:
- One fact per line, starting with "- "
- Be specific and concrete (e.g. "daughter's name is Sarah", not "has a daughter")
- Maximum 10 facts
- If nothing notable was mentioned, return an empty response — do not invent facts

Transcript:
{transcript}

Facts:"""


async def _extract_facts(transcript: str) -> list[str]:
    """Ask Ollama to extract a bullet list of facts from a transcript."""
    prompt = _EXTRACTION_PROMPT.format(transcript=transcript)

    try:
        async with httpx.AsyncClient(
            base_url=settings.ollama_base_url, timeout=90.0
        ) as client:
            resp = await client.post(
                "/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
    except Exception as exc:
        logger.error(f"Fact extraction LLM call failed: {exc}")
        return []

    facts = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("- "):
            facts.append(line[2:].strip())
        elif line.startswith("• "):
            facts.append(line[2:].strip())

    logger.info(f"Extracted {len(facts)} facts: {facts}")
    return facts
