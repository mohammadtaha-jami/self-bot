"""Async processing tasks for message ingestion and lead generation."""

from core.logger import setup_logging

logger = setup_logging(__name__)


async def process_raw_message(message_id: str) -> None:
    """
    Full processing pipeline for a single raw message.

    Steps: persist → match keywords → NLP score → create lead → notify.

    Args:
        message_id: Unique identifier of the queued raw message.
    """
    # TODO: Orchestrate matching, NLP, persistence, and notification
    logger.info("Processing message %s (placeholder)", message_id)
    raise NotImplementedError("Processing task not yet implemented")
