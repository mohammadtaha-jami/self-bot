"""FastAPI application factory."""

from fastapi import FastAPI

from core.logger import setup_logging

logger = setup_logging(__name__)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(
        title="Telegram Lead Intelligence API",
        description="Admin API and dashboard for opportunity detection",
        version="0.1.0",
    )

    # TODO: Register routers, admin panel, lifespan hooks
    logger.info("FastAPI application created (placeholder)")

    return app


app = create_app()
