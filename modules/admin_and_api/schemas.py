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
    is_admin: bool = False
    created_at: datetime


class AdminUserResponse(BaseModel):
    """Admin user row including license expiry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool = False
    business_type: Optional[str] = None
    dashboard_password: Optional[str] = None
    license_expires_at: Optional[datetime] = None


class AdminLicenseRenewRequest(BaseModel):
    """Days to add to a user's subscription."""

    days: int = Field(..., gt=0)


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


class KeywordUpdate(BaseModel):
    """Partial update for an existing keyword rule."""

    text: Optional[str] = Field(default=None, max_length=100)
    keyword_type: Optional[KeywordTypeEnum] = None
    weight: Optional[float] = Field(default=None, ge=0)


class KeywordResponse(BaseModel):
    """Public representation of a keyword row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    word: str
    type: KeywordTypeEnum
    weight: float
    created_at: datetime


class LicenseStatusResponse(BaseModel):
    """Current subscription validity for the authenticated user."""

    user_id: int
    is_valid: bool
    days_remaining: int
    subscription_end: Optional[datetime] = None


class LicenseRenewRequest(BaseModel):
    """Admin request to extend a user's subscription."""

    user_id: int
    extra_days: int = Field(..., gt=0)


class AdminSessionResponse(BaseModel):
    """Active Telegram session row for the admin sessions view."""

    id: int
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: str
    is_active: bool
    created_at: datetime


class FeedbackCreate(BaseModel):
    """Payload for submitting lead quality feedback."""

    lead_id: int
    feedback_type: FeedbackTypeEnum
    comment: str | None = None

class TelegramSendCodeRequest(BaseModel):
    phone_number: str  # فرمت: +989123456789


class TelegramVerifyRequest(BaseModel):
    """Payload for verifying Telegram login and attaching a session to a user."""

    phone_number: str
    phone_code_hash: str
    code: str
    two_factor_password: Optional[str] = None
    target_user_id: Optional[int] = None
    business_type: Optional[str] = None
    username: Optional[str] = None


TelegramVerifyCodeRequest = TelegramVerifyRequest
