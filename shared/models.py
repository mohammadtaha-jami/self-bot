"""ORM database models for the Telegram Lead Intelligence domain using SQLAlchemy 2.0."""

# Placeholder module — full model definitions to be implemented in Phase 1.
#
# Planned models:
#   - User        : SaaS tenant / account owner
#   - Session     : Telethon StringSession per user
#   - Keyword     : User-defined matching rules
#   - Source      : Monitored Telegram channels/groups
#   - Person      : Identified contact / author profile
#   - Message     : Raw ingested Telegram message
#   - Lead        : Scored opportunity derived from a Message
#   - Feedback    : User quality signal on a Lead



from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# استفاده از Base یکپارچه پروژه جهت شناسایی توسط Alembic و Core
from core.database import Base as BaseModel
from shared.enums import FeedbackTypeEnum, KeywordTypeEnum, LeadLevelEnum


class User(BaseModel):
    """SaaS tenant / account owner."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Telegram @username from get_me(), independent of login username",
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Dashboard login username (not phone, not Telegram @id)",
    )
    phone_number: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Contact / Telegram session phone",
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    business_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="e.g. real_estate, crypto, general, or a custom value",
    )
    listen_folder_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Telegram DialogFilter id; NULL means listen to all groups/channels",
    )
    listen_folder_title: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Cached Telegram folder title for the dashboard",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    dashboard_password: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="Plain dashboard password for non-admin users (admin panel display only)",
    )
    subscription_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    sessions: Mapped[List["TelegramSession"]] = relationship("TelegramSession", back_populates="user", cascade="all, delete-orphan")
    keywords: Mapped[List["Keyword"]] = relationship("Keyword", back_populates="user", cascade="all, delete-orphan")
    leads: Mapped[List["Lead"]] = relationship("Lead", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_superuser(self) -> bool:
        """Admin flag used by API dependencies (`is_admin` column)."""
        return bool(self.is_admin)


class TelegramSession(BaseModel):
    """Telethon StringSession per user."""

    __tablename__ = "telegram_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    session_string: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_engine_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="True when the user has started the listening engine from the dashboard",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="sessions")


class Keyword(BaseModel):
    """User-defined matching rules."""

    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[KeywordTypeEnum] = mapped_column(SQLEnum(KeywordTypeEnum), default=KeywordTypeEnum.POSITIVE)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="keywords")


class Source(BaseModel):
    """Monitored Telegram channels/groups."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_score: Mapped[float] = mapped_column(Float, default=50.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="source")


class Person(BaseModel):
    """Identified contact / author profile."""

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    topic_profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="person")
    leads: Mapped[List["Lead"]] = relationship("Lead", back_populates="person")


class Message(BaseModel):
    """Raw ingested Telegram message."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    source: Mapped["Source"] = relationship("Source", back_populates="messages")
    person: Mapped["Person"] = relationship("Person", back_populates="messages")
    leads: Mapped[List["Lead"]] = relationship("Lead", back_populates="message")


class Lead(BaseModel):
    """Scored opportunity derived from a Message."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    intent_score: Mapped[float] = mapped_column(Float, nullable=False)
    lead_level: Mapped[LeadLevelEnum] = mapped_column(SQLEnum(LeadLevelEnum), default=LeadLevelEnum.WARM)
    evidence_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="leads")
    message: Mapped["Message"] = relationship("Message", back_populates="leads")
    person: Mapped["Person"] = relationship("Person", back_populates="leads")
    feedbacks: Mapped[List["Feedback"]] = relationship("Feedback", back_populates="lead")


class Feedback(BaseModel):
    """User quality signal on a Lead."""

    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[FeedbackTypeEnum] = mapped_column(SQLEnum(FeedbackTypeEnum), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="feedbacks")
