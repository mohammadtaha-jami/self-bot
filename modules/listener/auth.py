"""
Telegram Authentication and StringSession Management Module.
Handles initial interactive login and session reloading with optional Proxy support.
"""

import os
from collections.abc import Awaitable
from typing import Any

import socks
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.tl.types import User

from core.logger import setup_logging

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
    """
    Disconnect Telethon client safely.

    Telethon's disconnect() returns a coroutine when the event loop is running,
    but type stubs declare it as None — this helper satisfies both runtime and Pyright.
    """
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


async def create_string_session(phone: str) -> str:
    """
    Authenticate interactively with Telegram using phone number & SMS code.
    """
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
    """
    Build and connect a Telethon client from an existing StringSession.
    """
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
            if not isinstance(me, User):
                raise RuntimeError(f"Unexpected entity type from get_me(): {type(me)}")
            username = f"@{me.username}" if me.username else "(no username)"
            print(f"🎉 Successfully logged in as: {me.first_name} {username}")
        finally:
            await _disconnect_client(active_client)

    asyncio.run(main())