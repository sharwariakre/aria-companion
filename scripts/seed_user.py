#!/usr/bin/env python3
"""
Seed a test user — Margaret, 78 — into the Aria database.

Usage (from repo root, with the DB running):
  python scripts/seed_user.py

Or with a custom phone number:
  MARGARET_PHONE=+15551234567 python scripts/seed_user.py
"""

import asyncio
import os
import sys
from datetime import time
from pathlib import Path

# Make backend/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aria:aria@localhost:5432/aria_db",
)

MARGARET_PHONE = os.getenv("MARGARET_PHONE", "+15550000001")
FAMILY_PHONE = os.getenv("FAMILY_PHONE", "+15550000002")


async def seed():
    engine = create_async_engine(DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    # Bootstrap tables + pgvector extension
    from db.database import Base
    import models.user  # noqa: F401 — registers ORM models with Base

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        from models.user import User

        # Check if Margaret already exists
        result = await db.execute(select(User).where(User.name == "Margaret"))
        existing = result.scalars().first()

        if existing:
            print(f"Margaret already exists (id={existing.id}).  Skipping insert.")
            print(f"  phone        : {existing.phone_number}")
            print(f"  family_phone : {existing.family_phone}")
            return

        margaret = User(
            name="Margaret",
            phone_number=MARGARET_PHONE,
            family_phone=FAMILY_PHONE,
            call_time=time(9, 0),
            timezone="America/New_York",
        )
        db.add(margaret)
        await db.commit()
        await db.refresh(margaret)

        print("Margaret created successfully!")
        print(f"  id           : {margaret.id}")
        print(f"  phone        : {margaret.phone_number}")
        print(f"  family_phone : {margaret.family_phone}")
        print(f"  call_time    : {margaret.call_time}  ({margaret.timezone})")
        print()
        print("Set MARGARET_PHONE / FAMILY_PHONE env vars to override defaults.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
