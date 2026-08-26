"""License / subscription endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.admin_and_api.deps import get_current_active_user, get_db, require_admin
from modules.admin_and_api.schemas import LicenseRenewRequest, LicenseStatusResponse
from shared.models import User

router = APIRouter()


def _subscription_status(user: User) -> LicenseStatusResponse:
    now = datetime.now(timezone.utc)
    end = user.subscription_end
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    if end is None:
        days_remaining = 0
        is_valid = False
    else:
        remaining = end - now
        days_remaining = max(0, remaining.days)
        is_valid = remaining.total_seconds() > 0

    return LicenseStatusResponse(
        user_id=user.id,
        is_valid=is_valid,
        days_remaining=days_remaining,
        subscription_end=end,
    )


@router.get("/status", response_model=LicenseStatusResponse)
async def get_license_status(
    current_user: User = Depends(get_current_active_user),
) -> LicenseStatusResponse:
    """Return remaining subscription days for the current user."""
    return _subscription_status(current_user)


@router.post("/renew", response_model=LicenseStatusResponse)
async def renew_license(
    payload: LicenseRenewRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> LicenseStatusResponse:
    """Extend a user's subscription. Admin-only."""
    result = await db.execute(select(User).where(User.id == payload.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    now = datetime.now(timezone.utc)
    current_end = user.subscription_end
    if current_end is not None and current_end.tzinfo is None:
        current_end = current_end.replace(tzinfo=timezone.utc)

    base = current_end if current_end is not None and current_end > now else now
    user.subscription_end = base + timedelta(days=payload.extra_days)
    await db.flush()
    await db.refresh(user)
    return _subscription_status(user)
