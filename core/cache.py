"""Redis connection pool and cache client setup."""

from redis.asyncio import ConnectionPool, Redis

from core.config import get_settings

_pool: ConnectionPool | None = None
_redis_client: Redis | None = None


def get_redis_pool() -> ConnectionPool:
    """Create or return the shared Redis connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return _pool


def get_redis_client() -> Redis:
    """Create or return the shared async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis(connection_pool=get_redis_pool())
    return _redis_client


async def close_redis() -> None:
    """Gracefully close Redis connections on shutdown."""
    global _redis_client, _pool
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    if _pool is not None:
        await _pool.aclose()
        _pool = None
