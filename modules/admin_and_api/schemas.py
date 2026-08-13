"""Pydantic request/response schemas for the REST API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from shared.enums import FeedbackTypeEnum, LeadLevelEnum, KeywordTypeEnum


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
