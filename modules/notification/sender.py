"""Lead notification sender via Telegram Saved Messages or Bot API."""

from core.logger import setup_logging

logger = setup_logging(__name__)


async def send_lead_notification(lead_id: int, user_id: int) -> None:
    """
    Deliver a lead alert to the user via Telegram.

    Args:
        lead_id: Database ID of the generated lead.
        user_id: Recipient tenant user ID.
    """
    # TODO: Format lead summary and send via Saved Messages or Bot
    logger.info("Sending lead notification lead_id=%d user_id=%d (placeholder)", lead_id, user_id)
    raise NotImplementedError("Notification sender not yet implemented")
