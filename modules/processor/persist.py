"""Persist matched leads into PostgreSQL."""

from datetime import datetime, timezone

from sqlalchemy import select

from core.database import get_session_factory
from core.logger import setup_logging
from modules.ai_engine.schemas import PredictionResult
from modules.processor.matching import MatchResult
from shared.models import Lead, Message, Person, Source, User

logger = setup_logging(__name__)


def _parse_message_date(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def build_lead_evidence(
    payload: dict,
    match_result: MatchResult,
    prediction: PredictionResult | None = None,
) -> dict:
    """JSON payload stored on Lead.evidence_json, including AI metadata."""
    evidence = {
        "matched_keywords": match_result.matched_keywords,
        "chat_title": payload.get("chat_title"),
        "sender_username": payload.get("sender_username"),
    }
    if prediction is not None:
        evidence.update(
            {
                "ai_label": int(prediction.label),
                "ai_label_name": prediction.label.name,
                "ai_confidence": float(prediction.confidence),
                "ai_latency_ms": float(prediction.latency_ms),
                "ai_source": prediction.source,
            }
        )
    return evidence


async def persist_matched_lead(
    payload: dict,
    match_result: MatchResult,
    prediction: PredictionResult | None = None,
) -> tuple[int | None, int | None, bool]:
    """Insert lead rows (with AI metadata) and return (lead_id, chat_id, notifier)."""
    user_id = payload.get("user_id")
    chat_id = payload.get("chat_id")
    sender_id = payload.get("sender_id")
    telegram_message_id = payload.get("message_id")
    if not user_id or chat_id is None or telegram_message_id is None:
        logger.warning("Skip lead persist: missing user_id/chat_id/message_id")
        return None, None, False
    if sender_id is None:
        sender_id = int(chat_id)

    session_factory = get_session_factory()
    async with session_factory() as db:
        source = (
            await db.execute(select(Source).where(Source.telegram_chat_id == int(chat_id)))
        ).scalar_one_or_none()
        if source is None:
            source = Source(
                telegram_chat_id=int(chat_id),
                title=payload.get("chat_title"),
                username=None,
            )
            db.add(source)
            await db.flush()

        person = (
            await db.execute(select(Person).where(Person.telegram_user_id == int(sender_id)))
        ).scalar_one_or_none()
        if person is None:
            person = Person(
                telegram_user_id=int(sender_id),
                username=payload.get("sender_username"),
                topic_profile={},
            )
            db.add(person)
            await db.flush()

        message = Message(
            telegram_message_id=int(telegram_message_id),
            source_id=source.id,
            person_id=person.id,
            raw_text=payload.get("text") or "",
            message_date=_parse_message_date(payload.get("date")),
        )
        db.add(message)
        await db.flush()

        lead = Lead(
            user_id=int(user_id),
            message_id=message.id,
            person_id=person.id,
            intent_score=float(match_result.score),
            lead_level=match_result.lead_level,
            evidence_json=build_lead_evidence(payload, match_result, prediction),
        )
        db.add(lead)
        await db.commit()
        await db.refresh(lead)
        owner = (
            await db.execute(
                select(User.telegram_chat_id, User.is_notifier_active).where(
                    User.id == int(user_id)
                )
            )
        ).one_or_none()
        logger.info("Lead persisted id=%s user_id=%s", lead.id, user_id)
        if owner is None:
            return lead.id, None, False
        return lead.id, owner.telegram_chat_id, bool(owner.is_notifier_active)
