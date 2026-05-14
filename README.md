# Aria — Proactive Voice Companion

Aria is a voice-first AI companion that **calls elderly users daily**, remembers their life stories across conversations, and surfaces passive wellbeing signals to a family dashboard.

Unlike a chatbot, Aria initiates contact — it calls you, you don't open an app. The interface is a phone call. Nothing else.

> "It was so lovely talking with you today, Margaret. How's Biscuit been doing?"

---

## Tech Stack

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=flat&logo=postgresql&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-336791?style=flat&logo=postgresql&logoColor=white)
![Whisper](https://img.shields.io/badge/Whisper-412991?style=flat&logo=openai&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-000000?style=flat)
![Twilio](https://img.shields.io/badge/Twilio-F22F46?style=flat&logo=twilio&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?style=flat&logo=react&logoColor=black)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=flat&logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?style=flat&logo=grafana&logoColor=white)

| Layer | Tool |
|---|---|
| STT | faster-whisper (`small.en`, int8, runs locally) |
| LLM | Ollama — `llama3.2:3b` for calls, `llama3.1:8b` for background tasks |
| TTS | Kokoro TTS — `af_heart` voice (runs locally) |
| Phone | Twilio outbound calling + webhooks |
| Backend | FastAPI (async Python) |
| Database | PostgreSQL + pgvector |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`, 384-dim) |
| Mood analysis | librosa (energy, pitch, speech rate, pause ratio) + LLM sentiment |
| Dashboard | React + Vite + Tailwind CSS + Recharts |
| Scheduler | APScheduler (`AsyncIOScheduler`, per-user timezone) |
| Alerts | Gmail SMTP email to family |
| Observability | Prometheus + Grafana (auto-provisioned) |
| Tests | pytest + pytest-asyncio (GitHub Actions on every push) |

---

## Project Phases

- [x] **Phase 1** — Call pipeline (Twilio → Whisper → Ollama → Kokoro → loop)
- [x] **Phase 2** — Episodic memory (pgvector embeddings, fact extraction, cosine deduplication)
- [x] **Phase 3** — Mood signals (acoustic features + LLM sentiment fusion, masking detection, escalation)
- [x] **Phase 4** — Family dashboard (React, mood chart, memory log, alert banner, multi-user, auto-poll)
- [x] **Phase 5** — Proactive scheduling (APScheduler, missed-call retry, startup reconciliation)
- [x] **Phase 6** — Observability (Prometheus metrics, Grafana dashboard, ngrok health check)

---

## Architecture

```mermaid
graph TD
    subgraph Triggers["Triggers"]
        SCHED["APScheduler\n(daily cron per user)"]
        MANUAL["trigger_call.py\n(manual / test)"]
    end

    subgraph Backend["FastAPI Backend  :8000"]
        CM["call_manager.py\norchestrator"]
        STT["Whisper STT\nsmall.en · int8"]
        LLM["Ollama LLM\n3b chat · 8b background"]
        TTS["Kokoro TTS\naf_heart · 24 kHz"]
        MEM["memory_service.py\nembed · dedupe · retrieve"]
        MOOD["mood.py\nlibrosa + LLM sentiment"]
        METRICS["metrics.py\nPrometheus counters"]
    end

    subgraph Data["Data"]
        PG[("PostgreSQL + pgvector\nusers · calls · memories")]
        WAV["audio/\nWAV files"]
    end

    subgraph Phone["Phone"]
        TW["Twilio\nProgrammable Voice"]
        USER(("User\nPhone"))
    end

    subgraph Obs["Observability"]
        PROM["Prometheus  :9090"]
        GRAF["Grafana  :3000"]
    end

    DASH["React Dashboard  :5173"]

    SCHED -->|"fires at call_time"| CM
    MANUAL --> CM

    CM -->|"retrieve recent memories"| MEM
    MEM <-->|"read / write"| PG
    CM -->|"generate greeting"| LLM
    LLM -->|"text"| TTS
    TTS -->|"save WAV"| WAV
    CM -->|"calls.create"| TW
    TW <-->|"outbound call"| USER
    TW -->|"recording URL"| STT
    STT -->|"transcript"| LLM
    LLM -->|"response text"| TTS
    WAV -->|"served over HTTP"| TW
    CM -->|"post-call: extract facts"| MEM
    CM -->|"post-call: score mood"| MOOD
    MOOD -->|"write score"| PG
    CM -->|"write call record"| PG
    METRICS -->|"scrape /metrics"| PROM
    PROM --> GRAF
    DASH -->|"REST API polls"| CM
    DASH -->|"reads history"| PG
    MOOD -->|"alert on low score / masking"| GMAIL["Gmail SMTP\nemail alert"]
    CM -->|"[ESCALATE] mid-call"| GMAIL
    GMAIL -->|"email"| FAMILY(("Family"))
```

---

## What Aria Does

### Phase 1 — Call pipeline
Aria places an outbound call via Twilio. A greeting is **pre-generated before dialing** (memories → LLM → TTS) so the webhook can respond in milliseconds and never hit Twilio's 15-second timeout. Each turn: records speech → transcribes with Whisper → generates a response with Ollama → speaks with Kokoro TTS → loops. The LLM uses `[GOODBYE]` and `[ESCALATE]` control tokens to end calls or trigger family alerts.

### Phase 2 — Episodic memory
After every call, the LLM extracts structured facts from the transcript and stores them as 384-dim vector embeddings in PostgreSQL via pgvector. Before inserting, a cosine similarity check deduplicates near-identical facts (distance < 0.1). On the next call, the most semantically relevant memories are injected into Aria's system prompt. Aria opens each call with a follow-up on a recent topic and avoids repeating the previous call's opening question.

### Phase 3 — Mood signals
Two signal sources are fused into a single 0–1 score:
- **Acoustic (40%)** — librosa extracts energy, pitch, speech rate, and pause ratio from per-turn recordings and compares them against the user's 3-call rolling baseline
- **Sentiment (60%)** — the LLM scores emotional state (cheerful / content / neutral / tired / anxious / sad / distressed) and flags masking (saying "fine" when acoustic signals suggest distress)

A `contradiction_flag` is set when the two sources differ by more than 0.4. Calls scoring below 0.35 trigger a family email alert. Mid-call `[ESCALATE]` fires immediately for genuine emergencies (chest pain, falls, confusion about location, self-harm) — not loneliness or everyday sadness.

### Phase 4 — Family dashboard
React + Vite SPA on port 5173. Auto-polls every 60 seconds, pauses when the browser tab is hidden. Features:
- **User selector** — supports multiple users; tracks selection in the URL (`?user=...`)
- **Status card** — last call time (local timezone), duration, turn count, mood label, emotional state
- **Alert banner** — visible when the most recent call was flagged
- **Mood chart** — 7-day Recharts line chart; threshold line at 0.35; red dots below threshold; shows calibrating state for the first 3 calls
- **Memory feed** — scrollable list of extracted facts with timestamps in browser local time

### Phase 5 — Proactive scheduling
APScheduler fires a daily call for each user at their configured time and timezone (`call_time`, `timezone` columns on User). On startup, all users are scheduled and any open calls (ended_at = NULL) are reconciled against the Twilio API. Key behaviours:
- **misfire_grace_time: 600s** — if the event loop was busy at the scheduled time, the job fires up to 10 minutes late
- **Voicemail detection** — `completed` status with duration < 30s and no conversation is treated as missed
- **Retry** — first missed call triggers a one-time retry 30 minutes later; second failure sends a family email alert
- **PATCH /users/{user_id}/call-time** — update call time and timezone, reschedules the job immediately

### Phase 6 — Observability
Prometheus metrics scraped every 15s; Grafana dashboard auto-provisioned on container start (no manual datasource setup needed).

**Metrics exported:**

| Metric | Type | Description |
|---|---|---|
| `aria_stt_latency_seconds` | Histogram | Whisper transcription duration |
| `aria_llm_latency_seconds` | Histogram | Ollama response generation duration |
| `aria_tts_latency_seconds` | Histogram | Kokoro TTS generation duration |
| `aria_turn_latency_seconds` | Histogram | Full STT→LLM→TTS pipeline per turn |
| `aria_calls_total{outcome}` | Counter | Calls by outcome (completed/missed/escalated) |
| `aria_active_calls` | Gauge | Calls currently in progress |
| `aria_mood_score` | Histogram | Distribution of mood scores |
| `aria_escalations_total{reason}` | Counter | Escalations by reason (low_mood/masking/mid_call) |
| `aria_memory_retrieval_latency_seconds` | Histogram | pgvector similarity search duration |
| `aria_memories_retrieved_per_call` | Histogram | Memories injected per call |
| `aria_ngrok_up` | Gauge | 1 if ngrok tunnel is reachable, 0 if not |

Counters are seeded from the database on startup so historical data survives backend restarts.

---

## Project Structure

```
aria-companion/
├── backend/
│   ├── main.py                      # FastAPI entry point, lifespan hooks
│   ├── config.py                    # pydantic-settings (loads ../.env)
│   ├── db/
│   │   └── database.py              # Async SQLAlchemy engine + idempotent migrations
│   ├── models/
│   │   └── user.py                  # User, Call, Memory ORM models
│   ├── routers/
│   │   ├── calls.py                 # Twilio webhooks + call history endpoints
│   │   ├── memory.py                # GET /memory/{user_id}
│   │   ├── mood.py                  # GET /mood/{user_id}/history
│   │   └── users.py                 # GET /users, PATCH /users/{id}/call-time
│   ├── services/
│   │   ├── call_manager.py          # Full call lifecycle orchestration
│   │   ├── llm.py                   # Ollama wrapper + control token parsing
│   │   ├── stt.py                   # Whisper transcription (small.en, int8)
│   │   ├── tts.py                   # Kokoro TTS → WAV
│   │   ├── memory_service.py        # Embedding, storage, deduplication, retrieval
│   │   ├── mood.py                  # Acoustic features + LLM sentiment fusion
│   │   ├── escalation.py            # Gmail SMTP email alerts
│   │   ├── scheduler.py             # APScheduler daily call jobs
│   │   ├── missed_call.py           # Retry logic + two-failure escalation
│   │   ├── health.py                # ngrok tunnel health check (local API)
│   │   └── metrics.py               # Prometheus metric definitions
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_mood.py             # Mood scoring unit tests (11 tests)
│   │   ├── test_llm.py              # LLM parsing unit tests (14 tests)
│   │   └── test_health.py           # ngrok health check tests (5 tests)
│   ├── requirements.txt
│   ├── requirements-dev.txt         # Lightweight test-only dependencies
│   └── pytest.ini
├── frontend/
│   ├── src/
│   │   ├── api.js                   # fetch helpers (fetchUsers, fetchCalls, etc.)
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   └── Dashboard.jsx        # Auto-poll, user selector, URL param state
│   │   └── components/
│   │       ├── Header.jsx           # User selector dropdown + refresh button
│   │       ├── StatusCard.jsx       # Last call summary, mood, missed state
│   │       ├── AlertBanner.jsx      # Flagged call alert
│   │       ├── MoodChart.jsx        # 7-day trend, calibrating state
│   │       └── MemoryFeed.jsx       # Extracted memory facts
│   ├── package.json
│   └── vite.config.js
├── grafana/
│   ├── aria_dashboard.json          # 6-panel Grafana dashboard
│   └── provisioning/
│       ├── datasources/prometheus.yml  # Auto-configures Prometheus datasource
│       └── dashboards/aria.yml         # Auto-loads dashboard on startup
├── scripts/
│   ├── seed_user.py                 # Create a test user
│   └── trigger_call.py             # Manually fire a test call
├── .github/
│   └── workflows/
│       └── tests.yml                # Run backend tests on every push
├── docker-compose.yml               # DB + Prometheus + Grafana services
├── prometheus.yml                   # Scrape config (host.docker.internal:8001)
└── .env.example
```

---

## Running locally vs Docker

There are two ways to run the backend:

### Option A — Everything in Docker (recommended)

The DB, backend, and frontend all run as containers. Use `.env` with `localhost:5433` as the database URL — `docker-compose.yml` automatically overrides it to `db:5432` inside the container, so you don't need to change anything.

```bash
cp .env.example .env          # fill in your keys
docker compose up -d
```

Dashboard: `http://localhost:5173` — Backend: `http://localhost:8000`

### Option B — Backend in venv, DB in Docker

Run the DB in Docker but the backend natively on your Mac (useful for faster iteration without rebuilding the image).

```bash
cp .env.local.example .env.local   # fill in your keys
docker compose up -d db            # start only the DB
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The `DATABASE_URL` in `.env.local.example` already points to `localhost:5433` which is the host-mapped DB port.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.11+
- Node.js 20+
- [Ollama](https://ollama.com/) installed and running locally
- [ngrok](https://ngrok.com/download) with a static domain (free tier works)
- A [Twilio](https://twilio.com) account (free trial credit included)
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) for email alerts

---

## Setup

### 1. Clone and configure

```bash
git clone <repo-url>
cd aria-companion
cp .env.example .env
```

Fill in `.env`:

```env
# Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx        # your Twilio number

# Email alerts (Gmail SMTP)
ALERT_EMAIL_FROM=you@gmail.com
ALERT_EMAIL_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail App Password
ALERT_EMAIL_TO=family@example.com

# Database
DATABASE_URL=postgresql+asyncpg://aria:aria@localhost:5433/aria_db

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b            # background tasks (extraction, sentiment)
OLLAMA_CHAT_MODEL=llama3.2:3b       # real-time call chat

# ngrok — fill in after step 5
BASE_URL=https://your-static-domain.ngrok-free.app
```

### 2. Start infrastructure

```bash
docker compose up db prometheus grafana -d
```

- Prometheus: [http://localhost:9090](http://localhost:9090)
- Grafana: [http://localhost:3000](http://localhost:3000) — admin / aria (Aria Companion dashboard is pre-loaded)

### 3. Pull the LLM models

```bash
ollama pull llama3.2:3b     # real-time chat (~2 GB)
ollama pull llama3.1:8b     # background extraction (~4.7 GB)
```

### 4. Start the backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Wait for:
```
All models loaded — Aria is ready to take calls.
Scheduler started.
```

### 5. Expose via ngrok

```bash
ngrok http --domain=your-static-domain.ngrok-free.app 8001
```

Copy the HTTPS URL into `.env` as `BASE_URL`, then restart uvicorn.

### 6. Start the dashboard

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

### 7. Seed a user and make a call

```bash
# from project root, venv active
python scripts/seed_user.py          # creates Margaret with call_time=09:00 America/New_York
python scripts/trigger_call.py       # fires an immediate test call
```

Your phone rings. Aria speaks.

---

## Scheduling

Each user has a `call_time` (HH:MM) and `timezone` stored in the database. The scheduler fires a daily call at that local time. To update:

```bash
curl -X PATCH http://localhost:8001/users/{user_id}/call-time \
  -H "Content-Type: application/json" \
  -d '{"call_time": "09:30", "timezone": "America/New_York"}'
```

**Missed call handling:**
1. First missed call → retry in 30 minutes
2. Second failure → email alert to family

---

## How the call loop works

```
APScheduler (or trigger_call.py)
    └─► pre-generate greeting (memories → LLM → TTS)  ← before dialing
    └─► Twilio dials user (calls.create in thread pool — never blocks event loop)
            └─► POST /calls/webhook/{user_id}           ← responds instantly
                    └─► <Play> greeting WAV
                    └─► <Record> user speech
                            └─► POST /calls/turn/{user_id}/{call_id}
                                    └─► Whisper STT
                                    └─► Ollama LLM
                                    └─► Kokoro TTS → WAV
                                    └─► <Play> + <Record>  (loops ≤ 12 turns)
                                    └─► [GOODBYE] → <Hangup>
                                    └─► [ESCALATE] → email family immediately
            └─► POST /calls/status/{call_id}
                    └─► BackgroundTask: extract memories + score mood
                    └─► Email alert if mood < 0.35 or masking detected
```

---

## Mood Scoring

Mood is scored after every call with at least 3 turns:

1. **Acoustic features** — librosa analyses the combined call recording: energy, pitch mean/std, speech rate, pause ratio
2. **LLM sentiment** — Ollama scores emotional state and detects masking (claiming to be fine while acoustic signals suggest distress)
3. **Personal baseline** — averaged from the user's last 3 scored calls
4. **Fused score** — `0.4 × acoustic + 0.6 × sentiment`, range 0–1
5. **Contradiction flag** — set when acoustic and sentiment scores diverge by > 0.4

Score interpretation: 0.0 = very distressed, 0.5 = neutral, 1.0 = very positive. Calls below **0.35** are flagged and shown in the dashboard alert banner.

> The first 3 calls are a calibration period. The chart shows progress dots until a baseline is established.

---

## Voice Synthesis (Kokoro TTS)

Aria's voice is generated by [Kokoro](https://github.com/hexgrad/kokoro), an open-source TTS model that runs entirely on local hardware — no cloud API, no latency cost, no per-character billing.

| Setting | Value |
|---|---|
| Voice | `af_heart` — warm American English female |
| Language | American English (`lang_code="a"`) |
| Sample rate | 24,000 Hz (Kokoro native) |
| Output format | 16-bit PCM WAV |
| Speed | 0.88× (slightly slower than default — easier for elderly users) |

**How it fits into the call loop:**

1. Before dialing, the opening greeting is synthesised and saved to disk. The webhook serves the pre-generated WAV instantly — no TTS latency on answer.
2. During each turn, Ollama's response text is passed to `synthesise()` in [services/tts.py](backend/services/tts.py), which runs the pipeline in a thread pool (`asyncio.to_thread`) so it never blocks the event loop.
3. The WAV file is saved to `AUDIO_DIR` with a UUID filename and served as a static file at `{BASE_URL}/audio/{filename}`. Twilio downloads and plays it directly.

The pipeline is loaded once at startup (`@lru_cache`) and reused for every turn. On long responses, Kokoro splits on sentence boundaries before synthesising so audio chunks can be streamed rather than waiting for the full paragraph.

---

## Memory System

- Facts extracted by LLM after every call (people, health, hobbies, events, sentiments)
- Each fact embedded as a 384-dim vector and stored in PostgreSQL with pgvector
- **Deduplication**: new memories with cosine distance < 0.1 to an existing memory are silently skipped
- **Semantic retrieval**: most contextually relevant memories injected into the system prompt per call
- **Recency retrieval**: most recent memories used to generate the opening follow-up question
- Aria avoids repeating the same opening topic from the previous call
- Memories can be soft-deleted (`active = FALSE`) without removing them from the database

---

## Observability

Open Grafana at [http://localhost:3000](http://localhost:3000) (admin / aria). The **Aria Companion** dashboard includes:

- **Pipeline Latency (p50/p95)** — STT, LLM, TTS, and full turn latency over time
- **Call Outcomes (last 7d)** — completed vs missed vs escalated
- **Active Calls** — live gauge (green/yellow/red thresholds)
- **Mood Score Distribution** — histogram of mood scores over 7 days
- **Memory Retrieval Latency (p95)** — pgvector similarity search timing
- **ngrok Tunnel** — UP/DOWN, checked every 60s via the ngrok local management API

---

## Running Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest -v
```

30 unit tests covering mood scoring logic, LLM token parsing, and ngrok health checks. No database or network access required. Tests run automatically on every push via GitHub Actions.

---

## Environment Variables

| Variable | Description |
|---|---|
| `TWILIO_ACCOUNT_SID` | From Twilio console homepage |
| `TWILIO_AUTH_TOKEN` | From Twilio console homepage |
| `TWILIO_PHONE_NUMBER` | Your Twilio number (E.164 format) |
| `ALERT_EMAIL_FROM` | Gmail address to send alerts from |
| `ALERT_EMAIL_PASSWORD` | Gmail App Password (not your login password) |
| `ALERT_EMAIL_TO` | Family member's email for escalation alerts |
| `DATABASE_URL` | asyncpg connection string (port 5433 to avoid local conflicts) |
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Background task model (default: `llama3.1:8b`) |
| `OLLAMA_CHAT_MODEL` | Real-time call model (default: `llama3.2:3b`) |
| `BASE_URL` | Your ngrok HTTPS URL — must be reachable by Twilio |
| `AUDIO_DIR` | Where TTS WAV files are saved (default: `./audio`) |
