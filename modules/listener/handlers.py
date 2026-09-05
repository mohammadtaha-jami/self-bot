"""Telethon event handlers for incoming Telegram messages."""

from telethon import events

from core.cache import should_ingest_message
from core.logger import setup_logging
from modules.listener.producer import publish_raw_message

logger = setup_logging(__name__)


async def on_new_message(
    event: events.NewMessage.Event,
    session_string: str,
    user_id: int | None = None,
    business_type: str | None = None,
) -> None:
    """Handle a single incoming NewMessage event and forward payload to Celery."""
    if not should_ingest_message(
        user_id,
        event.chat_id,
        is_group=bool(event.is_group),
        is_channel=bool(event.is_channel),
        is_private=bool(event.is_private),
    ):
        return

    chat = await event.get_chat()
    sender = await event.get_sender()

    message_data = {
        "user_id": user_id,
        "chat_id": event.chat_id,
        "chat_title": getattr(chat, "title", None)
        or getattr(chat, "first_name", None)
        or "Unknown",
        "sender_id": event.sender_id,
        "sender_username": getattr(sender, "username", None),
        "message_id": event.id,
        "text": event.raw_text,
        "business_type": business_type,
        "date": event.date.isoformat() if event.date else None,
        "session_string": session_string,
    }

    logger.info(
        f"📩 [Group: {message_data['chat_title']}] "
        f"User {message_data['sender_id']}: {message_data['text'][:30]}..."
    )

    await publish_raw_message(message_data)


def register_handlers(
    client,
    session_string: str,
    user_id: int | None = None,
    business_type: str | None = None,
) -> None:
    """Register event handlers with attached session and owner info."""

    async def handler(event):
        await on_new_message(
            event,
            session_string,
            user_id=user_id,
            business_type=business_type,
        )

    client.add_event_handler(handler, events.NewMessage(incoming=True))
    logger.info("Event handlers successfully registered.")
