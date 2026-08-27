"""Telegram client authentication endpoints for session string generation."""

from fastapi import APIRouter, Depends, HTTPException, status
from pyrogram.client import Client
from pyrogram.errors import PhoneCodeExpired, PhoneCodeInvalid, SessionPasswordNeeded
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.security import generate_dashboard_password, get_password_hash
from modules.admin_and_api.deps import get_db
from modules.admin_and_api.routers.auth import get_current_admin
from modules.admin_and_api.schemas import TelegramSendCodeRequest, TelegramVerifyRequest
from shared.models import TelegramSession, User

router = APIRouter(prefix="/telegram", tags=["Telegram Connection"])

active_auth_sessions: dict[str, Client] = {}


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

    client = Client(
        name=f"session_{payload.phone_number.replace('+', '')}",
        api_id=int(settings.telegram_api_id),
        api_hash=str(settings.telegram_api_hash),
        in_memory=True,
    )

    await client.connect()
    try:
        sent_code = await client.send_code(payload.phone_number)
        active_auth_sessions[payload.phone_number] = client

        return {
            "status": "success",
            "message": "کد تایید به تلگرام ارسال شد.",
            "phone_code_hash": sent_code.phone_code_hash,
        }
    except Exception as e:
        await client.disconnect()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"خطا در ارسال کد: {str(e)}",
        )


async def _next_fallback_username(db: AsyncSession) -> str:
    """Build user-06 style names from current user count."""
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    n = int(total) + 1
    while True:
        candidate = f"user-{n:02d}"
        taken = await db.execute(select(User).where(User.username == candidate))
        if taken.scalar_one_or_none() is None:
            return candidate
        n += 1


def _profile_from_telegram(tg_user) -> dict:
    username = (getattr(tg_user, "username", None) or "").strip() or None
    first = (getattr(tg_user, "first_name", None) or "").strip()
    last = (getattr(tg_user, "last_name", None) or "").strip()
    full_name = " ".join(part for part in (first, last) if part).strip() or None
    return {
        "telegram_id": getattr(tg_user, "id", None),
        "username": username,
        "full_name": full_name,
    }


async def _unique_username(db: AsyncSession, preferred: str | None) -> str:
    if preferred:
        preferred = preferred[:100]
        taken = await db.execute(select(User).where(User.username == preferred))
        if taken.scalar_one_or_none() is None:
            return preferred
    return await _next_fallback_username(db)


async def _assign_dashboard_password(user: User) -> None:
    if user.is_admin:
        user.dashboard_password = None
        return
    plain = generate_dashboard_password()
    user.dashboard_password = plain
    user.hashed_password = get_password_hash(plain)


async def _resolve_session_owner(
    db: AsyncSession,
    payload: TelegramVerifyRequest,
    tg_profile: dict,
) -> User:
    """Attach the Telegram session to an existing user or create a new one."""
    if payload.target_user_id is not None:
        result = await db.execute(select(User).where(User.id == payload.target_user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="کاربر هدف یافت نشد.",
            )
        if payload.business_type:
            user.business_type = payload.business_type
        if not user.full_name and tg_profile.get("full_name"):
            user.full_name = tg_profile["full_name"][:100]
        if not user.username:
            user.username = await _unique_username(db, tg_profile.get("username"))
        if not user.is_admin and not user.dashboard_password:
            await _assign_dashboard_password(user)
        await db.flush()
        return user

    username = await _unique_username(db, tg_profile.get("username"))
    full_name = tg_profile.get("full_name") or username
    user = User(
        username=username,
        full_name=full_name[:100],
        business_type=payload.business_type,
        telegram_id=tg_profile.get("telegram_id"),
        is_active=True,
        is_admin=False,
    )
    await _assign_dashboard_password(user)
    db.add(user)
    try:
        await db.flush()
    except Exception:
        user.telegram_id = None
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
            phone_number=payload.phone_number,
            phone_code_hash=payload.phone_code_hash,
            phone_code=payload.code,
        )
    except SessionPasswordNeeded:
        if not payload.two_factor_password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="2FA_REQUIRED",
            )
        await client.check_password(payload.two_factor_password)
    except (PhoneCodeInvalid, PhoneCodeExpired):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="کد وارد شده اشتباه یا منقضی شده است.",
        )

    string_session = await client.export_session_string()
    tg_profile = _profile_from_telegram(await client.get_me())
    await client.disconnect()
    del active_auth_sessions[payload.phone_number]

    owner = await _resolve_session_owner(db, payload, tg_profile)
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
        "full_name": owner.full_name,
        "business_type": owner.business_type,
        "dashboard_password": None if owner.is_admin else owner.dashboard_password,
    }
