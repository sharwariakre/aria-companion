"""
Groq LLM wrapper.

Sends multi-turn messages to the Groq API and returns the assistant
response as a plain string.  Also parses special control tokens that
Aria embeds in its replies:

  [GOODBYE]  — natural end of call
  [ESCALATE] — user mentioned pain, emergency, or extreme distress
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from groq import AsyncGroq

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Control tokens
# ---------------------------------------------------------------------------

GOODBYE_TOKEN = "[GOODBYE]"
ESCALATE_TOKEN = "[ESCALATE]"

_TOKEN_PATTERN = re.compile(r"\[?(GOODBYE|ESCALATE)\]?", re.IGNORECASE)


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
- Never contradict or correct the user. If they say something that conflicts with your memory, gently go along with what they say now.
- Keep responses very short — 1 to 3 sentences maximum. This is a phone call, not a text chat.
- Never mention that you are an AI unless directly asked.
- Speak naturally. Use their name occasionally but not every turn.

{memories_section}
Today is {today}.

Only use {goodbye} when the conversation has reached a natural close and the user has said goodbye or indicated they need to go. Do NOT use {goodbye} if you have just asked a question or the conversation is still active.
Only use {escalate} for genuine emergencies: the user mentions chest pain, a fall, a medical emergency, expresses they want to harm themselves, or is confused about where they are or who they are. Do NOT escalate for ordinary loneliness, missing family, feeling a bit down, or everyday sadness — those are normal and should be met with warmth and empathy, not alarm.

Do NOT include the tokens mid-sentence — always place them at the absolute end, separated by a space.
"""


def build_system_prompt(user_name: str, memories: str = "") -> str:
    if memories:
        memories_section = (
            f"What you remember about {user_name} from past conversations:\n"
            f"{memories}\n\n"
            "Use these as background context to personalise your responses — do NOT treat them as open questions to ask about. "
            "Only bring up a memory if {user_name} raises the topic first, or if it's directly relevant to something they just said. "
            "Never re-ask about something that has already been discussed and answered across calls.\n"
        )
    else:
        memories_section = ""

    return SYSTEM_PROMPT_TEMPLATE.format(
        user_name=user_name,
        memories_section=memories_section,
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
    memories: str = "",
    temperature: float = 0.7,
) -> LLMResponse:
    """
    Send a conversation history to Groq and return a structured response.

    `messages` is a list of {"role": "user"/"assistant", "content": str} dicts.
    The system prompt is prepended automatically.
    """
    try:
        client = AsyncGroq(api_key=settings.groq_api_key)
        completion = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": build_system_prompt(user_name, memories=memories)},
                *messages,
            ],
            temperature=temperature,
            max_tokens=500,
        )
        raw_text = completion.choices[0].message.content.strip()
    except Exception as exc:
        logger.error(f"Groq request failed: {exc}")
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

async def generate_opening(user_name: str, memories: str = "", prev_opening: str = "") -> LLMResponse:
    """Generate the very first line of a call — warm, brief, specific."""
    if memories:
        avoid_clause = (
            f" Do NOT ask about the same topic you opened with last time. "
            f"Last call you started with: \"{prev_opening}\""
            if prev_opening else ""
        )
        opening_instruction = (
            f"Start the call now. Greet {user_name} warmly, then ask a specific follow-up "
            f"question about something they mentioned in a recent conversation — like how an "
            f"outing went, how they're feeling after an event, or how someone they mentioned is doing. "
            f"Pick the most recent and meaningful thing from your memories. Keep it to 2 sentences max."
            f"{avoid_clause}"
        )
    else:
        opening_instruction = (
            f"Start the call now. Greet {user_name} warmly and ask one gentle open-ended "
            f"question about how they are feeling today."
        )

    messages = [{"role": "user", "content": opening_instruction}]
    resp = await chat(messages, user_name=user_name, memories=memories)

    # If Groq was down, the generic error fallback is a bad opening line — replace it
    if resp.text.startswith("I'm sorry, I had a little trouble"):
        resp.text = f"Hello {user_name}, it's Aria! How are you feeling today?"
    return resp
