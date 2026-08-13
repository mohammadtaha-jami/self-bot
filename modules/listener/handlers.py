"""Telethon event handlers for incoming Telegram messages."""

from core.logger import setup_logging

logger = setup_logging(__name__)


def register_handlers(client) -> None:
    """
    Attach NewMessage and related event handlers to the Telethon client.

    Args:
        client: Active TelegramClient instance.
    """
    # TODO: Register @client.on(events.NewMessage(...)) handlers
    logger.info("Event handlers registered (placeholder)")


async def on_new_message(event) -> None:
    """
    Handle a single incoming NewMessage event.

    Args:
        event: Telethon NewMessage event payload.
    """
    # TODO: Extract message metadata and forward to producer
    raise NotImplementedError("Message handler not yet implemented")
