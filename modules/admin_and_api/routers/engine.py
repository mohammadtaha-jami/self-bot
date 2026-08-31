"""User engine start/stop/status endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import read_pipeline_log, read_user_keyword_count, read_user_status
from modules.admin_and_api.deps import get_current_user, get_db
from modules.admin_and_api.engine_pipeline import run_start_pipeline, run_stop_pipeline
from modules.admin_and_api.routers.licenses import _subscription_status
from modules.admin_and_api.schemas import (
    EngineActionResponse,
    EnginePipelineLogResponse,
    EngineStatusResponse,
)
from shared.models import User

router = APIRouter(prefix="/engine", tags=["Engine"])


def _indicator(engine_active: bool, license_valid: bool) -> str:
    if not license_valid:
        return "expired"
    if engine_active:
        return "listening"
    return "stopped"


def _status_payload(user: User) -> EngineStatusResponse:
    license = _subscription_status(user)
    cached_status = read_user_status(user.id)
    engine_active = bool(cached_status.get("engine_active")) and user.is_active
    return EngineStatusResponse(
        engine_active=engine_active,
        license_valid=license.is_valid,
        keyword_count=read_user_keyword_count(user.id),
        days_remaining=license.days_remaining,
        license_expires_at=license.subscription_end,
        indicator=_indicator(engine_active, license.is_valid),
    )


def _action_payload(user: User, pipeline: list[dict]) -> EngineActionResponse:
    status_payload = _status_payload(user)
    return EngineActionResponse(**status_payload.model_dump(), pipeline=pipeline)


@router.post("/start", response_model=EngineActionResponse)
async def start_engine(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EngineActionResponse:
    """Activate listening for the authenticated user after license and account checks."""
    pipeline = await run_start_pipeline(current_user, db)
    return _action_payload(current_user, pipeline)


@router.post("/stop", response_model=EngineActionResponse)
async def stop_engine(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EngineActionResponse:
    """Stop listening and mark sessions as engine-inactive."""
    pipeline = await run_stop_pipeline(current_user, db)
    return _action_payload(current_user, pipeline)


@router.get("/status", response_model=EngineStatusResponse)
async def engine_status(
    current_user: User = Depends(get_current_user),
) -> EngineStatusResponse:
    """Return live engine flag, cached keyword count, and remaining license days."""
    return _status_payload(current_user)


@router.get("/pipeline", response_model=EnginePipelineLogResponse)
async def engine_pipeline_log(
    current_user: User = Depends(get_current_user),
) -> EnginePipelineLogResponse:
    """Return recent pipeline steps for live dashboard monitoring."""
    items = read_pipeline_log(current_user.id, limit=30)
    return EnginePipelineLogResponse(items=items)
