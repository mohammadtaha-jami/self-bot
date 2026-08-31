"""Engine start/stop pipeline orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import (
    append_pipeline_log,
    listener_heartbeat_key,
    processor_heartbeat_key,
    publish_engine_control,
    read_user_keyword_count,
    service_heartbeat_age_seconds,
    sync_user_keywords_payload,
    sync_user_status,
)
from core.logger import setup_logging
from modules.admin_and_api.routers.keywords import (
    _bundle,
    _custom_keywords,
    build_keywords_redis_payload,
)
from modules.admin_and_api.routers.licenses import _subscription_status
from modules.processor.worker import celery_app
from shared.models import TelegramSession, User

logger = setup_logging(__name__)

HEARTBEAT_MAX_AGE_SECONDS = 45


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _step(
    step_id: str,
    title: str,
    description: str,
    status: str,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "description": description,
        "status": status,
        "detail": detail,
        "timestamp": _utc_now_iso(),
    }


def _log_step(user_id: int, step: dict[str, Any]) -> None:
    append_pipeline_log(user_id, step)
    logger.info(
        "Engine pipeline user=%s step=%s status=%s detail=%s",
        user_id,
        step["id"],
        step["status"],
        step.get("detail"),
    )


def _check_celery_workers() -> tuple[bool, str]:
    try:
        inspector = celery_app.control.inspect(timeout=2.0)
        ping = inspector.ping() if inspector else None
        if ping:
            workers = ", ".join(sorted(ping.keys()))
            return True, f"ورکرهای فعال: {workers}"
        return False, "هیچ ورکر Celery پاسخ نداد. processor worker را اجرا کنید."
    except Exception as exc:
        logger.exception("Celery inspect failed")
        return False, f"بررسی Celery ناموفق بود: {exc}"


def _check_listener_service() -> tuple[bool, str]:
    age = service_heartbeat_age_seconds(listener_heartbeat_key())
    if age is None:
        return False, "سرویس Listener در حال اجرا نیست. `python -m modules.listener.app` را start کنید."
    if age > HEARTBEAT_MAX_AGE_SECONDS:
        return False, f"Heartbeat Listener قدیمی است ({int(age)}s). سرویس را restart کنید."
    return True, f"Listener فعال است (heartbeat {int(age)}s پیش)"


def _check_processor_service() -> tuple[bool, str]:
    age = service_heartbeat_age_seconds(processor_heartbeat_key())
    celery_ok, celery_detail = _check_celery_workers()
    if age is not None and age <= HEARTBEAT_MAX_AGE_SECONDS:
        return True, f"Processor heartbeat OK ({int(age)}s پیش). {celery_detail}"
    if celery_ok:
        return True, celery_detail
    if age is None:
        return False, f"Processor heartbeat یافت نشد. {celery_detail}"
    return False, f"Heartbeat Processor قدیمی است ({int(age)}s). {celery_detail}"


async def _set_engine_flag(db: AsyncSession, user_id: int, is_engine_active: bool) -> int:
    result = await db.execute(
        update(TelegramSession)
        .where(TelegramSession.user_id == user_id)
        .values(is_engine_active=is_engine_active)
    )
    return int(result.rowcount or 0)


async def run_start_pipeline(user: User, db: AsyncSession) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []

    if not user.is_active:
        step = _step(
            "validate_account",
            "بررسی حساب کاربری",
            "اعتبارسنجی فعال بودن اکانت",
            "error",
            "حساب کاربری غیرفعال است.",
        )
        steps.append(step)
        _log_step(user.id, step)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=step["detail"])

    step = _step(
        "validate_account",
        "بررسی حساب کاربری",
        "اعتبارسنجی فعال بودن اکانت",
        "success",
        "اکانت فعال است.",
    )
    steps.append(step)
    _log_step(user.id, step)

    license = _subscription_status(user)
    if not license.is_valid:
        step = _step(
            "validate_license",
            "بررسی لایسنس",
            "اعتبارسنجی تاریخ انقضای اشتراک",
            "error",
            "لایسنس منقضی شده یا تعریف نشده است.",
        )
        steps.append(step)
        _log_step(user.id, step)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=step["detail"])

    step = _step(
        "validate_license",
        "بررسی لایسنس",
        "اعتبارسنجی تاریخ انقضای اشتراک",
        "success",
        f"{license.days_remaining} روز تا انقضا باقی مانده.",
    )
    steps.append(step)
    _log_step(user.id, step)

    session_result = await db.execute(
        select(TelegramSession).where(TelegramSession.user_id == user.id)
    )
    session = session_result.scalars().first()
    if session is None:
        step = _step(
            "validate_session",
            "بررسی سشن تلگرام",
            "وجود StringSession متصل به کاربر",
            "error",
            "سشن تلگرام برای این کاربر یافت نشد.",
        )
        steps.append(step)
        _log_step(user.id, step)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=step["detail"])

    if not session.is_active:
        step = _step(
            "validate_session",
            "بررسی سشن تلگرام",
            "وجود StringSession متصل به کاربر",
            "error",
            "سشن تلگرام غیرفعال است. با ادمین تماس بگیرید.",
        )
        steps.append(step)
        _log_step(user.id, step)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=step["detail"])

    step = _step(
        "validate_session",
        "بررسی سشن تلگرام",
        "وجود StringSession متصل به کاربر",
        "success",
        f"سشن {session.phone_number} آماده شنود است.",
    )
    steps.append(step)
    _log_step(user.id, step)

    custom = await _custom_keywords(db, user.id)
    bundle = _bundle(user, custom)
    payload = build_keywords_redis_payload(user, bundle)
    try:
        keyword_count = sync_user_keywords_payload(user.id, payload)
    except Exception as exc:
        step = _step(
            "sync_keywords",
            "کش Redis کلمات کلیدی",
            "ذخیره کلمات ادغام‌شده در user:{id}:keywords",
            "error",
            str(exc),
        )
        steps.append(step)
        _log_step(user.id, step)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ذخیره کش کلمات کلیدی در Redis ناموفق بود.",
        ) from exc

    step = _step(
        "sync_keywords",
        "کش Redis کلمات کلیدی",
        "ذخیره کلمات ادغام‌شده در user:{id}:keywords",
        "success",
        f"{keyword_count} کلمه در Redis ذخیره و تأیید شد.",
    )
    steps.append(step)
    _log_step(user.id, step)

    updated_rows = await _set_engine_flag(db, user.id, True)
    step = _step(
        "set_db_flag",
        "Flag دیتابیس",
        "telegram_sessions.is_engine_active = True",
        "success" if updated_rows else "warning",
        f"{updated_rows} ردیف سشن به‌روزرسانی شد.",
    )
    steps.append(step)
    _log_step(user.id, step)

    sync_user_status(user.id, True, True)
    step = _step(
        "set_redis_status",
        "Flag Redis",
        "user:{id}:status → engine_active=true",
        "success",
        "وضعیت موتور در Redis ثبت شد.",
    )
    steps.append(step)
    _log_step(user.id, step)

    publish_engine_control("start", user.id)
    listener_ok, listener_detail = _check_listener_service()
    step = _step(
        "signal_listener",
        "سیگنال Listener",
        "ارسال رویداد engine:control و بررسی heartbeat",
        "success" if listener_ok else "warning",
        listener_detail,
    )
    steps.append(step)
    _log_step(user.id, step)

    processor_ok, processor_detail = _check_processor_service()
    step = _step(
        "check_processor",
        "بررسی Processor / Celery",
        "آمادگی ورکر برای تطبیق پیام‌ها",
        "success" if processor_ok else "warning",
        processor_detail,
    )
    steps.append(step)
    _log_step(user.id, step)

    verified_count = read_user_keyword_count(user.id)
    step = _step(
        "pipeline_ready",
        "Pipeline آماده",
        "موتور برای کاربر فعال شد؛ Listener/Processor باید پیام‌ها را پردازش کنند",
        "success" if verified_count > 0 else "warning",
        f"کش تأیید‌شده: {verified_count} کلمه.",
    )
    steps.append(step)
    _log_step(user.id, step)
    return steps


async def run_stop_pipeline(user: User, db: AsyncSession) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    license = _subscription_status(user)

    updated_rows = await _set_engine_flag(db, user.id, False)
    step = _step(
        "set_db_flag",
        "Flag دیتابیس",
        "telegram_sessions.is_engine_active = False",
        "success" if updated_rows else "warning",
        f"{updated_rows} ردیف سشن به‌روزرسانی شد.",
    )
    steps.append(step)
    _log_step(user.id, step)

    sync_user_status(user.id, False, license.is_valid)
    step = _step(
        "set_redis_status",
        "Flag Redis",
        "user:{id}:status → engine_active=false",
        "success",
        "شنود برای این کاربر متوقف شد.",
    )
    steps.append(step)
    _log_step(user.id, step)

    publish_engine_control("stop", user.id)
    step = _step(
        "signal_listener",
        "سیگنال Listener",
        "ارسال رویداد توقف به کانال engine:control",
        "success",
        "Listener پس از دریافت سیگنال اتصال را قطع می‌کند.",
    )
    steps.append(step)
    _log_step(user.id, step)
    return steps
