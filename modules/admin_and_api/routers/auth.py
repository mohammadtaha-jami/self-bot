"""Authentication endpoints."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.security import create_access_token, get_password_hash, verify_password
from modules.admin_and_api.deps import (
    clear_access_token_cookie,
    get_current_active_user,
    get_db,
    oauth2_scheme,
    set_access_token_cookie,
)
from modules.admin_and_api.schemas import Token, UserCreate, UserLogin, UserResponse
from shared.models import User

router = APIRouter()


async def get_current_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Reject non-admin users with HTTP 403."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="دسترسی غیرمجاز",
        )
    return current_user


async def _authenticate_user(
    db: AsyncSession, username: str, password: str
) -> User:
    """Load a user and verify password; raise 401 on failure."""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.hashed_password
        or not verify_password(password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _build_access_token(user: User) -> Token:
    settings = get_settings()
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return Token(access_token=access_token, token_type="bearer")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Create a new user with a hashed password."""
    existing_username = await db.execute(
        select(User).where(User.username == payload.username)
    )
    if existing_username.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    if payload.telegram_id is not None:
        existing_telegram = await db.execute(
            select(User).where(User.telegram_id == payload.telegram_id)
        )
        if existing_telegram.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Telegram ID already registered",
            )

    user = User(
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        business_type=payload.business_type,
        telegram_id=payload.telegram_id,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Validate OAuth2 form credentials and return a JWT access token."""
    credentials = UserLogin(username=form_data.username, password=form_data.password)
    user = await _authenticate_user(db, credentials.username, credentials.password)
    token = _build_access_token(user)
    set_access_token_cookie(response, token.access_token)
    return token


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the auth cookie (localStorage is cleared on the client)."""
    clear_access_token_cookie(response)
    return {"status": "ok"}


@router.post("/sync-cookie")
async def sync_cookie(
    response: Response,
    token: str = Depends(oauth2_scheme),
    _: User = Depends(get_current_active_user),
) -> dict:
    """Set the HttpOnly cookie from a Bearer token (HTML route guards)."""
    set_access_token_cookie(response, token)
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Return the authenticated active user."""
    return current_user
