"""Async processing tasks for message ingestion and lead generation."""

import asyncio
import os

from core.logger import setup_logging
from modules.processor.matching import MatchConfig, match_keywords
from modules.processor.nlp import clean_text
from modules.processor.persist import persist_matched_lead
from modules.processor.presets import (
    get_rules_for_business_types,
    get_user_engine_status,
    get_user_keywords_cache,
)
from modules.processor.worker import celery_app
from modules.notification.formatter import format_lead_message
from modules.notification.sender import send_lead_notification

logger = setup_logging(__name__)


@celery_app.task(name="tasks.process_raw_message")
def process_raw_message(payload: dict) -> dict:
    """
    Full processing pipeline for a single raw message.

    Steps: Extract -> Load Presets -> Clean text -> Match keywords -> Evaluate lead level.

    Args:
        payload: Dict containing message text, metadata, business_type, custom keywords, etc.
    """
    message_id = payload.get("message_id")
    raw_text = payload.get("text", "")
    chat_title = payload.get("chat_title", "Unknown")
    business_type = payload.get("business_type")
    user_id = payload.get("user_id")

    if not raw_text:
        logger.warning("Received empty message payload for ID: %s", message_id)
        return {"status": "ignored", "reason": "empty_text", "message_id": message_id}

    if user_id:
        engine_status = get_user_engine_status(user_id)
        if not engine_status.get("engine_active") or not engine_status.get("license_valid"):
            logger.info(
                "Message %s skipped: engine inactive or license invalid for user %s",
                message_id,
                user_id,
            )
            return {
                "status": "ignored",
                "reason": "engine_inactive_or_license_invalid",
                "message_id": message_id,
            }

    logger.info(
        "Processing message %s from '%s' (Business Types: %s)",
        message_id,
        chat_title,
        business_type,
    )

    preset_rules = get_rules_for_business_types(business_type)
    cached = get_user_keywords_cache(user_id) if user_id else None

    keywords = payload.get("keywords")
    negative_keywords = payload.get("negative_keywords")
    if cached:
        if isinstance(cached, list):
            keywords = keywords or cached
        elif isinstance(cached, dict):
            keywords = keywords or cached.get("final_keywords") or cached.get("keywords")
            negative_keywords = negative_keywords or cached.get("negative_keywords")
    keywords = keywords or preset_rules["keywords"]
    negative_keywords = negative_keywords or preset_rules["negative_keywords"] or []
    fuzzy_threshold = payload.get("fuzzy_threshold", 85.0)

    # اگر هیچ کلمه‌ای تنظیم نشده باشد، نیازی به پردازش متن نیست
    if not keywords:
        logger.info(
            "No keywords defined for message %s (business_type: %s). Ignored.",
            message_id,
            business_type,
        )
        return {
            "status": "ignored",
            "reason": "no_keywords_configured",
            "message_id": message_id,
        }

    # ۳. پاک‌سازی و نرمال‌سازی متن
    cleaned_text = clean_text(raw_text)

    config = MatchConfig(
        keywords=keywords,
        negative_keywords=negative_keywords,
        fuzzy_threshold=float(fuzzy_threshold),
        min_text_len=int(payload.get("min_text_len", MatchConfig.min_text_len)),
        min_meaningful_tokens=int(
            payload.get("min_meaningful_tokens", MatchConfig.min_meaningful_tokens)
        ),
        require_min_tokens=bool(payload.get("require_min_tokens", True)),
        min_fuzzy_len=int(payload.get("min_fuzzy_len", MatchConfig.min_fuzzy_len)),
        min_text_to_keyword_ratio=float(
            payload.get("min_text_to_keyword_ratio", MatchConfig.min_text_to_keyword_ratio)
        ),
        min_distinct_keywords_for_hot=int(
            payload.get(
                "min_distinct_keywords_for_hot",
                MatchConfig.min_distinct_keywords_for_hot,
            )
        ),
        min_exact_chars_for_hot=int(
            payload.get("min_exact_chars_for_hot", MatchConfig.min_exact_chars_for_hot)
        ),
    )

    # ۴. اجرای الگوریتم تطبیق کلمات کلیدی
    match_result = match_keywords(raw_text, config)

    if not match_result.matched:
        logger.info("Message %s ignored: %s", message_id, match_result.reason)
        return {
            "status": "ignored",
            "reason": match_result.reason,
            "message_id": message_id,
        }

    # ۵. شناسایی لید موفق
    logger.info(
        "Lead detected! Msg: %s | Level: %s | Score: %.1f | Keywords: %s",
        message_id,
        match_result.lead_level.value,
        match_result.score,
        match_result.matched_keywords,
    )

    lead_data = {
        "lead_level": match_result.lead_level.value,
        "matched_keywords": match_result.matched_keywords,
        "score": match_result.score,
    }

    lead_id = None
    try:
        lead_id = asyncio.run(persist_matched_lead(payload, match_result))
    except Exception:
        logger.exception("Failed to persist lead for message %s", message_id)

    message_text = format_lead_message(payload, lead_data)
    session_string = payload.get("session_string")
    celery_app.send_task(
        "tasks.publish_lead_notification",
        args=[session_string, message_text],
    )

    return {
        "status": "lead_created",
        "message_id": message_id,
        "lead_id": lead_id,
        "lead_level": match_result.lead_level.value,
        "matched_keywords": match_result.matched_keywords,
        "score": match_result.score,
        "cleaned_text": cleaned_text,
    }


@celery_app.task(name="tasks.publish_lead_notification")
def publish_lead_notification(session_string: str, message_text: str) -> dict:
    """Send a formatted lead alert to Telegram Saved Messages."""
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    sent = asyncio.run(
        send_lead_notification(
            int(api_id) if api_id else 0,
            api_hash or "",
            session_string or "",
            message_text,
        )
    )
    return {"status": "sent" if sent else "failed"}