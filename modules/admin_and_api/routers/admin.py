"""Admin-only user and license management endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.security import create_access_token, get_password_hash
from core.cache import listener_heartbeat_key, service_heartbeat_age_seconds
from modules.admin_and_api.deps import get_db, set_access_token_cookie
from modules.admin_and_api.engine_pipeline import HEARTBEAT_MAX_AGE_SECONDS
from modules.admin_and_api.routers.auth import get_current_admin
from modules.admin_and_api.schemas import (
    AdminLicenseRenewRequest,
    AdminSessionResponse,
    AdminUserCreate,
    AdminUserResponse,
    AdminUserUpdate,
    Token,
)
from shared.models import TelegramSession, User

router = APIRouter()


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _to_admin_user(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        phone_number=user.phone_number,
        telegram_username=user.telegram_username,
        telegram_id=user.telegram_id,
        telegram_chat_id=user.telegram_chat_id,
        is_notifier_active=user.is_notifier_active,
        full_name=user.full_name,
        is_active=user.is_active,
        is_admin=user.is_admin,
        business_type=user.business_type,
        dashboard_password=None if user.is_admin else user.dashboard_password,
        license_expires_at=_aware_utc(user.subscription_end),
    )


async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


async def _sync_telegram_sessions_active(
    db: AsyncSession, user_id: int, is_active: bool
) -> None:
    await db.execute(
        update(TelegramSession)
        .where(TelegramSession.user_id == user_id)
        .values(is_active=is_active)
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_admin_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[AdminUserResponse]:
    """Return all users with license expiry for the admin panel."""
    result = await db.execute(select(User).order_by(User.id))
    return [_to_admin_user(user) for user in result.scalars().all()]


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminUserResponse:
    """Create a dashboard user without Telegram authentication."""
    login_username = payload.username.strip()
    phone = payload.phone_number.strip()
    existing_login = await db.execute(select(User).where(User.username == login_username))
    if existing_login.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این نام کاربری قبلاً ثبت شده است.",
        )
    existing_phone = await db.execute(select(User).where(User.phone_number == phone))
    if existing_phone.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این شماره تلفن قبلاً ثبت شده است.",
        )

    now = datetime.now(timezone.utc)
    if payload.license_expires_at is not None:
        subscription_end = _aware_utc(payload.license_expires_at)
    else:
        subscription_end = now + timedelta(days=int(payload.license_duration_days))

    user = User(
        username=login_username[:100],
        phone_number=phone[:20],
        full_name=payload.full_name.strip()[:100],
        business_type=payload.business_type,
        hashed_password=get_password_hash(payload.password),
        dashboard_password=payload.password,
        is_active=True,
        is_admin=False,
        subscription_end=subscription_end,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return _to_admin_user(user)


@router.patch("/users/{user_id}/toggle-active", response_model=AdminUserResponse)
async def toggle_user_active(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> AdminUserResponse:
    """Flip the target user's ``is_active`` flag."""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نمی‌توانید وضعیت دسترسی خودتان را تغییر دهید.",
        )
    user = await _get_user_or_404(db, user_id)
    user.is_active = not user.is_active
    await _sync_telegram_sessions_active(db, user.id, user.is_active)
    await db.flush()
    await db.refresh(user)
    return _to_admin_user(user)


@router.post("/users/{user_id}/impersonate", response_model=Token)
async def impersonate_user(
    user_id: int,
    response: Response,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Token:
    """Issue a JWT as the target tenant so the admin can open their dashboard."""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نمی‌توانید با حساب خودتان وارد پنل کاربری شوید.",
        )
    user = await _get_user_or_404(db, user_id)
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ورود به پنل کاربر ادمین مجاز نیست.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این کاربر غیرفعال است.",
        )

    settings = get_settings()
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "impersonated_by": admin.id,
        },
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    set_access_token_cookie(response, access_token)
    return Token(access_token=access_token, token_type="bearer")


