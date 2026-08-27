"""Admin-only user management endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.admin_and_api.deps import get_db
from modules.admin_and_api.routers.auth import get_current_admin
from modules.admin_and_api.schemas import UserResponse
from shared.models import User

router = APIRouter()


@router.get("/", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> list[User]:
    """Return all users. Admin-only."""
    result = await db.execute(select(User).order_by(User.id))
    return list(result.scalars().all())
