"""FastAPI application factory."""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from core.logger import setup_logging
from modules.admin_and_api.deps import get_db, get_user_from_cookie
from modules.admin_and_api.routers import (
    admin,
    auth,
    engine,
    keywords,
    leads,
    licenses,
    notifications,
    users,
)
from modules.admin_and_api.routers.telegram_auth import router as telegram_router
logger = setup_logging(__name__)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(
        title="Telegram Lead Intelligence API",
        description="Admin API and dashboard for opportunity detection",
        version="0.1.0",
    )

    # 1. Mount Static Files
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # 2. Setup Template Engine
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # 3. Register API Routers
    app.include_router(
        auth.router,
        prefix="/api/v1/auth",
        tags=["Authentication"],
    )
    app.include_router(
        keywords.router,
        prefix="/api/v1/keywords",
        tags=["Keywords"],
    )
    app.include_router(
        licenses.router,
        prefix="/api/v1/licenses",
        tags=["Licenses"],
    )
    app.include_router(
        engine.router,
        prefix="/api/v1",
        tags=["Engine"],
    )
    app.include_router(
        leads.router,
        prefix="/api/v1/leads",
        tags=["Leads"],
    )
    app.include_router(
        telegram_router,
        prefix="/api/v1",
    )
    app.include_router(
        users.router,
        prefix="/api/v1/users",
        tags=["Users"],
    )
    app.include_router(
        admin.router,
        prefix="/api/v1/admin",
        tags=["Admin"],
    )
    app.include_router(
        notifications.router,
        prefix="/api/v1/notifications",
        tags=["Notifications"],
    )

    # 4. Web UI Routes
    def _admin_template(request: Request, name: str, user, templates=templates):
        if user is None:
            return templates.TemplateResponse(
                request=request, name="admin_gate.html"
            )
        if not user.is_active:
            return RedirectResponse(url="/login", status_code=303)
        if not user.is_admin:
            return templates.TemplateResponse(
                request=request, name="access_denied.html"
            )
        return templates.TemplateResponse(request=request, name=name)

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page(request: Request):
        return templates.TemplateResponse(request=request, name="login.html")

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard_page(request: Request):
        return templates.TemplateResponse(request=request, name="dashboard.html")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ):
        user = await get_user_from_cookie(request, db)
        return _admin_template(request, "index.html", user)

    @app.get("/users", response_class=HTMLResponse, include_in_schema=False)
    async def users_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ):
        user = await get_user_from_cookie(request, db)
        return _admin_template(request, "users.html", user)

    @app.get("/sessions", response_class=HTMLResponse, include_in_schema=False)
    async def sessions_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ):
        user = await get_user_from_cookie(request, db)
        return _admin_template(request, "sessions.html", user)

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ):
        user = await get_user_from_cookie(request, db)
        return _admin_template(request, "index.html", user)

    logger.info("FastAPI application created with UI and API endpoints")
    return app


app = create_app()