from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create all tables. Called on app startup."""
    # Import all models so Base knows about them before create_all
    import models.user  # noqa: F401  — registers User, Call, Memory with Base

    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
        )
        await conn.run_sync(Base.metadata.create_all)

        # Add columns introduced in later phases (idempotent — safe to re-run)
        migrations = [
            "ALTER TABLE calls ADD COLUMN IF NOT EXISTS sentiment_score FLOAT",
            "ALTER TABLE calls ADD COLUMN IF NOT EXISTS emotional_state VARCHAR(64)",
            "ALTER TABLE calls ADD COLUMN IF NOT EXISTS masking_detected BOOLEAN DEFAULT FALSE",
            "ALTER TABLE calls ADD COLUMN IF NOT EXISTS contradiction_flag BOOLEAN DEFAULT FALSE",
        ]
        for sql in migrations:
            await conn.execute(__import__("sqlalchemy").text(sql))
