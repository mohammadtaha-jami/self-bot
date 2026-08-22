"""FastAPI application factory."""

from fastapi import FastAPI

from core.logger import setup_logging
from modules.admin_and_api.routers import auth

logger = setup_logging(__name__)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(
        title="Telegram Lead Intelligence API",
        description="Admin API and dashboard for opportunity detection",
        version="0.1.0",
    )

    app.include_router(
        auth.router,
        prefix="/api/v1/auth",
        tags=["Authentication"],
    )

    logger.info("FastAPI application created")
    return app


app = create_app()
