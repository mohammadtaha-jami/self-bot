"""Leads management endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.admin_and_api.deps import get_current_user, get_db
from modules.admin_and_api.schemas import LeadResponse
from shared.models import Lead, Message, User

router = APIRouter()

_TEXT_PREVIEW_LEN = 180


def _to_lead_response(lead: Lead) -> LeadResponse:
    message = lead.message
    person = lead.person
    source = message.source if message is not None else None
    evidence = lead.evidence_json or {}
    raw_text = (message.raw_text if message is not None else "") or ""
    preview = raw_text if len(raw_text) <= _TEXT_PREVIEW_LEN else raw_text[:_TEXT_PREVIEW_LEN].rstrip() + "…"
    keywords = evidence.get("matched_keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    return LeadResponse(
        id=lead.id,
        message_id=message.telegram_message_id if message is not None else lead.message_id,
        level=lead.lead_level,
        score=lead.intent_score,
        created_at=lead.created_at,
        chat_title=evidence.get("chat_title") or (source.title if source is not None else None),
        sender_username=evidence.get("sender_username")
        or (person.username if person is not None else None),
        text=preview,
        matched_keywords=[str(item) for item in keywords],
    )


@router.get("/", response_model=list[LeadResponse])
async def list_leads(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LeadResponse]:
    """Return recent leads for the authenticated user."""
    result = await db.execute(
        select(Lead)
        .options(
            selectinload(Lead.message).selectinload(Message.source),
            selectinload(Lead.person),
        )
        .where(Lead.user_id == current_user.id)
        .order_by(Lead.created_at.desc())
        .limit(limit)
    )
    return [_to_lead_response(lead) for lead in result.scalars().all()]
