"""
Ollama LLM wrapper.

Sends multi-turn messages to the Ollama /api/chat endpoint and returns
the assistant response as a plain string.  Also parses special control
tokens that Aria embeds in its replies:

  [GOODBYE]  — natural end of call
  [ESCALATE] — user mentioned pain, emergency, or extreme distress
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date

import httpx

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Control tokens
# ---------------------------------------------------------------------------

GOODBYE_TOKEN = "[GOODBYE]"
ESCALATE_TOKEN = "[ESCALATE]"

_TOKEN_PATTERN = re.compile(r"\[(GOODBYE|ESCALATE)\]", re.IGNORECASE)


@dataclass
class LLMResponse:
    text: str                       # clean response text (tokens stripped)
    should_end: bool = False
    should_escalate: bool = False
    raw: str = field(default="", repr=False)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """\
You are Aria, a warm and patient voice companion calling {user_name} for their daily check-in.

Your personality:
- Warm, unhurried, and genuinely curious.
- Never interrupt. If there is silence, wait patiently.
- If the user repeats something they already told you, respond with interest, not correction.
- Keep responses very short — 1 to 3 sentences maximum. This is a phone call, not a text chat.
- Never mention that you are an AI unless directly asked.
- Speak naturally. Use their name occasionally but not every turn.

Today is {today}.

If you want to end the call naturally, add the token {goodbye} at the very end of your response.
If the user mentions pain, an emergency, feeling very sad, or confusion about their location or identity: express care calmly, say you will have someone check on them shortly, and add the token {escalate} at the very end of your response.

Do NOT include the tokens mid-sentence — always place them at the absolute end, separated by a space.
"""


def build_system_prompt(user_name: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        user_name=user_name,
        today=date.today().strftime("%A, %B %d %Y"),
        goodbye=GOODBYE_TOKEN,
        escalate=ESCALATE_TOKEN,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def chat(
    messages: list[dict],
    user_name: str,
    temperature: float = 0.7,
) -> LLMResponse:
    """
    Send a conversation history to Ollama and return a structured response.

    `messages` is a list of {"role": "user"/"assistant", "content": str} dicts.
    The system prompt is prepended automatically.
    """
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": build_system_prompt(user_name)},
            *messages,
        ],
        "stream": False,
        "options": {"temperature": temperature},
    }

    try:
        async with httpx.AsyncClient(
            base_url=settings.ollama_base_url, timeout=60.0
        ) as client:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["message"]["content"].strip()
    except Exception as exc:
        logger.error(f"Ollama request failed: {exc}")
        # Graceful fallback so the call doesn't die silently
        return LLMResponse(
            text="I'm sorry, I had a little trouble thinking just then. Could you say that again?",
            raw="",
        )

    return _parse_response(raw_text)


def _parse_response(raw: str) -> LLMResponse:
    tokens_found = {m.group(1).upper() for m in _TOKEN_PATTERN.finditer(raw)}
    clean = _TOKEN_PATTERN.sub("", raw).strip()
    # Also remove any trailing punctuation artifacts left after token removal
    clean = re.sub(r"\s{2,}", " ", clean).strip()

    return LLMResponse(
        text=clean,
        should_end="GOODBYE" in tokens_found,
        should_escalate="ESCALATE" in tokens_found,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Opening greeting helper
# ---------------------------------------------------------------------------

async def generate_opening(user_name: str) -> LLMResponse:
    """Generate the very first line of a call — warm, brief, specific."""
    messages = [
        {
            "role": "user",
            "content": (
                f"Start the call now. Greet {user_name} warmly, mention that it's great to talk "
                "with them today, and ask one gentle open-ended question about how they are feeling."
            ),
        }
    ]
    return await chat(messages, user_name=user_name)
