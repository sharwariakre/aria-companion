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
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)

| Layer | Tool |
|---|---|
| STT | faster-whisper (base.en, runs locally) |
| LLM | Ollama + llama3.2:3b (runs locally) |
| TTS | Kokoro TTS — `af_heart` voice (runs locally) |
| Phone | Twilio outbound calling + webhooks |
| Backend | FastAPI (async Python) |
| Database | PostgreSQL + pgvector |
| Scheduler | APScheduler (Phase 5) |
| Dashboard | React + Vite (Phase 4) |

---

## Project Phases

- [x] **Phase 1** — Call pipeline (Twilio → Whisper → Ollama → Kokoro → loop)
- [ ] **Phase 2** — Episodic memory (pgvector, fact extraction, memory injection)
- [ ] **Phase 3** — Mood signals (librosa acoustic features, baseline comparison)
- [ ] **Phase 4** — Family dashboard (React, mood chart, memory log, alerts)
- [ ] **Phase 5** — Proactive scheduling (APScheduler, missed-call SMS escalation)

---

## Project Structure

```
aria/
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── config.py                # Settings (pydantic-settings, loads ../.env)
│   ├── db/
│   │   └── database.py          # Async SQLAlchemy engine + init_db
│   ├── models/
│   │   └── user.py              # User + Call ORM models
│   ├── routers/
│   │   └── calls.py             # Twilio webhook handlers
│   └── services/
│       ├── stt.py               # Whisper transcription (faster-whisper)
│       ├── llm.py               # Ollama chat wrapper + GOODBYE/ESCALATE tokens
│       ├── tts.py               # Kokoro TTS → WAV → static file
│       └── call_manager.py      # Orchestrates the full call lifecycle
├── scripts/
│   ├── seed_user.py             # Create test user Margaret
│   └── trigger_call.py          # Manually fire a test call
├── docker-compose.yml           # PostgreSQL + pgvector (port 5433)
├── .env.example
└── README.md
```

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.11+
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

### 6. Seed Margaret and make a call

```bash
# From project root, venv active
source backend/venv/bin/activate

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
                    └─► LLM generates greeting
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
                                    └─► [ESCALATE] → SMS to family
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `TWILIO_ACCOUNT_SID` | From Twilio console homepage |
| `TWILIO_AUTH_TOKEN` | From Twilio console homepage |
| `TWILIO_PHONE_NUMBER` | Your Twilio number (E.164 format) |
| `DATABASE_URL` | Postgres connection string (port 5433 to avoid local conflicts) |
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Model name (recommended: `llama3.2:3b`) |
| `BASE_URL` | Your ngrok URL — must be publicly reachable by Twilio |
| `AUDIO_DIR` | Where TTS WAV files are saved (default: `./audio`) |