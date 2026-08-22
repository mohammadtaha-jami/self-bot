"""Telethon client startup entry point for the listener service."""

import asyncio
from sqlalchemy import select

from core.database import get_session_factory
from core.logger import setup_logging
from modules.listener.auth import load_client, _disconnect_client
from modules.listener.handlers import register_handlers
from modules.listener.producer import close_producer
from shared.models import TelegramSession

logger = setup_logging(__name__)


async def main() -> None:
    """Initialize Telethon client, register handlers, and start listening."""
    logger.info("Listener service starting...")

    session_factory = get_session_factory()

    # ۱. دریافت سشن فعال از دیتابیس
    async with session_factory() as db:
        stmt = select(TelegramSession).where(TelegramSession.is_active == True)
        result = await db.execute(stmt)
        session_record = result.scalars().first()

    if not session_record:
        logger.error("❌ No active TelegramSession found in database!")
        return

    logger.info(f"🔑 Loading active session for phone: {session_record.phone_number}")

    # ۲. راه‌اندازی کلاینت
    client = await load_client(session_record.session_string)

    try:
        # ۳. ثبت هندرها
        register_handlers(client, session_record.session_string)

        logger.info("🚀 Listener service is running and listening for group messages...")
        await client.run_until_disconnected()  # type: ignore
    finally:
        await _disconnect_client(client)
        await close_producer()


if __name__ == "__main__":
    asyncio.run(main())