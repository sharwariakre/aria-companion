#!/usr/bin/env python3
"""
Seed 7 fake completed calls for Margaret with realistic mood scores.

Day sequence:
  Day -7  0.62  (baseline building)
  Day -6  0.58  (baseline building)
  Day -5  0.71  (baseline building — 3rd call, baseline now established)
  Day -4  0.65  (normal)
  Day -3  0.28  ← THE DIP — flagged, email alert triggered  ← demo moment
  Day -2  0.55  (recovering)
  Day -1  0.67  (back to normal)

Usage (from repo root, venv active, DB running):
  python scripts/seed_mood_history.py
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aria:aria@localhost:5433/aria_db",
)

# Mood sequence — (score, features_profile)
# profiles: "normal", "good", "low"
CALL_PLAN = [
    # (days_ago, mood_score, profile, flagged)
    (7, 0.62, "normal", False),
    (6, 0.58, "normal", False),
    (5, 0.71, "good",   False),
    (4, 0.65, "normal", False),
    (3, 0.28, "low",    True),   # THE DIP
    (2, 0.55, "normal", False),
    (1, 0.67, "good",   False),
]

# Representative feature sets per profile
FEATURE_PROFILES = {
    "normal": {
        "energy": 0.038,
        "pitch_mean": 198.0,
        "pitch_std": 28.0,
        "speech_rate": 9.5,
        "pause_ratio": 0.38,
        "duration_seconds": 240.0,
    },
    "good": {
        "energy": 0.051,
        "pitch_mean": 215.0,
        "pitch_std": 35.0,
        "speech_rate": 11.2,
        "pause_ratio": 0.29,
        "duration_seconds": 310.0,
    },
    "low": {
        "energy": 0.018,
        "pitch_mean": 155.0,
        "pitch_std": 11.0,
        "speech_rate": 4.1,
        "pause_ratio": 0.71,
        "duration_seconds": 185.0,
    },
}

SAMPLE_TRANSCRIPTS = {
    "normal": (
        "Aria: Good morning Margaret! How are you feeling today?\n"
        "User: Oh, pretty good I suppose. Had a nice cup of tea this morning.\n"
        "Aria: That sounds lovely. Any plans for the day?\n"
        "User: Not much, maybe watch some TV. Sarah called last night which was nice.\n"
        "Aria: How wonderful that Sarah called. What did you two chat about?\n"
        "User: Oh this and that. She's doing well at her job. I'm proud of her.\n"
        "Aria: You should be! It's so nice to hear she's thriving.\n"
        "User: Yes. Biscuit is being a bit clingy today too.\n"
        "Aria: Cats always know when we need company. Take care Margaret, talk soon."
    ),
    "good": (
        "Aria: Good morning Margaret! You sound bright today!\n"
        "User: I do feel good! I slept wonderfully and made pancakes this morning.\n"
        "Aria: Pancakes sound delicious. Any special occasion?\n"
        "User: No, just felt like it! I called Sarah and she's visiting next weekend.\n"
        "Aria: That's wonderful news — you must be so excited.\n"
        "User: I am! I'm going to make her favourite lasagne.\n"
        "Aria: She's a lucky daughter. Have a beautiful day Margaret."
    ),
    "low": (
        "Aria: Good morning Margaret. How are you feeling today?\n"
        "User: Not so great to be honest. I didn't sleep well.\n"
        "Aria: I'm sorry to hear that. What kept you up?\n"
        "User: Just... I don't know. Felt lonely I think. Everything feels a bit heavy.\n"
        "Aria: I hear you Margaret. Those feelings are real and valid.\n"
        "User: I just miss people. Biscuit is here but it's quiet.\n"
        "Aria: You're not alone — I'm here, and I'll make sure someone checks in on you.\n"
        "User: Thank you. That's kind.\n"
        "Aria: Take good care of yourself today. Someone will be in touch soon."
    ),
}


async def seed():
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with Session() as db:
        # Find Margaret
        from models.user import Call, User

        result = await db.execute(select(User).where(User.name == "Margaret"))
        margaret = result.scalars().first()
        if not margaret:
            print("ERROR: Margaret not found. Run scripts/seed_user.py first.")
            return

        # Check how many seeded calls already exist
        existing = await db.execute(
            text("SELECT COUNT(*) FROM calls WHERE user_id = :uid AND transcript IS NOT NULL"),
            {"uid": str(margaret.id)},
        )
        count = existing.scalar()
        if count and count >= 7:
            print(f"Margaret already has {count} calls with transcripts. Skipping.")
            print("To re-seed, delete existing calls first:")
            print(f"  DELETE FROM calls WHERE user_id = '{margaret.id}';")
            return

        now = datetime.utcnow()
        inserted = 0

        for days_ago, mood_score, profile, flagged in CALL_PLAN:
            call_time = now - timedelta(days=days_ago)
            features = FEATURE_PROFILES[profile]
            transcript = SAMPLE_TRANSCRIPTS[profile]

            call = Call(
                id=uuid.uuid4(),
                user_id=margaret.id,
                twilio_call_sid=f"CA_seed_{uuid.uuid4().hex[:16]}",
                started_at=call_time,
                ended_at=call_time + timedelta(minutes=int(features["duration_seconds"] // 60)),
                transcript=transcript,
                messages=[],
                turn_count=transcript.count("Aria:"),
                mood_score=mood_score,
                mood_features=features,
                mood_delta=round(mood_score - 0.5, 3),
                flagged=flagged,
                summary=f"{'Concerning call — Margaret sounded low' if flagged else 'Normal check-in call'}.",
            )
            db.add(call)
            inserted += 1
            flag_note = "  ← FLAGGED (email alert would fire)" if flagged else ""
            print(f"  Day -{days_ago:1d}  mood={mood_score:.2f}  profile={profile}{flag_note}")

        await db.commit()
        print(f"\nInserted {inserted} seeded calls for Margaret ({margaret.id}).")
        print("\nDemo tip:")
        print("  Day -3 (score=0.28) is your dashboard demo moment.")
        print("  Point to the dip and say: 'This triggered an email alert to Sarah automatically.'")
        print(f"\nVerify: GET {os.getenv('BASE_URL', 'http://localhost:8001')}/mood/{margaret.id}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
