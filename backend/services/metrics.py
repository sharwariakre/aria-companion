"""
Prometheus custom metrics for Aria.

Import this module to register all metrics. Services instrument themselves
by importing the relevant metric objects directly.
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Pipeline latency
# ---------------------------------------------------------------------------

STT_LATENCY = Histogram(
    "aria_stt_latency_seconds",
    "Whisper transcription duration",
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
)

LLM_LATENCY = Histogram(
    "aria_llm_latency_seconds",
    "Ollama response generation duration",
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
)

TTS_LATENCY = Histogram(
    "aria_tts_latency_seconds",
    "Kokoro TTS generation duration",
    buckets=[0.2, 0.5, 1.0, 2.0, 3.0],
)

TOTAL_TURN_LATENCY = Histogram(
    "aria_turn_latency_seconds",
    "Full STT→LLM→TTS pipeline duration per turn",
    buckets=[1.0, 2.0, 4.0, 6.0, 10.0, 15.0],
)

# ---------------------------------------------------------------------------
# Call outcomes
# ---------------------------------------------------------------------------

CALLS_TOTAL = Counter(
    "aria_calls_total",
    "Total calls attempted",
    ["outcome"],  # completed, missed, escalated, failed
)

ACTIVE_CALLS = Gauge(
    "aria_active_calls",
    "Number of calls currently in progress",
)

# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

MEMORIES_RETRIEVED = Histogram(
    "aria_memories_retrieved_per_call",
    "Number of memories injected into prompt",
    buckets=[0, 1, 2, 3, 5, 8],
)

MEMORY_RETRIEVAL_LATENCY = Histogram(
    "aria_memory_retrieval_latency_seconds",
    "pgvector similarity search duration",
    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# ---------------------------------------------------------------------------
# Mood
# ---------------------------------------------------------------------------

MOOD_SCORE = Histogram(
    "aria_mood_score",
    "Distribution of mood scores",
    buckets=[0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0],
)

ESCALATIONS_TOTAL = Counter(
    "aria_escalations_total",
    "Total escalation alerts sent",
    ["reason"],  # low_mood, masking, mid_call
)

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

NGROK_UP = Gauge(
    "aria_ngrok_up",
    "1 if ngrok tunnel is reachable, 0 if not",
)
