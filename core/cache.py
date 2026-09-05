"""Redis connection pool and shared sync/async clients."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis as sync_redis
from redis.asyncio import ConnectionPool, Redis

from core.config import get_settings

_pool: ConnectionPool | None = None
_redis_client: Redis | None = None
_sync_redis_client: sync_redis.Redis | None = None

ENGINE_CONTROL_CHANNEL = "engine:control"
PIPELINE_LOG_MAX_ENTRIES = 50


def user_keywords_key(user_id: int | str) -> str:
    return f"user:{user_id}:keywords"


def user_status_key(user_id: int | str) -> str:
    return f"user:{user_id}:status"


def user_pipeline_log_key(user_id: int | str) -> str:
    return f"user:{user_id}:pipeline_log"


def user_allowed_chats_key(user_id: int | str) -> str:
    return f"user:{user_id}:allowed_chats"


def user_listen_scope_key(user_id: int | str) -> str:
    return f"user:{user_id}:listen_scope"


BOT_LINK_TTL_SECONDS = 300


def bot_link_key(token: str) -> str:
    return f"bot_link:{token}"


ALLOWED_CHATS_TTL_SECONDS = 6 * 60 * 60


def listener_heartbeat_key() -> str:
    return "service:listener:heartbeat"


def processor_heartbeat_key() -> str:
    return "service:processor:heartbeat"


def get_redis_pool() -> ConnectionPool:
    """Create or return the shared async Redis connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool.from_url(
            settings.resolved_redis_url,
            decode_responses=True,
            max_connections=20,
            protocol=2,
        )
    return _pool


