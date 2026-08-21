"""Formatting utilities for building Telegram notification messages."""


def format_lead_message(payload: dict, lead_data: dict) -> str:
    """تبدیل اطلاعات لید به فرمت متنی شکیل برای تلگرام."""
    chat_title = payload.get("chat_title", "گروه ناشناس")
    chat_username = payload.get("chat_username")
    message_id = payload.get("message_id")
    sender_id = payload.get("sender_id", "ناشناس")
    sender_username = payload.get("sender_username")
    raw_text = payload.get("text", "")

    # ساخت لینک مستقیم به پیام
    if chat_username:
        msg_link = f"https://t.me/{chat_username}/{message_id}"
    else:
        msg_link = "لینک مستقیم در دسترس نیست"

    sender_info = f"@{sender_username}" if sender_username else f"`{sender_id}`"
    matched_keywords = ", ".join(lead_data.get("matched_keywords", []))
    score = lead_data.get("score", 0.0)
    lead_level = str(lead_data.get("lead_level", "NORMAL")).upper()

    return (
        f"🎯 **لید جدید شناسایی شد! [{lead_level}]**\n\n"
        f"👥 **گروه:** {chat_title}\n"
        f"👤 **فرستنده:** {sender_info}\n"
        f"📊 **امتیاز تطابق:** `{score:.1f}`\n"
        f"🔑 **کلمات کلیدی:** `{matched_keywords}`\n\n"
        f"💬 **متن پیام:**\n"
        f"« {raw_text} »\n\n"
        f"🔗 [مشاهده پیام در گروه]({msg_link})"
    )