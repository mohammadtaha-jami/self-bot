"""Pydantic request/response schemas for the REST API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from shared.enums import FeedbackTypeEnum, LeadLevelEnum, KeywordTypeEnum


class UserCreate(BaseModel):
    """Payload for registering a new tenant user."""

    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    business_type: Optional[str] = None
    telegram_id: Optional[int] = None


class UserLogin(BaseModel):
    """JSON login payload (username may be an email-style identifier)."""

    username: str
    password: str


class UserResponse(BaseModel):
    """Public user profile returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    """OAuth2 access-token response."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Decoded JWT subject payload."""

    username: Optional[str] = None
    user_id: Optional[int] = None


class LeadResponse(BaseModel):
    """Public representation of a detected lead."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: int
    level: LeadLevelEnum
    score: float
    created_at: datetime


class KeywordCreate(BaseModel):
    """Payload for creating a new keyword rule."""

    text: str
    keyword_type: KeywordTypeEnum
    is_active: bool = True


class FeedbackCreate(BaseModel):
    """Payload for submitting lead quality feedback."""

    lead_id: int
    feedback_type: FeedbackTypeEnum
    comment: str | None = None
