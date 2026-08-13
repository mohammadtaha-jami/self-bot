"""Telethon client startup entry point for the listener service."""

from core.logger import setup_logging

logger = setup_logging(__name__)


async def main() -> None:
    """Initialize Telethon client, register handlers, and start listening."""
    logger.info("Listener service starting...")
    # TODO: Wire up Telethon client, auth, handlers, and producer
    raise NotImplementedError("Listener service not yet implemented")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
