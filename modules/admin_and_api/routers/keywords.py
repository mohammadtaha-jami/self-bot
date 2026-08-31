"""Keyword CRUD endpoints for the authenticated user."""

import json
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import get_redis_client
from core.logger import setup_logging
from modules.admin_and_api.deps import get_current_active_user, get_db
from modules.admin_and_api.schemas import (
    KeywordBundleResponse,
    KeywordCreate,
    KeywordResponse,
    KeywordUpdate,
)
from modules.processor.presets import get_rules_for_business_types
from shared.enums import KeywordTypeEnum
from shared.models import Keyword, User

logger = setup_logging(__name__)
router = APIRouter()

FALLBACK_DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "real_estate": ["فروش آپارتمان", "رهن", "اجاره"],
    "crypto": ["بیت کوین", "ارز دیجیتال", "تتر"],
    "general": [],
}


def _default_keywords_for_business(business_type: str | None) -> list[str]:
    rules = get_rules_for_business_types(business_type)
    positives = [str(item).strip() for item in rules.get("keywords", []) if str(item).strip()]
    if positives:
        return list(dict.fromkeys(positives))
    if not business_type:
        return []
    key = business_type.strip().lower()
    return list(FALLBACK_DEFAULT_KEYWORDS.get(key, []))


def _merge_keywords(default_keywords: Iterable[str], custom_words: Iterable[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for word in [*default_keywords, *custom_words]:
        normalized = word.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged


def _to_response(keyword: Keyword) -> KeywordResponse:
    return KeywordResponse.model_validate(keyword)


async def _custom_keywords(db: AsyncSession, user_id: int) -> list[Keyword]:
    result = await db.execute(
        select(Keyword).where(Keyword.user_id == user_id).order_by(Keyword.id)
    )
    return list(result.scalars().all())


def _bundle(user: User, custom: list[Keyword]) -> KeywordBundleResponse:
    default_keywords = _default_keywords_for_business(user.business_type)
    custom_words = [item.word for item in custom]
    return KeywordBundleResponse(
        business_type=user.business_type,
        default_keywords=default_keywords,
        custom_keywords=[_to_response(item) for item in custom],
        final_keywords=_merge_keywords(default_keywords, custom_words),
    )


async def _sync_user_keywords_redis(user: User, bundle: KeywordBundleResponse) -> None:
    payload = {
        "business_type": bundle.business_type,
        "default_keywords": bundle.default_keywords,
        "custom_keywords": [item.word for item in bundle.custom_keywords],
        "final_keywords": bundle.final_keywords,
        "keywords": bundle.final_keywords,
        "negative_keywords": get_rules_for_business_types(user.business_type).get(
            "negative_keywords", []
        ),
    }
    cache_key = f"user:{user.id}:keywords"
    try:
        redis = get_redis_client()
        await redis.set(cache_key, json.dumps(payload, ensure_ascii=False))
    except Exception:
        logger.exception("Failed to sync keyword cache for user %s", user.id)


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


@router.get("/", response_model=KeywordBundleResponse)
async def list_keywords(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> KeywordBundleResponse:
    """Return default, custom, and merged keywords for the current user."""
    custom = await _custom_keywords(db, current_user.id)
    bundle = _bundle(current_user, custom)
    await _sync_user_keywords_redis(current_user, bundle)
    return bundle


@router.post("/", response_model=KeywordResponse, status_code=status.HTTP_201_CREATED)
async def create_keyword(
    payload: KeywordCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Keyword:
    """Add a custom keyword and refresh Redis `user:{id}:keywords`."""
    word = payload.text.strip()
    if not word:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="متن کلمه کلیدی خالی است.",
        )
    existing = await db.execute(
        select(Keyword).where(Keyword.user_id == current_user.id, Keyword.word == word)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این کلمه کلیدی قبلاً ثبت شده است.",
        )
    keyword = Keyword(
        user_id=current_user.id,
        word=word,
        type=payload.keyword_type or KeywordTypeEnum.POSITIVE,
    )
    db.add(keyword)
    await db.flush()
    await db.refresh(keyword)
    custom = await _custom_keywords(db, current_user.id)
    await _sync_user_keywords_redis(current_user, _bundle(current_user, custom))
    return keyword


@router.put("/{keyword_id}", response_model=KeywordResponse)
async def update_keyword(
    keyword_id: int,
    payload: KeywordUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Keyword:
    """Update an owned custom keyword and refresh Redis."""
    keyword = await _get_owned_keyword(db, keyword_id, current_user.id)
    if payload.text is not None:
        keyword.word = payload.text.strip()
    if payload.keyword_type is not None:
        keyword.type = payload.keyword_type
    if payload.weight is not None:
        keyword.weight = payload.weight
    await db.flush()
    await db.refresh(keyword)
    custom = await _custom_keywords(db, current_user.id)
    await _sync_user_keywords_redis(current_user, _bundle(current_user, custom))
    return keyword


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_keyword(
    keyword_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a custom keyword and refresh Redis `user:{id}:keywords`."""
    keyword = await _get_owned_keyword(db, keyword_id, current_user.id)
    await db.delete(keyword)
    await db.flush()
    custom = await _custom_keywords(db, current_user.id)
    await _sync_user_keywords_redis(current_user, _bundle(current_user, custom))
