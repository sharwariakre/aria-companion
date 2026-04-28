"""
Unit tests for LLM response parsing and prompt building.

No network calls — all tests are pure string manipulation.
"""

import pytest
from unittest.mock import AsyncMock, patch

from services.llm import (
    ESCALATE_TOKEN,
    GOODBYE_TOKEN,
    LLMResponse,
    _parse_response,
    build_system_prompt,
)


# ---------------------------------------------------------------------------
# _parse_response — token extraction
# ---------------------------------------------------------------------------

def test_clean_response_no_tokens():
    resp = _parse_response("How are you feeling today?")
    assert resp.text == "How are you feeling today?"
    assert resp.should_end is False
    assert resp.should_escalate is False


def test_goodbye_token_sets_should_end():
    resp = _parse_response("It was lovely talking with you. [GOODBYE]")
    assert resp.should_end is True
    assert resp.should_escalate is False
    assert "GOODBYE" not in resp.text
    assert "[" not in resp.text


def test_escalate_token_sets_should_escalate():
    resp = _parse_response("I'll make sure someone checks on you right away. [ESCALATE]")
    assert resp.should_escalate is True
    assert resp.should_end is False
    assert "ESCALATE" not in resp.text


def test_both_tokens_present():
    resp = _parse_response("Please stay safe. [ESCALATE] [GOODBYE]")
    assert resp.should_end is True
    assert resp.should_escalate is True
    assert resp.text.strip() == "Please stay safe."


def test_token_without_brackets_still_parsed():
    resp = _parse_response("Take care now. GOODBYE")
    assert resp.should_end is True


def test_token_case_insensitive():
    resp = _parse_response("Goodbye for now. [goodbye]")
    assert resp.should_end is True


def test_raw_field_preserved():
    raw = "Talk soon. [GOODBYE]"
    resp = _parse_response(raw)
    assert resp.raw == raw


def test_multiple_spaces_collapsed():
    resp = _parse_response("That's good to hear  [GOODBYE]")
    assert "  " not in resp.text


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------

def test_system_prompt_contains_user_name():
    prompt = build_system_prompt("Margaret")
    assert "Margaret" in prompt


def test_system_prompt_contains_control_tokens():
    prompt = build_system_prompt("Margaret")
    assert GOODBYE_TOKEN in prompt
    assert ESCALATE_TOKEN in prompt


def test_system_prompt_no_memories_section_when_empty():
    prompt = build_system_prompt("Margaret", memories="")
    assert "What you remember" not in prompt


def test_system_prompt_includes_memories_when_provided():
    prompt = build_system_prompt("Margaret", memories="Has a cat named Whiskers.")
    assert "Has a cat named Whiskers." in prompt
    assert "What you remember about Margaret" in prompt


def test_system_prompt_includes_today():
    from datetime import date
    today = date.today().strftime("%A, %B %d %Y")
    prompt = build_system_prompt("Margaret")
    assert today in prompt


# ---------------------------------------------------------------------------
# generate_opening — Ollama-down fallback
# ---------------------------------------------------------------------------

async def test_generate_opening_fallback_when_ollama_down():
    """When Ollama is unreachable, generate_opening must return a clean greeting,
    not the internal error message that would confuse the user."""
    error_resp = LLMResponse(
        text="I'm sorry, I had a little trouble thinking just then. Could you say that again?",
        raw="",
    )
    with patch("services.llm.chat", new=AsyncMock(return_value=error_resp)):
        from services.llm import generate_opening
        resp = await generate_opening("Margaret")

    assert not resp.text.startswith("I'm sorry, I had a little trouble")
    assert "Margaret" in resp.text
    assert "Aria" in resp.text
