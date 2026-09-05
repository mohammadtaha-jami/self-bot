"""Pydantic request/response schemas for the REST API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.enums import FeedbackTypeEnum, LeadLevelEnum, KeywordTypeEnum


class UserCreate(BaseModel):
    """Payload for registering a new tenant user."""

    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    phone_number: Optional[str] = Field(default=None, min_length=5, max_length=20)
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
    phone_number: Optional[str] = None
    telegram_username: Optional[str] = None
    telegram_id: Optional[int] = None
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool = False
    business_type: Optional[str] = None
    created_at: datetime


class AdminUserResponse(BaseModel):
    """Admin user row including license expiry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: Optional[str] = None
    phone_number: Optional[str] = None
    telegram_username: Optional[str] = None
    telegram_id: Optional[int] = None
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool = False
    business_type: Optional[str] = None
    dashboard_password: Optional[str] = None
    license_expires_at: Optional[datetime] = None


class AdminUserCreate(BaseModel):
    """Admin-created user; independent of Telegram login."""

    full_name: str = Field(..., min_length=1, max_length=100)
    username: str = Field(..., min_length=3, max_length=100)
    phone_number: str = Field(..., min_length=5, max_length=20)
    password: str = Field(..., min_length=6, max_length=128)
    business_type: Optional[str] = None
    license_duration_days: Optional[int] = Field(default=None, gt=0)
    license_expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def require_license_window(self):
        if self.license_duration_days is None and self.license_expires_at is None:
            raise ValueError("یکی از فیلدهای license_duration_days یا license_expires_at الزامی است.")
        return self


class AdminUserUpdate(BaseModel):
    """Partial admin update for an existing user."""

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    phone_number: Optional[str] = Field(default=None, min_length=5, max_length=20)
    username: Optional[str] = Field(default=None, min_length=3, max_length=100)
    business_type: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    license_days: Optional[int] = Field(default=None, gt=0)
    is_active: Optional[bool] = None


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
    """Payload for creating a custom keyword rule."""

    text: str = Field(..., min_length=1, max_length=100)
    keyword_type: KeywordTypeEnum = KeywordTypeEnum.POSITIVE
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


class KeywordBundleResponse(BaseModel):
    """Default, custom, and merged keywords for the dashboard and Redis cache."""

    business_type: Optional[str] = None
    default_keywords: list[str]
    custom_keywords: list[KeywordResponse]
    final_keywords: list[str]


class LicenseStatusResponse(BaseModel):
    """Current subscription validity for the authenticated user."""

    user_id: int
    is_valid: bool
    days_remaining: int
    subscription_end: Optional[datetime] = None


class EngineStartRequest(BaseModel):
    """Optional Telegram chat-folder scope when starting the engine."""

    folder_id: Optional[int] = None


class TelegramFolderOption(BaseModel):
    """One Telegram Dialog Filter (chat folder) for the dashboard dropdown."""

    id: Optional[int] = None
    title: str
    kind: str = "all"


class TelegramFolderListResponse(BaseModel):
    folders: list[TelegramFolderOption]
    selected_folder_id: Optional[int] = None
    detail: Optional[str] = None


class EngineStatusResponse(BaseModel):
    """Live engine flag, cached keyword count, and license window."""

    engine_active: bool
    license_valid: bool
    keyword_count: int
    days_remaining: int
    license_expires_at: Optional[datetime] = None
    indicator: str = Field(
        description="listening | stopped | expired",
    )
    listen_mode: str = "all"
    listen_folder_id: Optional[int] = None
    listen_folder_title: Optional[str] = None
    allowed_chat_count: Optional[int] = None


class EnginePipelineStep(BaseModel):
    """Single pipeline step shown in the dashboard timeline."""

    id: str
    title: str
    description: str
    status: str = Field(description="success | warning | error | running | pending")
    detail: Optional[str] = None
    timestamp: datetime


class EngineActionResponse(EngineStatusResponse):
    """Engine status plus ordered pipeline steps from start/stop."""

    pipeline: list[EnginePipelineStep] = Field(default_factory=list)


class EnginePipelineLogResponse(BaseModel):
    """Recent pipeline log entries stored in Redis."""

    items: list[EnginePipelineStep] = Field(default_factory=list)


class LicenseRenewRequest(BaseModel):
    """Admin request to extend a user's subscription."""

    user_id: int
    extra_days: int = Field(..., gt=0)


class AdminSessionResponse(BaseModel):
    """Telegram session row for the admin sessions view."""

    id: int
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: str
    is_active: bool
    is_engine_active: bool = False
    is_listening: bool = False
    created_at: datetime


class FeedbackCreate(BaseModel):
    """Payload for submitting lead quality feedback."""

    lead_id: int
    feedback_type: FeedbackTypeEnum
    comment: str | None = None

class TelegramSendCodeRequest(BaseModel):
    phone_number: str  # فرمت: +989123456789


class TelegramVerifyRequest(BaseModel):
    """Verify Telegram login and attach the session to an existing user."""

    phone_number: str
    phone_code_hash: str
    code: str
    two_factor_password: Optional[str] = None
    user_id: Optional[int] = None
    target_user_id: Optional[int] = None

    @model_validator(mode="after")
    def require_existing_user(self):
        if self.user_id is None and self.target_user_id is None:
            raise ValueError("انتخاب کاربر مقصد (user_id) الزامی است.")
        return self

    @property
    def owner_user_id(self) -> int:
        if self.user_id is not None:
            return self.user_id
        if self.target_user_id is not None:
            return self.target_user_id
        raise ValueError("انتخاب کاربر مقصد (user_id) الزامی است.")


TelegramVerifyCodeRequest = TelegramVerifyRequest
