"""Async processing tasks for message ingestion and lead generation."""

import asyncio
import os

from core.logger import setup_logging
from modules.processor.matching import MatchConfig, match_keywords
from modules.processor.nlp import clean_text
from modules.processor.presets import get_rules_for_business_types
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
    business_type = payload.get("business_type")  # مثلا "programmer" یا "programmer, web_designer"

    if not raw_text:
        logger.warning("Received empty message payload for ID: %s", message_id)
        return {"status": "ignored", "reason": "empty_text", "message_id": message_id}

    logger.info(
        "Processing message %s from '%s' (Business Types: %s)",
        message_id,
        chat_title,
        business_type,
    )

    # ۱. دریافت کلمات پیش‌فرض دسته‌بندی(ها) از فایل‌های JSON
    preset_rules = get_rules_for_business_types(business_type)

    # ۲. تعیین کلمات کلیدی (اولویت با کلمات اختصاصی پویلود است، در غیر این صورت از پریست استفاده می‌شود)
    keywords = payload.get("keywords") or preset_rules["keywords"]
    negative_keywords = (
        payload.get("negative_keywords") or preset_rules["negative_keywords"]
    )
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
        fuzzy_threshold=fuzzy_threshold,
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
    message_text = format_lead_message(payload, lead_data)
    session_string = payload.get("session_string")
    celery_app.send_task(
        "tasks.publish_lead_notification",
        args=[session_string, message_text],
    )

    return {
        "status": "lead_created",
        "message_id": message_id,
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