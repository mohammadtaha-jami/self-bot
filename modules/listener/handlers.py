"""Telethon event handlers for incoming Telegram messages."""

from telethon import events
from core.logger import setup_logging
from modules.listener.producer import publish_raw_message

logger = setup_logging(__name__)


async def on_new_message(event: events.NewMessage.Event, session_string: str) -> None:
    """Handle a single incoming NewMessage event and forward payload to Celery."""
    if not (event.is_group or event.is_channel):
        return

    chat = await event.get_chat()
    sender = await event.get_sender()

    user_business_type = "programmer, web_designer" 

    message_data = {
        "chat_id": event.chat_id,
        "chat_title": getattr(chat, "title", "Unknown Group"),
        "sender_id": event.sender_id,
        "sender_username": getattr(sender, "username", None),
        "message_id": event.id,
        "text": event.raw_text,
        "business_type": user_business_type,
        "date": event.date.isoformat() if event.date else None,
        "session_string": session_string,  # 👈 اضافه شد
    }

    logger.info(
        f"📩 [Group: {message_data['chat_title']}] "
        f"User {message_data['sender_id']}: {message_data['text'][:30]}..."
    )

    await publish_raw_message(message_data)


def register_handlers(client, session_string: str) -> None:
    """Register event handlers with attached session info."""
    async def handler(event):
        await on_new_message(event, session_string)

    client.add_event_handler(handler, events.NewMessage(incoming=True))
    logger.info("Event handlers successfully registered.")