"""Telethon client startup entry point for the listener service."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.cache import ENGINE_CONTROL_CHANNEL, get_sync_redis, listener_heartbeat_key
from core.database import get_session_factory
from core.logger import setup_logging
from modules.listener.auth import _disconnect_client, load_client
from modules.listener.handlers import register_handlers
from modules.listener.producer import close_producer
from shared.models import TelegramSession

logger = setup_logging(__name__)

POLL_INTERVAL_SECONDS = 5
HEARTBEAT_INTERVAL_SECONDS = 15


async def _fetch_engine_session() -> TelegramSession | None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = (
            select(TelegramSession)
            .options(selectinload(TelegramSession.user))
            .where(
                TelegramSession.is_active.is_(True),
                TelegramSession.is_engine_active.is_(True),
            )
            .order_by(TelegramSession.id)
        )
        result = await db.execute(stmt)
        return result.scalars().first()


async def _session_still_active(session_id: int) -> bool:
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = select(TelegramSession).where(
            TelegramSession.id == session_id,
            TelegramSession.is_active.is_(True),
            TelegramSession.is_engine_active.is_(True),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None


async def _write_heartbeat(stop_event: asyncio.Event) -> None:
    client = get_sync_redis()
    while not stop_event.is_set():
        client.set(listener_heartbeat_key(), datetime.now(timezone.utc).isoformat())
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue


async def _watch_control_channel(stop_event: asyncio.Event) -> None:
    client = get_sync_redis()
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(ENGINE_CONTROL_CHANNEL)
    try:
        while not stop_event.is_set():
            message = await asyncio.to_thread(pubsub.get_message, timeout=1.0)
            if not message or message.get("type") != "message":
                await asyncio.sleep(0.2)
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            action = payload.get("action")
            if action in {"start", "stop"}:
                logger.info("Engine control signal received: %s", payload)
                stop_event.set()
                break
    finally:
        pubsub.close()


async def _watch_session_state(session_id: int, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        if not await _session_still_active(session_id):
            logger.info("Engine deactivated for session %s — stopping listener.", session_id)
            stop_event.set()
            break


async def _run_listener_session(session_record: TelegramSession) -> None:
    logger.info("Loading active session for phone: %s", session_record.phone_number)
    client = await load_client(session_record.session_string)
    stop_event = asyncio.Event()

    owner = session_record.user
    register_handlers(
        client,
        session_record.session_string,
        user_id=session_record.user_id,
        business_type=owner.business_type if owner else None,
    )

    heartbeat_task = asyncio.create_task(_write_heartbeat(stop_event))
    control_task = asyncio.create_task(_watch_control_channel(stop_event))
    state_task = asyncio.create_task(_watch_session_state(session_record.id, stop_event))
    runner_task = asyncio.create_task(client.run_until_disconnected())  # type: ignore[attr-defined]

    logger.info("Listener is running and watching Telegram group messages...")
    await stop_event.wait()

    if client.is_connected():
        await client.disconnect()
    for task in (runner_task, heartbeat_task, control_task, state_task):
        task.cancel()
    await asyncio.gather(runner_task, heartbeat_task, control_task, state_task, return_exceptions=True)
    await _disconnect_client(client)


async def main() -> None:
    """Wait for engine-active sessions and run the Telethon listener loop."""
    logger.info("Listener service starting...")
    try:
        while True:
            session_record = await _fetch_engine_session()
            if session_record is None:
                logger.info("No engine-active TelegramSession yet. Waiting for dashboard start...")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue
            await _run_listener_session(session_record)
            logger.info("Listener cycle finished. Checking for next engine-active session...")
            await asyncio.sleep(2)
    finally:
        await close_producer()


if __name__ == "__main__":
    asyncio.run(main())
