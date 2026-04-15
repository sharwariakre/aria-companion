#!/usr/bin/env python3
"""
Manually trigger a test call to Margaret (or any user by name or ID).

Usage (from repo root, DB + backend must be running):
  python scripts/trigger_call.py
  python scripts/trigger_call.py --user-id <uuid>
  python scripts/trigger_call.py --name "Margaret"
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

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aria:aria@localhost:5432/aria_db",
)


async def trigger(user_id: UUID | None, name: str):
    engine = create_async_engine(DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with SessionLocal() as db:
        from models.user import User
        from services.call_manager import trigger_outbound_call

        if user_id:
            user = await db.get(User, user_id)
        else:
            result = await db.execute(select(User).where(User.name == name))
            user = result.scalars().first()

        if not user:
            print(f"ERROR: No user found (id={user_id}, name='{name}').")
            print("Run scripts/seed_user.py first.")
            return

        print(f"Triggering call for {user.name} ({user.phone_number})…")
        sid = await trigger_outbound_call(user, db)
        print(f"Call created!  Twilio SID: {sid}")
        print()
        print("Watch your phone — Aria will call momentarily.")
        print("Check backend logs for the full conversation trace.")

    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Trigger an Aria test call")
    parser.add_argument("--user-id", type=UUID, default=None, help="User UUID")
    parser.add_argument("--name", type=str, default="Margaret", help="User name")
    args = parser.parse_args()
    asyncio.run(trigger(user_id=args.user_id, name=args.name))


if __name__ == "__main__":
    main()
