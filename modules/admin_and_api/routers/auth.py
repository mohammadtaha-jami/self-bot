"""Authentication endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login() -> dict:
    """Authenticate a user and return an access token."""
    # TODO: Implement JWT or session-based auth
    raise NotImplementedError("Login endpoint not yet implemented")
