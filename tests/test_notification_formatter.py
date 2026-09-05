"""Notification formatter and keyboard helpers."""

from modules.notification.formatter import (
    build_inline_keyboard,
    build_message_link,
    build_sender_link,
    format_lead_message,
)


def test_format_lead_message_html_structure():
    payload = {
        "chat_title": "گروه تست",
        "text": "نیاز به برنامه‌نویس",
        "message_id": 42,
        "chat_id": -1001234567890,
        "sender_id": 987654321,
        "sender_username": "employer",
        "date": "2026-09-05T08:00:00+00:00",
    }
    lead_data = {"matched_keywords": ["برنامه‌نویس"]}
    text = format_lead_message(payload, lead_data)
    assert "<b>" in text
    assert "<blockquote>" in text
    assert "برنامه‌نویس" in text


def test_inline_keyboard_links():
    payload = {
        "message_id": 10,
        "chat_username": "mygroup",
        "sender_username": "boss",
        "sender_id": 1,
    }
    keyboard = build_inline_keyboard(payload)
    row = keyboard["inline_keyboard"][0]
    assert row[0]["url"] == "https://t.me/mygroup/10"
    assert row[1]["url"] == "https://t.me/boss"


def test_message_link_private_supergroup():
    payload = {"message_id": 5, "chat_id": -1009876543210}
    assert build_message_link(payload) == "https://t.me/c/9876543210/5"


def test_sender_link_without_username():
    payload = {"sender_id": 555}
    assert build_sender_link(payload) == "tg://user?id=555"
