"""End-to-end scenario test: 15 real messages through the Celery pipeline."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.ai_engine import predict_intent  # noqa: E402
from modules.processor.tasks import process_raw_message  # noqa: E402

SCENARIO_KEYWORDS = [
    "استخدام",
    "نیازمند",
    "برنامه‌نویس",
    "فریلنسر",
    "سئو",
    "طراح",
    "ادمین",
    "پروژه",
    "ربات",
    "رزومه",
    "همکاری",
    "فروش",
    "سیگنال",
    "لپ‌تاپ",
]

SAMPLES: list[tuple[str, str]] = [
    (
        "استخدام ادمین حرفه‌ای اینستاگرام با سابقه کاری مشخص، تمام‌وقت، حقوق توافقی + بیمه.",
        "HIRING_LEAD",
    ),
    (
        "نیازمند یک متخصص سئو برای بهبود رتبه سایت فروشگاهی هستیم. همکاری بلندمدت. حقوق ثابت + پاداش عملکرد.",
        "HIRING_LEAD",
    ),
    (
        "به یک طراح UI/UX مسلط به Figma جهت طراحی اپلیکیشن فروشگاهی نیازمندیم.",
        "HIRING_LEAD",
    ),
    (
        "پروژه فوری توسعه ربات تلگرامی با پایتون نیاز داریم. مهلت تحویل ۵ روز.",
        "HIRING_LEAD",
    ),
    (
        "به یک برنامه‌نویس فرانت‌اند مسلط به React جهت همکاری در پروژه استارتاپی نیازمندیم.",
        "HIRING_LEAD",
    ),
    (
        "برنامه‌نویس بک‌اند هستم با ۲ سال تجربه در Node.js. آماده همکاری پروژه‌ای یا تمام‌وقت هستم.",
        "SEEKING_JOB",
    ),
    (
        "طراح UI/UX با ۳ سال سابقه کار روی اپلیکیشن‌های موبایل هستم. نمونه کار در پیوی موجوده.",
        "SEEKING_JOB",
    ),
    (
        "#انجام_دهنده نگارش مقاله علمی و پایان‌نامه. تحلیل آماری با SPSS. هماهنگی در پیوی.",
        "SEEKING_JOB",
    ),
    (
        "توسعه‌دهنده فول‌استک هستم (Laravel + Vue)، دنبال پروژه پاره وقت میگردم، نمونه کارها آماده ارسال.",
        "SEEKING_JOB",
    ),
    (
        "فریلنسر هستم و رزومه دارم، دنبال کار پاره‌وقت می‌گردم، نمونه کار آماده ارسال.",
        "SEEKING_JOB",
    ),
    (
        "فروش ویژه فالوور اینستاگرام + لایک ایرانی، تحویل فوری، قیمت استثنایی!",
        "SPAM_OTHER",
    ),
    (
        "کانال VIP سیگنال بورس تهران امروز رایگان، فردا پولی! عجله کن عضو شو.",
        "SPAM_OTHER",
    ),
    (
        "سلام بچه‌ها کسی میدونه بهترین لپ‌تاپ زیر ۲۰ میلیون برای ادیت ویدیو چیه؟",
        "SPAM_OTHER",
    ),
    (
        "استخدام در شرکت ما؟ نه! ما فقط دوره آموزشی میفروشیم، پس لطفا رزومه نفرستید.",
        "SPAM_OTHER",
    ),
    (
        "سلام، من دنبال همکار برای تیم بازی‌سازی نیستم، فقط میخوام بدونم یونیتی یاد بگیرم به دردم میخوره؟",
        "SPAM_OTHER",
    ),
]


def _clip(text: str, width: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= width:
        return compact
    return compact[: width - 1] + "…"


def _payload(index: int, text: str) -> dict:
    return {
        "message_id": 9000 + index,
        "text": text,
        "chat_title": "گروه سناریو ۷.۶",
        "chat_id": -100111222333,
        "sender_id": 700000 + index,
        "sender_username": f"sample_{index}",
        "user_id": 1,
        "keywords": SCENARIO_KEYWORDS,
        "negative_keywords": [],
        "date": "2026-09-06T10:00:00+00:00",
    }


def _run_pipeline(payload: dict) -> tuple[dict, bool]:
    send_task = MagicMock()
    with (
        patch(
            "modules.processor.tasks.get_user_engine_status",
            return_value={"engine_active": True, "license_valid": True},
        ),
        patch("modules.processor.tasks.get_user_keywords_cache", return_value=None),
        patch(
            "modules.processor.tasks.get_rules_for_business_types",
            return_value={"keywords": [], "negative_keywords": []},
        ),
        patch(
            "modules.processor.tasks.persist_matched_lead",
            new=MagicMock(),
        ),
        patch(
            "modules.processor.tasks.run_async_isolated",
            return_value=(101, 555000111, True),
        ),
        patch("modules.processor.tasks.celery_app.send_task", new=send_task),
        patch("modules.processor.tasks.format_lead_message", return_value="fmt"),
        patch("modules.processor.tasks.build_inline_keyboard", return_value={}),
    ):
        result = process_raw_message.run(payload)
    return result, send_task.called


def main() -> int:
    logging.getLogger("modules.processor.tasks").setLevel(logging.WARNING)
    logging.getLogger("modules.ai_engine.classifier").setLevel(logging.WARNING)

    rows: list[tuple[str, str, str, float, float, str, bool]] = []
    for index, (text, expected) in enumerate(SAMPLES, start=1):
        result, notified = _run_pipeline(_payload(index, text))
        label = result.get("ai_label_name")
        confidence = result.get("ai_confidence")
        latency = result.get("ai_latency_ms")
        if label is None:
            prediction = predict_intent(text, keywords=SCENARIO_KEYWORDS)
            label = prediction.label.name
            confidence = prediction.confidence
            latency = prediction.latency_ms
        rows.append(
            (
                text,
                expected,
                str(label),
                float(confidence),
                float(latency),
                "Yes" if notified else "No",
                str(label) == expected,
            )
        )

    text_w, class_w, conf_w, lat_w, notify_w = 46, 13, 10, 10, 12
    header = (
        f"{'#':<3} "
        f"{'متن':<{text_w}} "
        f"{'کلاس AI':<{class_w}} "
        f"{'اطمینان':<{conf_w}} "
        f"{'Latency':<{lat_w}} "
        f"{'نوتیفیکیشن':<{notify_w}}"
    )
    print("=== Phase 7.6 scenario test (process_raw_message) ===")
    print(header)
    print("-" * len(header))
    correct = 0
    notify_yes = 0
    for index, (text, expected, label, confidence, latency, notify, ok) in enumerate(
        rows, start=1
    ):
        correct += int(ok)
        notify_yes += int(notify == "Yes")
        mark = "✓" if ok else "✗"
        print(
            f"{index:<3} "
            f"{_clip(text, text_w):<{text_w}} "
            f"{label:<{class_w}} "
            f"{confidence:>8.3f}  "
            f"{latency:>7.1f}ms "
            f"{notify:<{notify_w}} {mark}"
        )

    print("-" * len(header))
    print(
        f"accuracy: {correct}/{len(rows)}  |  notifications: {notify_yes}/{len(rows)} "
        "(Yes only for HIRING_LEAD >= 0.75)"
    )
    return 0 if correct == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
