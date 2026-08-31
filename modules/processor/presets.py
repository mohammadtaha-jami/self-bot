"""Dynamic loader for business type keyword presets with Redis caching layer."""

import json
from pathlib import Path
from typing import List, Optional, Union
import redis

from core.logger import setup_logging

logger = setup_logging(__name__)

PRESETS_DIR = Path("config/presets")

# اتصال به Redis (تنظیمات را متناسب با env پروژه ست کنید)
redis_client = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True,
    protocol=2,
)

CACHE_TTL_SECONDS = 86400  # مدت زمان اعتبارسنجی کش (۲۴ ساعت)


def _normalize_business_types(
    business_types: Union[str, List[str], None]
) -> List[str]:
    """تبدیل ورودی‌های مختلف به لیست استاندارد."""
    if not business_types:
        return []

    if isinstance(business_types, str):
        return [
            t.strip()
            for t in business_types.replace(",", " ").split()
            if t.strip()
        ]

    if isinstance(business_types, list):
        return [str(t).strip() for t in business_types if str(t).strip()]

    return []


def get_rules_for_single_preset(b_type: str) -> dict:
    """
    دریافت کلمات کلیدی یک دسته‌بندی با اولویت Redis Cache و پشتیبانی از Fallback به Disk.
    """
    cache_key = f"preset:keywords:{b_type}"

    # ۱. تلاش برای خواندن از Redis
    try:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            logger.info("Cache HIT for business_type: %s", b_type)
            return json.loads(cached_data)
    except Exception as e:
        logger.error("Redis Cache Read Error for '%s': %s", b_type, e)

    # ۲. در صورت عدم وجود در Redis خواندن از فایل JSON
    file_path = PRESETS_DIR / f"{b_type}.json"
    if not file_path.exists():
        logger.warning("Preset file for '%s' not found at %s", b_type, file_path)
        return {"keywords": [], "negative_keywords": []}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            rules = {
                "keywords": data.get("keywords", []),
                "negative_keywords": data.get("negative_keywords", []),
            }

        # ۳. ذخیره در Redis برای استفاده‌های بعدی
        try:
            redis_client.setex(
                cache_key,
                CACHE_TTL_SECONDS,
                json.dumps(rules, ensure_ascii=False)
            )
            logger.info("Cached preset rules in Redis for: %s", b_type)
        except Exception as e:
            logger.error("Redis Cache Write Error for '%s': %s", b_type, e)

        return rules

    except Exception as e:
        logger.error("Error loading preset file %s: %s", file_path, e, exc_info=True)
        return {"keywords": [], "negative_keywords": []}


def get_rules_for_business_types(
    business_types: Union[str, List[str], None]
) -> dict:
    """بارگذاری و ترکیب کلمات کلیدی برای یک یا چند دسته‌بندی شغلی از کش."""
    types_list = _normalize_business_types(business_types)

    if not types_list:
        return {"keywords": [], "negative_keywords": []}

    all_keywords = []
    all_negative_keywords = []

    for b_type in types_list:
        rules = get_rules_for_single_preset(b_type)
        all_keywords.extend(rules.get("keywords", []))
        all_negative_keywords.extend(rules.get("negative_keywords", []))

    # حذف کلمات تکراری با حفظ ترتیب
    unique_keywords = list(dict.fromkeys(all_keywords))
    unique_negative_keywords = list(dict.fromkeys(all_negative_keywords))

    return {
        "keywords": unique_keywords,
        "negative_keywords": unique_negative_keywords,
    }


# --- توابع اختصاصی کش برای هر کاربر (User-Specific Caching) ---

def user_keywords_cache_key(user_id: Union[int, str]) -> str:
    return f"user:{user_id}:keywords"


def user_status_cache_key(user_id: Union[int, str]) -> str:
    return f"user:{user_id}:status"


def get_user_engine_status(user_id: Union[int, str]) -> dict:
    """Read engine_active / license_valid flags from Redis."""
    cache_key = user_status_cache_key(user_id)
    default = {"engine_active": False, "license_valid": False}
    try:
        data = redis_client.get(cache_key)
        if not data:
            return default
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            return default
        return {
            "engine_active": bool(parsed.get("engine_active")),
            "license_valid": bool(parsed.get("license_valid")),
        }
    except Exception as e:
        logger.error("Error reading engine status for user %s: %s", user_id, e)
        return default


def get_user_keywords_cache(user_id: Union[int, str]) -> Optional[Union[dict, list]]:
    """دریافت کلمات کلیدی اختصاصی یک کاربر از کش Redis."""
    keys = [user_keywords_cache_key(user_id), f"user:keywords:{user_id}"]
    try:
        for cache_key in keys:
            data = redis_client.get(cache_key)
            if data:
                return json.loads(data)
        return None
    except Exception as e:
        logger.error("Error reading user cache for user %s: %s", user_id, e)
        return None


def set_user_keywords_cache(
    user_id: Union[int, str],
    keywords: List[str],
    negative_keywords: List[str] | None = None,
    ttl: int = CACHE_TTL_SECONDS,
    extra: Optional[dict] = None,
) -> bool:
    """ذخیره یا به‌روزرسانی کلمات کلیدی ادغام‌شده کاربر در Redis."""
    cache_key = user_keywords_cache_key(user_id)
    payload = {
        "keywords": keywords,
        "final_keywords": keywords,
        "negative_keywords": negative_keywords or [],
    }
    if extra:
        payload.update(extra)
    try:
        redis_client.set(cache_key, json.dumps(payload, ensure_ascii=False))
        if ttl:
            redis_client.expire(cache_key, ttl)
        logger.info("Updated keyword cache for user: %s", user_id)
        return True
    except Exception as e:
        logger.error("Error setting user cache for user %s: %s", user_id, e)
        return False


def invalidate_preset_cache(b_type: str) -> None:
    """ابطال کش یک دسته‌بندی (مثلاً پس از ویرایش فایل JSON)."""
    cache_key = f"preset:keywords:{b_type}"
    try:
        redis_client.delete(cache_key)
        logger.info("Invalidated cache for preset: %s", b_type)
    except Exception as e:
        logger.error("Error invalidating cache for %s: %s", b_type, e)