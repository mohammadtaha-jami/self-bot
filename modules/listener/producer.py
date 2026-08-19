"""Redis queue producer for raw Telegram messages."""

import json
import os
from typing import Any

from dotenv import load_dotenv
import redis.asyncio as aioredis

from core.logger import setup_logging

logger = setup_logging(__name__)
load_dotenv()

# تنظیمات Redis از فایل .env با مقادیر پیش‌فرض
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
MESSAGE_QUEUE_KEY = os.getenv("REDIS_QUEUE_NAME", "queue:raw_messages")

# کلاینت سراسری برای مدیریت اتصال (Singleton)
_redis_client: aioredis.Redis | None = None


async def get_redis_client() -> aioredis.Redis:
    """Get or initialize the async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=0,
            decode_responses=True,
            protocol=2,  # برای سازگاری کامل با نسخه‌های مختلف Redis در ویندوز
        )
    return _redis_client


async def publish_raw_message(payload: dict[str, Any]) -> None:
    """
    Push a serialized raw message onto the Redis processing queue.

    Args:
        payload: Dict containing message_id, source_id, text, metadata, etc.
    """
    try:
        client = await get_redis_client()
        serialized_payload = json.dumps(payload, ensure_ascii=False)
        
        # اضافه کردن پیام به انتهای صف
        await client.rpush(MESSAGE_QUEUE_KEY, serialized_payload)
        
        logger.debug(
            "Published raw message to queue [%s]: %s", 
            MESSAGE_QUEUE_KEY, 
            payload.get("message_id")
        )
    except Exception as e:
        logger.error("❌ Failed to publish raw message to Redis queue: %s", e)


async def close_producer() -> None:
    """Close the Redis connection safely when shutting down."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("🔌 Redis producer connection closed.")