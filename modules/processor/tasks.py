"""Async processing tasks for message ingestion and lead generation."""

from core.logger import setup_logging
from modules.processor.worker import celery_app

logger = setup_logging(__name__)


@celery_app.task(name="tasks.process_raw_message")
def process_raw_message(payload: dict) -> dict:
    """
    Full processing pipeline for a single raw message.

    Steps: persist → match keywords → NLP score → create lead → notify.

    Args:
        payload: Dict containing message text, metadata, chat_id, etc.
    """
    message_id = payload.get("message_id")
    text = payload.get("text", "")
    chat_title = payload.get("chat_title", "Unknown")

    logger.info("Processing message %s from '%s' (placeholder)", message_id, chat_title)

    # TODO: Orchestrate matching, NLP, persistence, and notification

    return {"status": "success", "message_id": message_id}