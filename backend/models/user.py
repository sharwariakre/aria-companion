import uuid
from datetime import datetime, time
from typing import Optional

from sqlalchemy import String, Text, Float, Boolean, ForeignKey, DateTime, Time, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    family_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    call_time: Mapped[time] = mapped_column(Time, default=time(9, 0))
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    calls: Mapped[list["Call"]] = relationship("Call", back_populates="user")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    twilio_call_sid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Conversation history stored as JSON list of {role, content} dicts
    messages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    turn_count: Mapped[int] = mapped_column(default=0)
    mood_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mood_delta: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship("User", back_populates="calls")
