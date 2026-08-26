"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.logger import setup_logging
from modules.admin_and_api.routers import auth, keywords, leads, licenses

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
        leads.router,
        prefix="/api/v1/leads",
        tags=["Leads"],
    )

    # 4. Web UI Routes
    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page(request: Request):
        return templates.TemplateResponse(request=request, name="login.html")

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard_page(request: Request):
        return templates.TemplateResponse(request=request, name="dashboard.html")

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    async def admin_page(request: Request):
        return templates.TemplateResponse(request=request, name="admin.html")

    logger.info("FastAPI application created with UI and API endpoints")
    return app


app = create_app()