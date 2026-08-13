"""Redis queue producer for raw Telegram messages."""

from core.logger import setup_logging

logger = setup_logging(__name__)

MESSAGE_QUEUE_KEY = "queue:raw_messages"


async def publish_raw_message(payload: dict) -> None:
    """
    Push a serialized raw message onto the Redis processing queue.

    Args:
        payload: Dict containing message_id, source_id, text, metadata, etc.
    """
    # TODO: Serialize payload and LPUSH to Redis
    logger.debug("Publishing raw message to queue (placeholder): %s", payload.get("message_id"))
    raise NotImplementedError("Producer not yet implemented")
