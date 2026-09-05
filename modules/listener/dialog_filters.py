"""Fetch Telegram Dialog Filters (chat folders) and extract chat IDs."""

from __future__ import annotations

from typing import Any

from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.utils import get_peer_id

from core.logger import setup_logging

logger = setup_logging(__name__)


def _filter_title(item: Any) -> str:
    title = getattr(item, "title", None)
    if title is None:
        return ""
    if hasattr(title, "text"):
        return str(title.text or "").strip()
    return str(title).strip()


def collect_peer_ids(peer: Any) -> set[int]:
    """Normalize a Telethon peer to IDs that can match event.chat_id."""
    ids: set[int] = set()
    try:
        ids.add(int(get_peer_id(peer)))
    except Exception:
        pass
    channel_id = getattr(peer, "channel_id", None)
    chat_id = getattr(peer, "chat_id", None)
    user_id = getattr(peer, "user_id", None)
    if channel_id is not None:
        cid = int(channel_id)
        ids.add(cid)
        ids.add(int(f"-100{cid}"))
    if chat_id is not None:
        gid = int(chat_id)
        ids.add(gid)
        ids.add(-gid)
    if user_id is not None:
        ids.add(int(user_id))
    return {i for i in ids if i}


async def fetch_dialog_filter_items(client: TelegramClient) -> list[Any]:
    raw = await client(GetDialogFiltersRequest())
    items = getattr(raw, "filters", raw)
    if items is None:
        return []
    return list(items)


def summarize_dialog_filters(items: list[Any]) -> list[dict[str, Any]]:
    """User-created folders only (skip DialogFilterDefault / All chats)."""
    folders: list[dict[str, Any]] = []
    for item in items:
        kind = type(item).__name__
        if kind == "DialogFilterDefault":
            continue
        folder_id = getattr(item, "id", None)
        if folder_id is None:
            continue
        title = _filter_title(item) or f"پوشه {folder_id}"
        folders.append({"id": int(folder_id), "title": title, "kind": kind})
    return folders


def find_dialog_filter(items: list[Any], folder_id: int) -> Any | None:
    for item in items:
        current_id = getattr(item, "id", None)
        if current_id is not None and int(current_id) == int(folder_id):
            return item
    return None


async def extract_folder_chat_ids(client: TelegramClient, dialog_filter: Any) -> set[int]:
    """Chat IDs from pinned/include peers, minus exclude; type-flag fallback."""
    ids: set[int] = set()
    exclude: set[int] = set()
    for peer in list(getattr(dialog_filter, "exclude_peers", None) or []):
        exclude |= collect_peer_ids(peer)
    for attr in ("pinned_peers", "include_peers"):
        for peer in list(getattr(dialog_filter, attr, None) or []):
            ids |= collect_peer_ids(peer)
    ids -= exclude
    if ids:
        return ids

    want_groups = bool(getattr(dialog_filter, "groups", False))
    want_broadcasts = bool(getattr(dialog_filter, "broadcasts", False))
    if not (want_groups or want_broadcasts):
        return ids

    logger.info("Folder has no explicit peers; scanning dialogs by type flags")
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        is_broadcast = bool(getattr(entity, "broadcast", False))
        if want_broadcasts and (dialog.is_channel and is_broadcast):
            ids |= collect_peer_ids(entity)
        elif want_groups and dialog.is_group and not is_broadcast:
            ids |= collect_peer_ids(entity)
    return ids - exclude
