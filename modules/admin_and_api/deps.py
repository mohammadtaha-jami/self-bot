"""FastAPI dependencies for database sessions and JWT-authenticated users."""

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import get_db_session as get_db
from modules.admin_and_api.schemas import TokenData
from shared.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
ACCESS_TOKEN_COOKIE = "access_token"


def set_access_token_cookie(response: Response, token: str) -> None:
    """Attach the JWT as an HttpOnly cookie so HTML routes can authorize."""
    settings = get_settings()
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        path="/",
        max_age=settings.access_token_expire_minutes * 60,
    )


def clear_access_token_cookie(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the Bearer JWT and load the matching User row."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id = payload.get("sub")
        username = payload.get("username")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(username=username, user_id=int(user_id))
        if token_data.user_id is None:
            raise credentials_exception
    except (JWTError, TypeError, ValueError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_user_from_cookie(
    request: Request,
    db: AsyncSession,
) -> User | None:
    """Load the user from the HttpOnly access_token cookie, if present."""
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token:
        return None
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id = payload.get("sub")
        if user_id is None:
            return None
        token_user_id = int(user_id)
    except (JWTError, TypeError, ValueError):
        return None

    result = await db.execute(select(User).where(User.id == token_user_id))
    return result.scalar_one_or_none()


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Reject inactive accounts."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user  


async def get_current_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Allow only active users with ``is_admin == True``."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="دسترسی غیرمجاز",
        )
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_admin),
) -> User:
    """Alias for get_current_admin (backward-compatible)."""
    return current_user