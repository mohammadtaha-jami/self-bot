"""Celery / async worker entry point for the processor service."""

from core.logger import setup_logging

logger = setup_logging(__name__)


def main() -> None:
    """Start the background worker consuming messages from Redis."""
    logger.info("Processor worker starting...")
    # TODO: Initialize Celery app or async consumer loop
    raise NotImplementedError("Processor worker not yet implemented")


if __name__ == "__main__":
    main()
