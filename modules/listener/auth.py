"""
Telegram Authentication and StringSession Management Module.
Handles initial interactive login and session reloading from stored database tokens.
"""

import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from core.logger import setup_logging

logger = setup_logging(__name__)
load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")


def _validate_credentials():
    """Ensure API credentials exist in environment variables."""
    if not API_ID or not API_HASH:
        logger.error("TELEGRAM_API_ID or TELEGRAM_API_HASH is not configured in .env!")
        raise ValueError("TELEGRAM_API_ID or TELEGRAM_API_HASH is missing from environment variables.")


async def create_string_session(phone: str) -> str:
    """
    Authenticate interactively with Telegram using phone number & SMS code.
    Used ONCE per account onboarding to generate a persistent session token.

    Args:
        phone: E.164 phone number for Telegram login (e.g., +989123456789).

    Returns:
        Serialized Telethon StringSession string for database storage.
    """
    _validate_credentials()
    logger.info(f"Initiating interactive authentication for phone: {phone}")

    # ساخت کلاینت موقت جهت دریافت session
    client = TelegramClient(StringSession(), int(API_ID), API_HASH)
    
    # شروع لاگین تعاملی (دریافت کد SMS در ترمینال)
    await client.start(phone=phone)
    
    session_string = client.session.save()
    logger.info(f"Successfully generated StringSession for {phone}")
    
    await client.disconnect()
    return session_string


async def load_client(session_string: str) -> TelegramClient:
    """
    Build and connect a Telethon client from an existing database StringSession.
    Used continuously by the listener service on startup without SMS intervention.

    Args:
        session_string: Serialized session token retrieved from database.

    Returns:
        Connected and authenticated TelegramClient instance.
    """
    _validate_credentials()
    logger.info("Initializing TelegramClient from provided StringSession...")

    client = TelegramClient(StringSession(session_string), int(API_ID), API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        logger.error("Failed to authorize client with provided StringSession. Token might be revoked.")
        raise PermissionError("StringSession is invalid or expired.")

    logger.info("TelegramClient successfully connected and authorized.")
    return client


if __name__ == "__main__":
    import asyncio

    async def main():
        print("=== Telegram Session Management Utility ===")
        user_phone = input("📱 Enter Telegram phone number (+98...): ").strip()
        
        # ۱. ساخت سشن جدید
        token = await create_string_session(user_phone)
        print(f"\n✅ Generated Token:\n{token}\n")
        
        # ۲. تست تابع load_client برای اطمینان از سلامت سشن ساخته‌شده
        print("🔄 Testing load_client with generated token...")
        active_client = await load_client(token)
        me = await active_client.get_me()
        print(f"🎉 Successfully logged in as: {me.first_name} (@{me.username})")
        await active_client.disconnect()

    asyncio.run(main())