@router.put("/users/{user_id}", response_model=AdminUserResponse)
async def update_admin_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> AdminUserResponse:
    """Update user profile fields; deactivate linked Telegram sessions when inactive."""
    user = await _get_user_or_404(db, user_id)

    if payload.is_active is False and user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نمی‌توانید وضعیت دسترسی خودتان را تغییر دهید.",
        )

    if payload.username is not None:
        new_username = payload.username.strip()
        taken = await db.execute(
            select(User).where(User.username == new_username, User.id != user_id)
        )
        if taken.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="این نام کاربری قبلاً ثبت شده است.",
            )
        user.username = new_username[:100]

    if payload.phone_number is not None:
        new_phone = payload.phone_number.strip()
        taken_phone = await db.execute(
            select(User).where(User.phone_number == new_phone, User.id != user_id)
        )
        if taken_phone.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="این شماره تلفن قبلاً ثبت شده است.",
            )
        user.phone_number = new_phone[:20]

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()[:100]
    if payload.business_type is not None:
        user.business_type = payload.business_type
    if payload.password:
        user.hashed_password = get_password_hash(payload.password)
        if not user.is_admin:
            user.dashboard_password = payload.password
    if payload.license_days is not None:
        user.subscription_end = datetime.now(timezone.utc) + timedelta(days=payload.license_days)
    if payload.is_active is not None:
        user.is_active = payload.is_active

    await _sync_telegram_sessions_active(db, user.id, user.is_active)

    await db.flush()
    await db.refresh(user)
    return _to_admin_user(user)


@router.post("/users/{user_id}/renew-license", response_model=AdminUserResponse)
async def renew_user_license(
    user_id: int,
    payload: AdminLicenseRenewRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> AdminUserResponse:
    """Extend subscription from remaining expiry, or from UTC now if expired/missing."""
    user = await _get_user_or_404(db, user_id)
    now = datetime.now(timezone.utc)
    current_end = _aware_utc(user.subscription_end)
    base = current_end if current_end is not None and current_end > now else now
    user.subscription_end = base + timedelta(days=payload.days)
    await db.flush()
    await db.refresh(user)
    return _to_admin_user(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> None:
    """Delete a non-admin user and cascaded sessions/keywords/leads."""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="نمی‌توانید حساب خودتان را حذف کنید.",
        )
    user = await _get_user_or_404(db, user_id)
    if user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="حذف کاربر ادمین مجاز نیست.",
        )
    await db.delete(user)
    await db.flush()


@router.get("/telegram-sessions", response_model=list[AdminSessionResponse])
@router.get("/sessions", response_model=list[AdminSessionResponse], include_in_schema=False)
async def list_active_telegram_sessions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[AdminSessionResponse]:
    """Return connected telegram_sessions with engine and live-listener status."""
    result = await db.execute(
        select(TelegramSession, User)
        .join(User, User.id == TelegramSession.user_id)
        .where(TelegramSession.is_active.is_(True))
        .order_by(TelegramSession.id)
    )
    pairs = result.all()
    heartbeat_age = service_heartbeat_age_seconds(listener_heartbeat_key())
    listener_alive = heartbeat_age is not None and heartbeat_age <= HEARTBEAT_MAX_AGE_SECONDS
    listening_session_id = next(
        (session.id for session, _owner in pairs if session.is_engine_active),
        None,
    )

    rows: list[AdminSessionResponse] = []
    for session, owner in pairs:
        rows.append(
            AdminSessionResponse(
                id=session.id,
                user_id=session.user_id,
                username=owner.username if owner else None,
                full_name=owner.full_name if owner else None,
                phone_number=session.phone_number,
                is_active=session.is_active,
                is_engine_active=bool(session.is_engine_active),
                is_listening=bool(
                    listener_alive
                    and session.is_engine_active
                    and session.id == listening_session_id
                ),
                created_at=session.created_at,
            )
        )
    return rows