def get_redis_client() -> Redis:
    """Create or return the shared async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis(connection_pool=get_redis_pool())
    return _redis_client


def get_sync_redis() -> sync_redis.Redis:
    """Shared sync Redis client — same URL as async pool (Celery + API writes)."""
    global _sync_redis_client
    if _sync_redis_client is None:
        settings = get_settings()
        _sync_redis_client = sync_redis.Redis.from_url(
            settings.resolved_redis_url,
            decode_responses=True,
            protocol=2,
        )
    return _sync_redis_client


def sync_user_keywords_payload(user_id: int, payload: dict[str, Any]) -> int:
    """Write merged keywords to Redis and verify the round-trip."""
    client = get_sync_redis()
    cache_key = user_keywords_key(user_id)
    serialized = json.dumps(payload, ensure_ascii=False)
    client.set(cache_key, serialized)
    raw = client.get(cache_key)
    if not raw:
        raise RuntimeError(f"Redis keyword cache verification failed for {cache_key}")
    stored = json.loads(raw)
    words = stored.get("final_keywords") or stored.get("keywords") or []
    if not isinstance(words, list):
        raise RuntimeError("Redis keyword cache payload is invalid")
    return len(words)


def read_user_keyword_count(user_id: int) -> int:
    """Return cached final keyword count for a user."""
    client = get_sync_redis()
    for cache_key in (user_keywords_key(user_id), f"user:keywords:{user_id}"):
        raw = client.get(cache_key)
        if not raw:
            continue
        data = json.loads(raw)
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            words = data.get("final_keywords") or data.get("keywords") or []
            return len(words) if isinstance(words, list) else 0
    return 0


def sync_user_status(user_id: int, engine_active: bool, license_valid: bool) -> None:
    client = get_sync_redis()
    client.set(
        user_status_key(user_id),
        json.dumps(
            {"engine_active": engine_active, "license_valid": license_valid},
            ensure_ascii=False,
        ),
    )


def read_user_status(user_id: int) -> dict[str, bool]:
    client = get_sync_redis()
    raw = client.get(user_status_key(user_id))
    if not raw:
        return {"engine_active": False, "license_valid": False}
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {"engine_active": False, "license_valid": False}
    return {
        "engine_active": bool(data.get("engine_active")),
        "license_valid": bool(data.get("license_valid")),
    }


def sync_listen_scope(
    user_id: int,
    *,
    mode: str,
    folder_id: int | None = None,
    folder_title: str | None = None,
    chat_ids: set[int] | None = None,
) -> int:
    """Persist listen scope JSON and optional Redis SET of allowed chat IDs."""
    client = get_sync_redis()
    scope = {
        "mode": mode,
        "folder_id": folder_id,
        "folder_title": folder_title,
        "chat_count": len(chat_ids) if chat_ids is not None else None,
    }
    client.set(user_listen_scope_key(user_id), json.dumps(scope, ensure_ascii=False))
    chats_key = user_allowed_chats_key(user_id)
    client.delete(chats_key)
    if mode != "folder":
        return 0
    members = [str(chat_id) for chat_id in sorted(chat_ids or [])]
    if members:
        client.sadd(chats_key, *members)
        client.expire(chats_key, ALLOWED_CHATS_TTL_SECONDS)
    return len(members)


def read_listen_scope(user_id: int) -> dict[str, Any]:
    client = get_sync_redis()
    raw = client.get(user_listen_scope_key(user_id))
    if not raw:
        return {"mode": "all", "folder_id": None, "folder_title": None, "chat_count": None}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"mode": "all", "folder_id": None, "folder_title": None, "chat_count": None}
    if not isinstance(data, dict):
        return {"mode": "all", "folder_id": None, "folder_title": None, "chat_count": None}
    return {
        "mode": data.get("mode") or "all",
        "folder_id": data.get("folder_id"),
        "folder_title": data.get("folder_title"),
        "chat_count": data.get("chat_count"),
    }


def clear_listen_scope(user_id: int) -> None:
    client = get_sync_redis()
    client.delete(user_listen_scope_key(user_id), user_allowed_chats_key(user_id))


def is_chat_allowed(user_id: int | None, chat_id: int | None) -> bool:
    """Fast Redis SISMEMBER check; mode=all (or missing scope) allows every chat."""
    if user_id is None:
        return True
    scope = read_listen_scope(user_id)
    if scope.get("mode") != "folder":
        return True
    if chat_id is None:
        return False
    client = get_sync_redis()
    return bool(client.sismember(user_allowed_chats_key(user_id), str(chat_id)))


def should_ingest_message(
    user_id: int | None,
    chat_id: int | None,
    *,
    is_group: bool,
    is_channel: bool,
    is_private: bool,
) -> bool:
    """Folder-scoped SISMEMBER, otherwise only groups/channels (legacy 'all' mode)."""
    if user_id is None:
        return bool(is_group or is_channel)
    scope = read_listen_scope(user_id)
    if scope.get("mode") != "folder":
        return bool(is_group or is_channel)
    if chat_id is None:
        return False
    client = get_sync_redis()
    if not client.sismember(user_allowed_chats_key(user_id), str(chat_id)):
        return False
    return bool(is_group or is_channel or is_private)


def publish_engine_control(action: str, user_id: int) -> None:
    client = get_sync_redis()
    message = json.dumps(
        {"action": action, "user_id": user_id, "ts": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False,
    )
    client.publish(ENGINE_CONTROL_CHANNEL, message)


def append_pipeline_log(user_id: int, entry: dict[str, Any]) -> None:
    client = get_sync_redis()
    key = user_pipeline_log_key(user_id)
    payload = {
        **entry,
        "timestamp": entry.get("timestamp") or datetime.now(timezone.utc).isoformat(),
    }
    client.lpush(key, json.dumps(payload, ensure_ascii=False))
    client.ltrim(key, 0, PIPELINE_LOG_MAX_ENTRIES - 1)


def read_pipeline_log(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    client = get_sync_redis()
    raw_items = client.lrange(user_pipeline_log_key(user_id), 0, max(0, limit - 1))
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                items.append(parsed)
        except json.JSONDecodeError:
            continue
    return items


def service_heartbeat_age_seconds(key: str) -> float | None:
    client = get_sync_redis()
    raw = client.get(key)
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except ValueError:
        return None


async def close_redis() -> None:
    """Gracefully close Redis connections on shutdown."""
    global _redis_client, _pool, _sync_redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    if _pool is not None:
        await _pool.aclose()
        _pool = None
    if _sync_redis_client is not None:
        _sync_redis_client.close()
        _sync_redis_client = None
