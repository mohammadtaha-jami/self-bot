"""Keyword CRUD endpoints for the authenticated user."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.admin_and_api.deps import get_current_active_user, get_db
from modules.admin_and_api.schemas import KeywordCreate, KeywordResponse, KeywordUpdate
from shared.models import Keyword, User

router = APIRouter()


async def _get_owned_keyword(
    db: AsyncSession, keyword_id: int, user_id: int
) -> Keyword:
    result = await db.execute(
        select(Keyword).where(Keyword.id == keyword_id, Keyword.user_id == user_id)
    )
    keyword = result.scalar_one_or_none()
    if keyword is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keyword not found",
        )
    return keyword


@router.get("/", response_model=list[KeywordResponse])
async def list_keywords(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[Keyword]:
    """Return the current user's keyword rules."""
    result = await db.execute(
        select(Keyword)
        .where(Keyword.user_id == current_user.id)
        .order_by(Keyword.id)
    )
    return list(result.scalars().all())


@router.post("/", response_model=KeywordResponse, status_code=status.HTTP_201_CREATED)
async def create_keyword(
    payload: KeywordCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Keyword:
    """Add a new keyword rule for the current user."""
    keyword = Keyword(
        user_id=current_user.id,
        word=payload.text,
        type=payload.keyword_type,
    )
    db.add(keyword)
    await db.flush()
    await db.refresh(keyword)
    return keyword


@router.put("/{keyword_id}", response_model=KeywordResponse)
async def update_keyword(
    keyword_id: int,
    payload: KeywordUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Keyword:
    """Update an owned keyword rule."""
    keyword = await _get_owned_keyword(db, keyword_id, current_user.id)
    if payload.text is not None:
        keyword.word = payload.text
    if payload.keyword_type is not None:
        keyword.type = payload.keyword_type
    if payload.weight is not None:
        keyword.weight = payload.weight
    await db.flush()
    await db.refresh(keyword)
    return keyword


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_keyword(
    keyword_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an owned keyword rule."""
    keyword = await _get_owned_keyword(db, keyword_id, current_user.id)
    await db.delete(keyword)
    await db.flush()
