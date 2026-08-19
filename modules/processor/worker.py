"""Celery worker entry point for the processor service."""

import os

import redis.connection as redis_connection
from celery import Celery
from dotenv import load_dotenv

from core.logger import setup_logging

logger = setup_logging(__name__)
load_dotenv()


def _legacy_redis_kwargs(kwargs: dict) -> dict:
    """RESP2 + no maintenance push-notifications (Redis < 6 / old Windows builds)."""
    from redis.maint_notifications import MaintNotificationsConfig

    kwargs["protocol"] = 2
    kwargs["maint_notifications_config"] = MaintNotificationsConfig(enabled=False)
    return kwargs


def _patch_init(cls) -> None:
    original_init = cls.__init__
    if getattr(original_init, "_selfbot_resp2_patched", False):
        return

    def _init(self, *args, **kwargs):
        original_init(self, *args, **_legacy_redis_kwargs(kwargs))

    _init._selfbot_resp2_patched = True  # type: ignore[attr-defined]
    cls.__init__ = _init


def _force_redis_resp2() -> None:
    """Force redis-py onto RESP2 before Celery/Kombu opens any sockets.

    redis-py 8 defaults to RESP3 (``HELLO 3``) and also auto-enables
    maintenance notifications, which require hiredis/RESP3 parsers.

    Kombu 5.6 ``Connection._init_params()`` does **not** accept ``protocol``,
    so it cannot be set via the broker URL. Patch redis-py Connection and
    ConnectionPool instead — covers both broker and result backend.
    """
    conn_cls = getattr(redis_connection, "AbstractConnection", None)
    if conn_cls is None:
        conn_cls = redis_connection.Connection
    _patch_init(conn_cls)

    pool_cls = getattr(redis_connection, "ConnectionPool", None)
    if pool_cls is not None:
        _patch_init(pool_cls)


_force_redis_resp2()

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
# Do not append ?protocol=2 — Kombu treats unknown query keys as Connection kwargs.
REDIS_URL = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0")

celery_app = Celery(
    "processor_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["modules.processor.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=4,
    broker_connection_retry_on_startup=True,
    # Only keys Kombu redis transport actually understands (not `protocol`).
    broker_transport_options={
        "client_name": "celery_worker",
        "retry_on_timeout": True,
        "socket_connect_timeout": 10,
        "socket_timeout": 10,
        "health_check_interval": 30,
    },
    result_backend_transport_options={
        "retry_on_timeout": True,
    },
)


def main() -> None:
    """Start the background worker consuming messages from Redis."""
    logger.info("Processor worker starting...")
    celery_app.worker_main(["worker", "--loglevel=info", "-P", "solo"])


if __name__ == "__main__":
    main()
