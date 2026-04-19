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

| Layer | Tool |
|---|---|
| STT | faster-whisper (base.en, runs locally) |
| LLM | Ollama + llama3.2:3b (runs locally) |
| TTS | Kokoro TTS — `af_heart` voice (runs locally) |
| Phone | Twilio outbound calling + webhooks |
| Backend | FastAPI (async Python) |
| Database | PostgreSQL + pgvector |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Mood analysis | librosa (energy, pitch, speech rate, pause ratio) |
| Dashboard | React + Vite + Tailwind CSS + Recharts |
| Scheduler | APScheduler (Phase 5) |

---

## Project Phases

- [x] **Phase 1** — Call pipeline (Twilio → Whisper → Ollama → Kokoro → loop)
- [x] **Phase 2** — Episodic memory (pgvector embeddings, fact extraction, memory injection)
- [x] **Phase 3** — Mood signals (librosa acoustic features, personal baseline, escalation)
- [x] **Phase 4** — Family dashboard (React, mood chart, memory log, alert banner)
- [ ] **Phase 5** — Proactive scheduling (APScheduler, missed-call SMS escalation)

---

## What Aria Does

### Phase 1 — Call pipeline
Aria places an outbound call via Twilio. Each turn: records the user's speech → transcribes with Whisper → generates a response with Ollama → speaks with Kokoro TTS → loops. The LLM uses `[GOODBYE]` and `[ESCALATE]` control tokens to end calls or trigger emergency SMS. A pre-generated greeting is prepared before dialing to beat Twilio's 15-second answer timeout.

### Phase 2 — Episodic memory
After every call, the LLM extracts structured facts (people, places, health, hobbies, sentiments) from the transcript and stores them as vector embeddings in PostgreSQL via pgvector. On the next call, the **8 most recent memories** are injected into the system prompt — giving Aria continuity across conversations. Memories are used as background context; Aria does not re-ask about things it already knows.

### Phase 3 — Mood signals
After every call (minimum 3 turns), librosa extracts four acoustic features from the recorded audio: **energy**, **pitch**, **speech rate**, and **pause ratio**. These are compared against a rolling 3-call personal baseline to produce a normalized mood score (0–1). Scores below 0.35 flag the call for family review. Escalation (`[ESCALATE]`) is reserved for genuine emergencies: chest pain, falls, confusion about location, or expressions of self-harm — not loneliness or sadness.

### Phase 4 — Family dashboard
A React + Vite single-page app served on port 5173. Reads call data from the backend REST API and displays:
- **Status card** — last call time, duration, turn count, mood label (Calm / Low / Distressed)
- **Alert banner** — only visible when the most recent call was flagged
- **Mood chart** — 7-day Recharts line chart with a threshold reference line at 0.35; dots colored red below threshold
- **Memory feed** — chronological list of extracted memory facts with category labels

---

## Project Structure

