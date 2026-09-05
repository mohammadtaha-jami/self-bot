"""Lead notification sender via Telegram Bot API (sync, Celery-safe)."""

from __future__ import annotations

import httpx
from sqlalchemy import select

from core.config import get_settings
from core.database import get_session_factory, run_async_isolated
from core.logger import setup_logging
from shared.models import User

logger = setup_logging(__name__)


async def _deactivate_notifier(user_id: int) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return
        user.is_notifier_active = False
        await db.commit()
        logger.info("Notifier deactivated for user_id=%s (bot blocked)", user_id)


def _proxy_url() -> str | None:
    settings = get_settings()
    if not settings.use_proxy:
        return None
    return f"{settings.proxy_type}://{settings.proxy_host}:{settings.proxy_port}"


def send_lead_notification(
    chat_id: int,
    formatted_text: str,
    reply_markup: dict,
    user_id: int | None = None,
) -> bool:
    """
    Deliver a lead alert to the user's notifier bot chat via Bot API.

    On Telegram error 403 (user blocked the bot), sets is_notifier_active=False.
    """
    settings = get_settings()
    token = settings.resolved_bot_token
    if not token:
        logger.error("BOT_TOKEN / NOTIFIER_BOT_TOKEN is not configured.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body: dict = {
        "chat_id": chat_id,
        "text": formatted_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": False,
    }
    if reply_markup.get("inline_keyboard"):
        body["reply_markup"] = reply_markup

    proxy = _proxy_url()
    try:
        with httpx.Client(timeout=30.0, proxy=proxy) as client:
            response = client.post(url, json=body)
    except ImportError:
        logger.exception(
            "SOCKS proxy needs httpx[socks]. Install with: pip install 'httpx[socks]'"
        )
        return False
    except httpx.HTTPError as exc:
        logger.error("Notifier HTTP request failed: %s", exc, exc_info=True)
        return False

    try:
        data = response.json()
    except ValueError:
        logger.error(
            "Notifier API returned non-JSON response (status=%s)",
            response.status_code,
        )
        return False

    if data.get("ok"):
        logger.info("Lead notification sent to chat_id=%s (user_id=%s)", chat_id, user_id)
        return True

    error_code = data.get("error_code")
    description = data.get("description", "unknown error")
    logger.warning(
        "Notifier API error chat_id=%s user_id=%s code=%s desc=%s",
        chat_id,
        user_id,
        error_code,
        description,
    )

    if error_code == 403 and user_id is not None:
        try:
            run_async_isolated(_deactivate_notifier(user_id))
        except Exception:
            logger.exception("Failed to deactivate notifier for user_id=%s", user_id)

    return False
