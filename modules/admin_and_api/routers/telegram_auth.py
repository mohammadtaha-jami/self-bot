"""Telegram client authentication endpoints for Telethon session string generation."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

from core.config import get_settings
from modules.admin_and_api.deps import get_db
from modules.admin_and_api.routers.auth import get_current_admin
from modules.admin_and_api.schemas import TelegramSendCodeRequest, TelegramVerifyRequest
from modules.listener.auth import _build_client, _disconnect_client
from shared.models import TelegramSession, User

router = APIRouter(prefix="/telegram", tags=["Telegram Connection"])

active_auth_sessions: dict[str, TelegramClient] = {}


@router.post("/send-code")
async def send_telegram_code(
    payload: TelegramSendCodeRequest,
    admin_user: User = Depends(get_current_admin),
):
    """ارسال کد تایید به شماره تلفن تلگرام"""
    settings = get_settings()

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="تنظیمات TELEGRAM_API_ID یا TELEGRAM_API_HASH در فایل .env تعریف نشده است.",
        )

    previous = active_auth_sessions.pop(payload.phone_number, None)
    if previous is not None:
        await _disconnect_client(previous)

    client = _build_client()
    await client.connect()
    try:
        sent_code = await client.send_code_request(payload.phone_number)
        active_auth_sessions[payload.phone_number] = client

        return {
            "status": "success",
            "message": "کد تایید به تلگرام ارسال شد.",
            "phone_code_hash": sent_code.phone_code_hash,
        }
    except Exception as e:
        await _disconnect_client(client)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"خطا در ارسال کد: {str(e)}",
        )


def _profile_from_telegram(tg_user) -> dict:
    first = (getattr(tg_user, "first_name", None) or "").strip()
    last = (getattr(tg_user, "last_name", None) or "").strip()
    full_name = " ".join(part for part in (first, last) if part).strip() or None
    raw_username = getattr(tg_user, "username", None)
    telegram_username = (
        raw_username.strip() if isinstance(raw_username, str) and raw_username.strip() else None
    )
    return {
        "telegram_id": getattr(tg_user, "id", None),
        "telegram_username": telegram_username,
        "full_name": full_name,
    }


async def _attach_session_to_user(
    db: AsyncSession,
    user_id: int,
    tg_profile: dict,
    phone_number: str,
) -> User:
    """Attach Telegram session data to an existing users row."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="کاربر هدف یافت نشد.",
        )
    telegram_id = tg_profile.get("telegram_id")
    if telegram_id:
        taken = await db.execute(
            select(User).where(User.telegram_id == telegram_id, User.id != user.id)
        )
        if taken.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="این اکانت تلگرام به کاربر دیگری متصل است.",
            )
        user.telegram_id = telegram_id
    user.telegram_username = tg_profile.get("telegram_username")
    if phone_number:
        user.phone_number = phone_number[:20]
    if not user.full_name and tg_profile.get("full_name"):
        user.full_name = tg_profile["full_name"][:100]
    await db.flush()
    return user


async def _upsert_telegram_session(
    db: AsyncSession,
    *,
    user_id: int,
    phone_number: str,
    session_string: str,
) -> TelegramSession:
    """One active session per phone number (and per user+phone)."""
    by_phone = await db.execute(
        select(TelegramSession).where(TelegramSession.phone_number == phone_number)
    )
    session_obj = by_phone.scalar_one_or_none()

    if session_obj is None:
        by_user_phone = await db.execute(
            select(TelegramSession).where(
                TelegramSession.user_id == user_id,
                TelegramSession.phone_number == phone_number,
            )
        )
        session_obj = by_user_phone.scalar_one_or_none()

    if session_obj:
        session_obj.user_id = user_id
        session_obj.session_string = session_string
        session_obj.is_active = True
        return session_obj

    session_obj = TelegramSession(
        user_id=user_id,
        phone_number=phone_number,
        session_string=session_string,
        is_active=True,
    )
    db.add(session_obj)
    return session_obj


@router.post("/verify-code")
async def verify_telegram_code(
    payload: TelegramVerifyRequest,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Verify Telegram login, resolve the owner user, and upsert telegram_sessions."""
    client = active_auth_sessions.get(payload.phone_number)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="جلسه کاری یافت نشد. لطفاً ابتدا شماره تلفن را وارد کنید.",
        )

    try:
        await client.sign_in(
            payload.phone_number,
            payload.code,
            phone_code_hash=payload.phone_code_hash,
        )
    except SessionPasswordNeededError:
        if not payload.two_factor_password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="2FA_REQUIRED",
            )
        await client.sign_in(password=payload.two_factor_password)
    except (PhoneCodeInvalidError, PhoneCodeExpiredError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="کد وارد شده اشتباه یا منقضی شده است.",
        )

    if not isinstance(client.session, StringSession):
        await _disconnect_client(client)
        active_auth_sessions.pop(payload.phone_number, None)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ذخیره سشن تلگرام ناموفق بود.",
        )
    string_session = client.session.save()
    tg_profile = _profile_from_telegram(await client.get_me())
    await _disconnect_client(client)
    del active_auth_sessions[payload.phone_number]

    owner = await _attach_session_to_user(
        db,
        payload.owner_user_id,
        tg_profile,
        payload.phone_number,
    )
    await _upsert_telegram_session(
        db,
        user_id=owner.id,
        phone_number=payload.phone_number,
        session_string=string_session,
    )
    await db.commit()

    return {
        "status": "success",
        "message": "اتصال تلگرام ذخیره شد.",
        "user_id": owner.id,
        "username": owner.username,
        "phone_number": owner.phone_number,
        "telegram_username": owner.telegram_username,
        "telegram_id": owner.telegram_id,
        "full_name": owner.full_name,
        "business_type": owner.business_type,
        "dashboard_password": None if owner.is_admin else owner.dashboard_password,
    }
