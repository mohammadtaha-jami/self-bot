"""Notifier bot deep-link and connection-status endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from core.cache import BOT_LINK_TTL_SECONDS, bot_link_key, get_redis_client
from core.config import get_settings
from modules.admin_and_api.deps import get_current_user
from modules.admin_and_api.schemas import GenerateLinkResponse, NotificationStatusResponse
from shared.models import User

router = APIRouter()


def _normalized_bot_username() -> str:
    raw = get_settings().resolved_bot_username
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="BOT_USERNAME is not configured.",
        )
    return raw


@router.post("/generate-link", response_model=GenerateLinkResponse)
async def generate_notification_link(
    current_user: User = Depends(get_current_user),
) -> GenerateLinkResponse:
    """Issue a 5-minute Telegram deep link that binds this user to the notifier bot."""
    bot_username = _normalized_bot_username()
    token = str(uuid.uuid4())
    redis_client = get_redis_client()
    await redis_client.setex(
        bot_link_key(token),
        BOT_LINK_TTL_SECONDS,
        str(current_user.id),
    )
    link = f"https://t.me/{bot_username}?start={token}"
    return GenerateLinkResponse(link=link, expires_in=BOT_LINK_TTL_SECONDS)


@router.get("/status", response_model=NotificationStatusResponse)
async def get_notification_status(
    current_user: User = Depends(get_current_user),
) -> NotificationStatusResponse:
    """Return notifier connection flags from the authenticated user row."""
    return NotificationStatusResponse(
        is_notifier_active=bool(current_user.is_notifier_active),
        telegram_chat_id=current_user.telegram_chat_id,
    )
