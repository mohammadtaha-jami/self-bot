"""
Telegram Authentication and StringSession Management Module.
Handles initial interactive login, session reloading with optional Proxy support,
and persisting session details into PostgreSQL database.
"""

import os
from collections.abc import Awaitable
from typing import Any

import socks
from dotenv import load_dotenv
from sqlalchemy import select
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.tl.types import User as TelethonUser

from core.database import get_session_factory
from core.logger import setup_logging
from shared.models import TelegramSession, User as DBUser

logger = setup_logging(__name__)
load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

# دریافت تنظیمات پروکسی از فایل .env
USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"
PROXY_TYPE = os.getenv("PROXY_TYPE", "socks5").lower()
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("PROXY_PORT", 10808))


def _get_proxy_config():
    """Build proxy tuple for Telethon if enabled in .env."""
    if not USE_PROXY:
        return None

    p_type = socks.SOCKS5 if PROXY_TYPE == "socks5" else socks.HTTP
    logger.info(f"🌐 Connecting via Proxy: {PROXY_TYPE}://{PROXY_HOST}:{PROXY_PORT}")
    return (p_type, PROXY_HOST, PROXY_PORT)


def _get_credentials() -> tuple[int, str]:
    """Return validated Telegram API credentials from environment."""
    if not API_ID or not API_HASH:
        logger.error("TELEGRAM_API_ID or TELEGRAM_API_HASH is missing in .env!")
        raise ValueError("TELEGRAM_API_ID or TELEGRAM_API_HASH is not set in .env file.")
    return int(API_ID), API_HASH


def _build_client(session: StringSession | None = None) -> TelegramClient:
    """Create a TelegramClient with optional proxy configuration."""
    api_id, api_hash = _get_credentials()
    client_kwargs: dict[str, Any] = {}
    proxy = _get_proxy_config()
    if proxy is not None:
        client_kwargs["proxy"] = proxy
    return TelegramClient(session or StringSession(), api_id, api_hash, **client_kwargs)


async def _disconnect_client(client: TelegramClient) -> None:
    """Disconnect Telethon client safely."""
    result = client.disconnect()
    if isinstance(result, Awaitable):
        await result


async def _interactive_sign_in(client: TelegramClient, phone: str) -> None:
    """Complete phone + SMS (and optional 2FA) login flow."""
    if await client.is_user_authorized():
        return

    await client.send_code_request(phone)
    code = input("Enter the Telegram login code: ").strip()
    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        password = input("Enter your 2FA password: ").strip()
        await client.sign_in(password=password)


async def save_session_to_db(
    phone: str,
    session_str: str,
    user_id: int | None = None,
    telegram_user: TelethonUser | None = None,
) -> TelegramSession:
    """
    Saves or updates the Telegram StringSession and User in PostgreSQL.
    - Extracts telegram_id, username, and full_name from TelethonUser.
    - Creates or updates DBUser in users table.
    - Persists session in telegram_sessions table.
    """
    session_factory = get_session_factory()

    async with session_factory() as db:
        # ۱. استخراج مشخصات از TelethonUser
        tg_id = telegram_user.id if telegram_user else None
        username = telegram_user.username if telegram_user else None
        full_name = None
        if telegram_user:
            first_name = telegram_user.first_name or ""
            last_name = telegram_user.last_name or ""
            full_name = f"{first_name} {last_name}".strip() or None

        # ۲. جستجو یا ساخت کاربر در جدول users
        target_user = None

        if user_id is not None:
            stmt_u = select(DBUser).where(DBUser.id == user_id)
            res_u = await db.execute(stmt_u)
            target_user = res_u.scalars().first()
        elif tg_id is not None:
            stmt_u = select(DBUser).where(DBUser.telegram_id == tg_id)
            res_u = await db.execute(stmt_u)
            target_user = res_u.scalars().first()

        if target_user:
            # به‌روزرسانی اطلاعات کاربر موجود
            if tg_id is not None:
                target_user.telegram_id = tg_id
            if username is not None:
                target_user.username = username
            if full_name is not None:
                target_user.full_name = full_name
            logger.info(f"👤 Updated DB User ID {target_user.id} ({full_name})")
        else:
            # ساخت کاربر جدید در جدول users
            target_user = DBUser(
                telegram_id=tg_id,
                username=username,
                full_name=full_name,
                is_active=True,
            )
            db.add(target_user)
            await db.flush()
            logger.info(f"👤 Created new DB User ID {target_user.id} ({full_name})")

        # ۳. ذخیره یا به‌روزرسانی سشن در جدول telegram_sessions
        stmt_s = select(TelegramSession).where(TelegramSession.phone_number == phone)
        res_s = await db.execute(stmt_s)
        account = res_s.scalars().first()

        if account:
            account.session_string = session_str
            account.user_id = target_user.id
            account.is_active = True
            logger.info(f"✅ Updated existing Telegram session in DB for: {phone}")
        else:
            account = TelegramSession(
                user_id=target_user.id,
                phone_number=phone,
                session_string=session_str,
                is_active=True,
            )
            db.add(account)
            logger.info(f"✅ Saved new Telegram session to DB for: {phone}")

        await db.commit()
        await db.refresh(account)
        return account


async def create_string_session(phone: str) -> str:
    """Authenticate interactively with Telegram using phone number & SMS code."""
    logger.info(f"Initiating interactive authentication for phone: {phone}")

    client = _build_client()
    await client.connect()
    try:
        await _interactive_sign_in(client, phone)

        if not isinstance(client.session, StringSession):
            raise RuntimeError("Expected StringSession after authentication.")

        session_string = client.session.save()
        logger.info(f"Successfully generated StringSession for {phone}")
        return session_string
    finally:
        await _disconnect_client(client)


async def load_client(session_string: str) -> TelegramClient:
    """Build and connect a Telethon client from an existing StringSession."""
    logger.info("Initializing TelegramClient from provided StringSession...")

    client = _build_client(StringSession(session_string))
    await client.connect()

    if not await client.is_user_authorized():
        await _disconnect_client(client)
        logger.error("Failed to authorize client with provided StringSession.")
        raise PermissionError("StringSession is invalid or expired.")

    logger.info("TelegramClient successfully connected and authorized.")
    return client


if __name__ == "__main__":
    import asyncio

    async def main():
        print("=== Telegram Session Management Utility ===")
        user_phone = input("📱 Enter Telegram phone number (+98...): ").strip()

        token = await create_string_session(user_phone)
        print(f"\n✅ Generated Token:\n{token}\n")

        print("🔄 Testing load_client with generated token...")
        active_client = await load_client(token)
        try:
            me = await active_client.get_me()
            if not isinstance(me, TelethonUser):
                raise RuntimeError(f"Unexpected entity type from get_me(): {type(me)}")

            username = f"@{me.username}" if me.username else "(no username)"
            print(f"🎉 Successfully logged in as: {me.first_name} {username}")

            # ذخیره ساختاریافته و واقعی در دیتابیس
            print("💾 Saving session to database...")
            session_record = await save_session_to_db(
                phone=user_phone,
                session_str=token,
                telegram_user=me,
            )
            print(
                f"✅ Session successfully saved! (User DB ID: {session_record.user_id}, Session ID: {session_record.id})"
            )

        finally:
            await _disconnect_client(active_client)

    asyncio.run(main())