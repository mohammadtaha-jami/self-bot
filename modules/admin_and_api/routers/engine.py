"""User engine start/stop/status endpoints."""

import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import get_redis_client
from core.logger import setup_logging
from modules.admin_and_api.deps import get_current_user, get_db
from modules.admin_and_api.routers.keywords import (
    _bundle,
    _custom_keywords,
    _sync_user_keywords_redis,
)
from modules.admin_and_api.routers.licenses import _subscription_status
from modules.admin_and_api.schemas import EngineStatusResponse
from modules.processor.presets import get_user_keywords_cache
from shared.models import TelegramSession, User

logger = setup_logging(__name__)
router = APIRouter(prefix="/engine", tags=["Engine"])


def _user_status_key(user_id: int) -> str:
    return f"user:{user_id}:status"


def _license_valid(user: User) -> bool:
    return _subscription_status(user).is_valid


async def _set_engine_flag(db: AsyncSession, user_id: int, is_engine_active: bool) -> int:
    result = await db.execute(
        update(TelegramSession)
        .where(TelegramSession.user_id == user_id)
        .values(is_engine_active=is_engine_active)
    )
    return int(result.rowcount or 0)


async def _write_status(user_id: int, engine_active: bool, license_valid: bool) -> None:
    redis = get_redis_client()
    await redis.set(
        _user_status_key(user_id),
        json.dumps(
            {"engine_active": engine_active, "license_valid": license_valid},
            ensure_ascii=False,
        ),
    )


async def _read_status(user_id: int) -> dict:
    try:
        redis = get_redis_client()
        raw = await redis.get(_user_status_key(user_id))
        if not raw:
            return {"engine_active": False, "license_valid": False}
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"engine_active": False, "license_valid": False}
        return {
            "engine_active": bool(data.get("engine_active")),
            "license_valid": bool(data.get("license_valid")),
        }
    except Exception:
        logger.exception("Failed to read engine status for user %s", user_id)
        return {"engine_active": False, "license_valid": False}


def _keyword_count(user_id: int) -> int:
    cached = get_user_keywords_cache(user_id)
    if isinstance(cached, list):
        return len(cached)
    if isinstance(cached, dict):
        words = cached.get("final_keywords") or cached.get("keywords") or []
        return len(words) if isinstance(words, list) else 0
    return 0


def _indicator(engine_active: bool, license_valid: bool) -> str:
    if not license_valid:
        return "expired"
    if engine_active:
        return "listening"
    return "stopped"


async def _status_payload(user: User) -> EngineStatusResponse:
    license = _subscription_status(user)
    cached_status = await _read_status(user.id)
    engine_active = bool(cached_status.get("engine_active")) and user.is_active
    return EngineStatusResponse(
        engine_active=engine_active,
        license_valid=license.is_valid,
        keyword_count=_keyword_count(user.id),
        days_remaining=license.days_remaining,
        license_expires_at=license.subscription_end,
        indicator=_indicator(engine_active, license.is_valid),
    )


@router.post("/start", response_model=EngineStatusResponse)
async def start_engine(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EngineStatusResponse:
    """Activate listening for the authenticated user after license and account checks."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="حساب کاربری غیرفعال است.",
        )
    if not _license_valid(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="لایسنس منقضی شده یا تعریف نشده است.",
        )

    sessions = await db.execute(
        select(TelegramSession).where(TelegramSession.user_id == current_user.id)
    )
    if sessions.scalars().first() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="سشن تلگرام برای این کاربر یافت نشد.",
        )

    custom = await _custom_keywords(db, current_user.id)
    bundle = _bundle(current_user, custom)
    await _sync_user_keywords_redis(current_user, bundle)
    await _set_engine_flag(db, current_user.id, True)
    await _write_status(current_user.id, True, True)
    return await _status_payload(current_user)


@router.post("/stop", response_model=EngineStatusResponse)
async def stop_engine(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EngineStatusResponse:
    """Stop listening and mark sessions as engine-inactive."""
    license_valid = _license_valid(current_user)
    await _set_engine_flag(db, current_user.id, False)
    await _write_status(current_user.id, False, license_valid)
    return await _status_payload(current_user)


@router.get("/status", response_model=EngineStatusResponse)
async def engine_status(
    current_user: User = Depends(get_current_user),
) -> EngineStatusResponse:
    """Return live engine flag, cached keyword count, and remaining license days."""
    return await _status_payload(current_user)
