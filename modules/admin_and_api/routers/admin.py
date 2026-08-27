"""Admin-only user and license management endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.admin_and_api.deps import get_db
from modules.admin_and_api.routers.auth import get_current_admin
from modules.admin_and_api.schemas import (
    AdminLicenseRenewRequest,
    AdminSessionResponse,
    AdminUserResponse,
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


@router.get("/users", response_model=list[AdminUserResponse])
async def list_admin_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[AdminUserResponse]:
    """Return all users with license expiry for the admin panel."""
    result = await db.execute(select(User).order_by(User.id))
    return [_to_admin_user(user) for user in result.scalars().all()]


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
    """Return active rows from telegram_sessions with the owning user."""
    result = await db.execute(
        select(TelegramSession, User)
        .join(User, User.id == TelegramSession.user_id)
        .where(TelegramSession.is_active.is_(True))
        .order_by(TelegramSession.id)
    )
    rows: list[AdminSessionResponse] = []
    for session, owner in result.all():
        rows.append(
            AdminSessionResponse(
                id=session.id,
                user_id=session.user_id,
                username=owner.username if owner else None,
                full_name=owner.full_name if owner else None,
                phone_number=session.phone_number,
                is_active=session.is_active,
                created_at=session.created_at,
            )
        )
    return rows
