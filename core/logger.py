"""Structured logging configuration for all services."""

import logging
import sys

from core.config import get_settings


def setup_logging(name: str | None = None) -> logging.Logger:
    """
    Configure and return a logger with structured formatting.

    Args:
        name: Logger name. Defaults to root logger when None.

    Returns:
        Configured logger instance.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if not logger.handlers:
        logger.addHandler(handler)

    return logger
