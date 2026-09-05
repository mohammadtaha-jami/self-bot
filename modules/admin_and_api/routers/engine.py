"""User engine start/stop/status endpoints."""

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import read_listen_scope, read_pipeline_log, read_user_keyword_count, read_user_status
from modules.admin_and_api.deps import get_current_user, get_db
from modules.admin_and_api.engine_pipeline import run_start_pipeline, run_stop_pipeline
from modules.admin_and_api.routers.licenses import _subscription_status
from modules.admin_and_api.schemas import (
    EngineActionResponse,
    EnginePipelineLogResponse,
    EngineStartRequest,
    EngineStatusResponse,
    TelegramFolderListResponse,
    TelegramFolderOption,
)
from shared.models import TelegramSession, User

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
    scope = read_listen_scope(user.id)
    if engine_active and scope.get("mode") == "folder":
        listen_mode = "folder"
        folder_id = scope.get("folder_id")
        folder_title = scope.get("folder_title")
        chat_count = scope.get("chat_count")
    elif user.listen_folder_id is not None:
        listen_mode = "folder"
        folder_id = user.listen_folder_id
        folder_title = user.listen_folder_title
        chat_count = scope.get("chat_count") if scope.get("mode") == "folder" else None
    else:
        listen_mode = "all"
        folder_id = None
        folder_title = None
        chat_count = None
    return EngineStatusResponse(
        engine_active=engine_active,
        license_valid=license.is_valid,
        keyword_count=read_user_keyword_count(user.id),
        days_remaining=license.days_remaining,
        license_expires_at=license.subscription_end,
        indicator=_indicator(engine_active, license.is_valid),
        listen_mode=listen_mode,
        listen_folder_id=folder_id,
        listen_folder_title=folder_title,
        allowed_chat_count=chat_count,
    )


def _action_payload(user: User, pipeline: list[dict]) -> EngineActionResponse:
    status_payload = _status_payload(user)
    return EngineActionResponse(**status_payload.model_dump(), pipeline=pipeline)


@router.get("/folders", response_model=TelegramFolderListResponse)
async def list_telegram_folders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TelegramFolderListResponse:
    """List Telegram chat folders (Dialog Filters) for the signed-in user's session."""
    all_option = TelegramFolderOption(id=None, title="همه (گروه‌ها و کانال‌ها)", kind="all")
    result = await db.execute(
        select(TelegramSession)
        .where(
            TelegramSession.user_id == current_user.id,
            TelegramSession.is_active.is_(True),
        )
        .order_by(TelegramSession.id)
    )
    session = result.scalars().first()
    if session is None:
        return TelegramFolderListResponse(
            folders=[all_option],
            selected_folder_id=current_user.listen_folder_id,
            detail="سشن تلگرام یافت نشد؛ فقط گزینه «همه» در دسترس است.",
        )

    from modules.listener.auth import _disconnect_client, load_client
    from modules.listener.dialog_filters import fetch_dialog_filter_items, summarize_dialog_filters

    client = None
    try:
        client = await load_client(session.session_string)
        items = await fetch_dialog_filter_items(client)
        folders = [
            TelegramFolderOption(id=item["id"], title=item["title"], kind=item["kind"])
            for item in summarize_dialog_filters(items)
        ]
        return TelegramFolderListResponse(
            folders=[all_option, *folders],
            selected_folder_id=current_user.listen_folder_id,
        )
    except Exception as exc:
        return TelegramFolderListResponse(
            folders=[all_option],
            selected_folder_id=current_user.listen_folder_id,
            detail=f"خواندن پوشه‌های تلگرام ممکن نشد: {exc}",
        )
    finally:
        if client is not None:
            await _disconnect_client(client)


@router.post("/start", response_model=EngineActionResponse)
async def start_engine(
    payload: EngineStartRequest = Body(default=EngineStartRequest()),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EngineActionResponse:
    """Activate listening for the authenticated user after license and account checks."""
    pipeline = await run_start_pipeline(current_user, db, folder_id=payload.folder_id)
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
