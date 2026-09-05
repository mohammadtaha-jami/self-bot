"""Aiogram 3 notifier bot: /start deep-link binds telegram_chat_id to a dashboard user."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy import select

from core.cache import bot_link_key, close_redis, get_redis_client
from core.config import get_settings
from core.database import get_engine, get_session_factory
from core.logger import setup_logging
from shared.models import User

logger = setup_logging(__name__)

settings = get_settings()
router = Router()
dp = Dispatcher()
dp.include_router(router)

MSG_NO_TOKEN = (
    "سلام! برای فعال‌سازی سیستم اطلاع‌رسانی، لطفاً از طریق دکمه «اتصال به ربات» "
    "در داشبورد وب‌سایت وارد شوید."
)
MSG_INVALID_TOKEN = (
    "❌ لینک اتصال منقضی شده یا نامعتبر است. لطفاً از داشبورد مجدداً دکمه اتصال را بزنید."
)
MSG_SUCCESS = (
    "✅ **حساب شما با موفقیت متصل شد!**\n"
    " از این پس تمامی لیدها و موقعیت‌های کاری شناسا‌یی‌شده به‌صورت لحظه‌ای به همین چت ارسال خواهند شد."
)
MSG_SERVER_ERROR = (
    "⚠️ خطا در برقراری ارتباط با سرور. لطفاً چند لحظه دیگر دوباره تلاش کنید."
)


def _build_bot() -> Bot:
    token = settings.resolved_bot_token
    if not token:
        raise RuntimeError("BOT_TOKEN / NOTIFIER_BOT_TOKEN is not configured.")

    session: AiohttpSession | None = None
    if settings.use_proxy:
        proxy_url = f"{settings.proxy_type}://{settings.proxy_host}:{settings.proxy_port}"
        logger.info("Notifier bot using proxy %s", proxy_url)
        session = AiohttpSession(proxy=proxy_url)

    return Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )


async def _load_user_id_from_token(token: str) -> int | None:
    redis_client = get_redis_client()
    raw = await redis_client.get(bot_link_key(token))
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("bot_link token stored a non-integer user id")
        return None


async def _activate_notifier(user_id: int, chat_id: int) -> bool:
    session_factory = get_session_factory()
    async with session_factory() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            return False
        user.telegram_chat_id = chat_id
        user.is_notifier_active = True
        await db.commit()
        return True


async def _consume_token(token: str) -> None:
    redis_client = get_redis_client()
    await redis_client.delete(bot_link_key(token))


@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject) -> None:
    """Deep-link /start: validate Redis token and persist telegram_chat_id."""
    token = (command.args or "").strip()
    if not token:
        await message.answer(MSG_NO_TOKEN, parse_mode=None)
        return

    try:
        user_id = await _load_user_id_from_token(token)
    except Exception:
        logger.exception("Redis lookup failed for notifier deep-link token")
        await message.answer(MSG_SERVER_ERROR, parse_mode=None)
        return

    if user_id is None:
        await message.answer(MSG_INVALID_TOKEN, parse_mode=None)
        return

    try:
        updated = await _activate_notifier(user_id, message.chat.id)
    except Exception:
        logger.exception("Database update failed while linking notifier user_id=%s", user_id)
        await message.answer(MSG_SERVER_ERROR, parse_mode=None)
        return

    if not updated:
        await message.answer(MSG_INVALID_TOKEN, parse_mode=None)
        return

    try:
        await _consume_token(token)
    except Exception:
        logger.exception("Failed to delete used bot_link token (user already linked)")

    await message.answer(MSG_SUCCESS)


async def main() -> None:
    """Run long-polling until cancelled."""
    username = settings.resolved_bot_username
    if username:
        logger.info("Starting notifier bot @%s", username)
    else:
        logger.info("Starting notifier bot (BOT_USERNAME not set)")

    bot = _build_bot()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await close_redis()
        await get_engine().dispose()


if __name__ == "__main__":
    logging.getLogger("aiogram").setLevel(logging.INFO)
    asyncio.run(main())
