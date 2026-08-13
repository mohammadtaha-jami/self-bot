"""SQLAdmin interface setup for database management."""

from core.logger import setup_logging

logger = setup_logging(__name__)


def setup_admin(app, engine) -> None:
    """
    Mount SQLAdmin views onto the FastAPI application.

    Args:
        app: FastAPI application instance.
        engine: SQLAlchemy sync or async engine for admin queries.
    """
    # TODO: Register ModelView classes for all 8 domain models
    logger.info("SQLAdmin setup (placeholder)")