```
aria-companion/
├── backend/
│   ├── main.py                      # FastAPI entry point + CORS middleware
│   ├── config.py                    # Settings (pydantic-settings, loads ../.env)
│   ├── db/
│   │   └── database.py              # Async SQLAlchemy engine + init_db
│   ├── models/
│   │   └── user.py                  # User, Call, Memory ORM models
│   ├── routers/
│   │   ├── calls.py                 # Twilio webhook handlers + GET /{user_id}
│   │   ├── memory.py                # GET /memories/{user_id}
│   │   └── mood.py                  # GET /mood/{user_id}/history
│   └── services/
│       ├── stt.py                   # Whisper transcription (faster-whisper)
│       ├── llm.py                   # Ollama chat wrapper + control token parsing
│       ├── tts.py                   # Kokoro TTS → WAV → static file
│       ├── call_manager.py          # Orchestrates the full call lifecycle
│       ├── memory_service.py        # Embedding, storage, recency retrieval
│       ├── mood.py                  # librosa feature extraction + baseline scoring
│       └── escalation.py           # SMS escalation via Twilio Messaging
├── frontend/
│   ├── src/
│   │   ├── api.js                   # fetch helpers for calls, mood, memories
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   └── Dashboard.jsx
│   │   └── components/
│   │       ├── Header.jsx
│   │       ├── StatusCard.jsx
│   │       ├── AlertBanner.jsx
│   │       ├── MoodChart.jsx
│   │       └── MemoryFeed.jsx
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   ├── seed_user.py                 # Create test user Margaret
│   └── trigger_call.py             # Manually fire a test call
├── docker-compose.yml               # PostgreSQL + pgvector (port 5433) + frontend
├── .env.example
└── README.md
```

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.11+
- Node.js 20+
- [Ollama](https://ollama.com/) installed and running
- [ngrok](https://ngrok.com/download) for local Twilio webhooks
- A [Twilio](https://twilio.com) account (free trial works — $15 credit included)

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
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx
TWILIO_TO_NUMBER=+1xxxxxxxxxx          # number to call (Margaret's phone)
EMERGENCY_CONTACT_NUMBER=+1xxxxxxxxxx  # family member's number for escalation SMS
OLLAMA_MODEL=llama3.2:3b
DATABASE_URL=postgresql+asyncpg://aria:aria@localhost:5433/aria_db
BASE_URL=https://your-ngrok-url.ngrok-free.app   # fill in after step 4
```

### 2. Start the database

```bash
docker compose up db -d
```

### 3. Pull the LLM

```bash
ollama pull llama3.2:3b   # ~2GB, one-time download
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
```

### 5. Expose via ngrok

```bash
ngrok http 8001
```

Copy the `https://....ngrok-free.app` URL into `.env` as `BASE_URL`, then restart uvicorn.

### 6. Start the dashboard

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

### 7. Seed Margaret and make a call

```bash
# From project root, venv active
MARGARET_PHONE=+1xxxxxxxxxx python scripts/seed_user.py
python scripts/trigger_call.py
```

Your phone rings. Press any key past the Twilio trial message. Aria speaks.

---

## How the call loop works

```
trigger_call.py
    └─► Twilio dials user
            └─► POST /calls/webhook/{user_id}
                    └─► fetch 8 most recent memories
                    └─► LLM generates personalised greeting
                    └─► Kokoro TTS → WAV file
                    └─► TwiML: <Play> + <Record>
                            └─► user speaks
                            └─► POST /calls/turn/{user_id}/{call_id}
                                    └─► download recording
                                    └─► Whisper transcribes
                                    └─► Ollama generates response
                                    └─► Kokoro TTS → WAV
                                    └─► TwiML: <Play> + <Record>  (loops)
                                    └─► [GOODBYE] → <Hangup>
                                    └─► [ESCALATE] → SMS to emergency contact
                    └─► BackgroundTask: extract memories + score mood
```

---

## Mood Scoring

Mood is scored after every call with at least 3 turns:

1. **Feature extraction** — librosa analyses the call recording for energy, pitch mean/std, speech rate, and pause ratio
2. **Personal baseline** — the user's last 3 calls establish their normal range
3. **Normalised score** — each feature is Z-scored against the baseline and mapped to 0–1 (0.5 = neutral, 1.0 = significantly elevated)
4. **Flag threshold** — calls scoring below 0.35 are flagged and shown in the dashboard alert banner

> Mood scoring requires a warm-up period. The first 3 calls default to 0.5 while the baseline is being established.

---

## Memory System

- Facts are extracted from every call transcript by the LLM and stored with vector embeddings
- On each new call, the **8 most recent memories** are injected into Aria's system prompt
- Aria uses memories as background context only — it does not re-ask about things it already knows
- Aria opens each call with a follow-up question about a recent topic, and avoids repeating the same opening topic from the previous call

> Known limitation: the small LLM (llama3.2:3b) occasionally hallucinates facts or creates duplicates. Deduplication and active/archived memory flags are planned for a future phase (see [#10](https://github.com/sharwariakre/aria-companion/issues/10)).

---

## Known Limitations & Open Issues

| Issue | Description |
|---|---|
| [#9](https://github.com/sharwariakre/aria-companion/issues/9) | No proactive scheduling yet — calls must be triggered manually |
| [#10](https://github.com/sharwariakre/aria-companion/issues/10) | Memory deduplication and stale-fact handling not yet implemented |
| [#11](https://github.com/sharwariakre/aria-companion/issues/11) | Mood scores are unreliable for the first 3 calls (baseline warm-up) |
| [#12](https://github.com/sharwariakre/aria-companion/issues/12) | Dashboard requires manual page reload to see new data |
| [#13](https://github.com/sharwariakre/aria-companion/issues/13) | Dashboard and trigger script are hardcoded to Margaret's UUID |
| [#14](https://github.com/sharwariakre/aria-companion/issues/14) | Short utterances ("yes", "no") are sometimes missed by Whisper VAD |

---

## Environment Variables

| Variable | Description |
|---|---|
| `TWILIO_ACCOUNT_SID` | From Twilio console homepage |
| `TWILIO_AUTH_TOKEN` | From Twilio console homepage |
| `TWILIO_PHONE_NUMBER` | Your Twilio number (E.164 format) |
| `TWILIO_TO_NUMBER` | The number Aria calls (Margaret's phone) |
| `EMERGENCY_CONTACT_NUMBER` | Family member's number for escalation SMS |
| `DATABASE_URL` | Postgres connection string (port 5433 to avoid local conflicts) |
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Model name (recommended: `llama3.2:3b`) |
| `BASE_URL` | Your ngrok URL — must be publicly reachable by Twilio |
| `AUDIO_DIR` | Where TTS WAV files are saved (default: `./audio`) |
