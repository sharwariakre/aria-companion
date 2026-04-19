#!/usr/bin/env python3
"""
Re-run post_call_processing on recent calls to backfill mood scores.

Usage (from repo root, venv active):
  python scripts/reprocess_mood.py              # last 10 calls
  python scripts/reprocess_mood.py --limit 3    # last N calls
  python scripts/reprocess_mood.py --call-id <uuid>  # specific call
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://aria:aria@localhost:5433/aria_db")


async def run(call_id: UUID | None, limit: int):
    engine = create_async_engine(DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with SessionLocal() as db:
        from models.user import Call
        from services.call_manager import post_call_processing

        if call_id:
            call = await db.get(Call, call_id)
            calls = [call] if call else []
        else:
            result = await db.execute(
                select(Call)
                .where(Call.ended_at.isnot(None))
                .order_by(Call.started_at.desc())
                .limit(limit)
            )
            calls = list(result.scalars().all())

    if not calls:
        print("No calls found.")
        await engine.dispose()
        return

    print(f"Reprocessing {len(calls)} call(s)...\n")
    for call in reversed(calls):  # oldest first so baseline builds correctly
        print(f"  call {call.id}  turns={call.turn_count}  started={call.started_at}")
        await post_call_processing(call.id)
        print(f"  done\n")

    # Print updated scores
    engine2 = create_async_engine(DATABASE_URL, echo=False)
    Session2 = async_sessionmaker(bind=engine2, expire_on_commit=False)
    async with Session2() as db:
        from models.user import Call
        for call in reversed(calls):
            refreshed = await db.get(Call, call.id)
            print(f"  {refreshed.id}  mood_score={refreshed.mood_score}  flagged={refreshed.flagged}")

    await engine.dispose()
    await engine2.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--call-id", type=UUID, default=None)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(run(call_id=args.call_id, limit=args.limit))


if __name__ == "__main__":
    main()
