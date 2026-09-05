"""HTML formatting and inline keyboards for notifier Bot API messages."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_TEHRAN = ZoneInfo("Asia/Tehran")


def _escape_html(value: object) -> str:
    return html.escape(str(value), quote=False)


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_created_at_fa(value: object) -> str:
    """Format message timestamp for display in Tehran timezone."""
    local = _parse_datetime(value).astimezone(_TEHRAN)
    return local.strftime("%Y/%m/%d - %H:%M")


def build_message_link(payload: dict) -> str | None:
    """Direct link to the source Telegram message."""
    message_id = payload.get("message_id")
    if message_id is None:
        return None

    chat_username = payload.get("chat_username")
    if chat_username:
        username = str(chat_username).lstrip("@")
        return f"https://t.me/{username}/{message_id}"

    chat_id = payload.get("chat_id")
    if chat_id is None:
        return None

    cid = str(chat_id)
    if cid.startswith("-100"):
        internal = cid[4:]
    elif cid.startswith("-"):
        internal = cid[1:]
    else:
        internal = cid
    return f"https://t.me/c/{internal}/{message_id}"


def build_sender_link(payload: dict) -> str | None:
    """Deep link to the message author's Telegram profile."""
    sender_username = payload.get("sender_username")
    if sender_username:
        return f"https://t.me/{str(sender_username).lstrip('@')}"

    sender_id = payload.get("sender_id")
    if sender_id is not None:
        return f"tg://user?id={int(sender_id)}"
    return None


def format_lead_message(payload: dict, lead_data: dict) -> str:
    """Build HTML notification text for the notifier bot."""
    keywords = lead_data.get("matched_keywords") or []
    keyword = "، ".join(str(k) for k in keywords) if keywords else "—"
    group_title = payload.get("chat_title") or "گروه ناشناس"
    created_at_fa = format_created_at_fa(payload.get("date"))
    message_text = payload.get("text") or ""

    return (
        "🎯 <b>فرصت شغلی / پروژه جدید یافت شد!</b>\n\n"
        f"🔑 <b>کلمه کلیدی:</b> <code>{_escape_html(keyword)}</code>\n"
        f"👥 <b>گروه مبدا:</b> {_escape_html(group_title)}\n"
        f"⏰ <b>زمان:</b> {_escape_html(created_at_fa)}\n\n"
        "📝 <b>متن پیام:</b>\n"
        f"<blockquote>{_escape_html(message_text)}</blockquote>"
    )


def build_inline_keyboard(payload: dict) -> dict:
    """Telegram Bot API inline keyboard JSON for a lead alert."""
    row: list[dict[str, str]] = []

    message_link = build_message_link(payload)
    if message_link:
        row.append({"text": "🔗 مشاهده پیام در گروه", "url": message_link})

    sender_link = build_sender_link(payload)
    if sender_link:
        row.append({"text": "👤 گفتگو با کارفرما", "url": sender_link})

    if not row:
        return {"inline_keyboard": []}
    return {"inline_keyboard": [row]}
