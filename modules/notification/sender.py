"""Lead notification sender via Telegram Saved Messages or Bot API."""

from telethon import TelegramClient
from telethon.sessions import StringSession

from core.logger import setup_logging

logger = setup_logging(__name__)


async def send_lead_notification(
    api_id: int,
    api_hash: str,
    session_string: str,
    message_text: str,
    lead_id: int | None = None,
    user_id: int | None = None,
) -> bool:
    """
    Deliver a lead alert to the user's Saved Messages via Telethon.

    Args:
        api_id: Telegram API ID
        api_hash: Telegram API Hash
        session_string: Active user StringSession
        message_text: Formatted markdown text
        lead_id: Optional Database ID (for future logging)
        user_id: Optional Recipient user ID (for future logging)
    """
    if not all([api_id, api_hash, session_string]):
        logger.error("Missing Telegram session details for sending notification.")
        return False

    try:
        async with TelegramClient(
            StringSession(session_string), api_id, api_hash
        ) as client:
            # ارسال پیام به Saved Messages (حساب me)
            await client.send_message(
                "me", message_text, parse_mode="md", link_preview=False
            )
            logger.info(
                "Lead notification delivered to Saved Messages. (lead_id=%s, user_id=%s)",
                lead_id,
                user_id,
            )
            return True
    except Exception as e:
        logger.error("Failed to send lead notification: %s", e, exc_info=True)
        return False