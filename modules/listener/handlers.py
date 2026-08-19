"""Telethon event handlers for incoming Telegram messages."""

from telethon import events
from core.logger import setup_logging
from modules.listener.producer import publish_raw_message

logger = setup_logging(__name__)


async def on_new_message(event: events.NewMessage.Event) -> None:
    """
    Handle a single incoming NewMessage event and forward payload to Redis.
    """
    # فیلتر: فقط پیام‌های دریافتی از گروه‌ها و سوپرگروه‌ها
    if not (event.is_group or event.is_channel):
        return

    chat = await event.get_chat()
    sender = await event.get_sender()

    message_data = {
        "chat_id": event.chat_id,
        "chat_title": getattr(chat, "title", "Unknown Group"),
        "sender_id": event.sender_id,
        "sender_username": getattr(sender, "username", None),
        "message_id": event.id,
        "text": event.raw_text,
        "date": event.date.isoformat() if event.date else None,
    }

    logger.info(
        f"📩 [Group: {message_data['chat_title']}] "
        f"User {message_data['sender_id']}: {message_data['text'][:30]}..."
    )

    # ارسال به صف Redis
    await publish_raw_message(message_data)


def register_handlers(client) -> None:
    """
    Attach NewMessage and related event handlers to the Telethon client.
    """
    client.add_event_handler(on_new_message, events.NewMessage(incoming=True))
    logger.info("Event handlers successfully registered.")