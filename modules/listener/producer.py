"""Redis queue producer for raw Telegram messages."""

import json
import os
from typing import Any

from dotenv import load_dotenv
import redis.asyncio as aioredis

from core.logger import setup_logging
from modules.processor.worker import celery_app

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


async def publish_raw_message(payload: dict) -> None:
    """
    Dispatch a raw message payload directly to the Celery task queue.
    """
    try:
        # ارسال مستقیم تسک به ورکر Celery
        task = celery_app.send_task("tasks.process_raw_message", args=[payload])

        logger.info(
            "🚀 Task dispatched to Celery! Msg ID: %s | Task ID: %s",
            payload.get("message_id"),
            task.id
        )
    except Exception as e:
        logger.error("❌ Failed to dispatch task to Celery: %s", e, exc_info=True)


async def close_producer() -> None:
    """No-op for backward compatibility."""
    pass