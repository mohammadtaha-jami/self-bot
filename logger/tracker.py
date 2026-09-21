"""Safe AI inference tracker: console dump + TXT archive."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

from core.logger import setup_logging

logger = setup_logging(__name__)

LABEL_ORDER = (
    "SPAM_OTHER",
    "SEEKING_JOB",
    "HIRING_LEAD",
)
LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"
TXT_PATH = LOGS_DIR / "inference_tracker.txt"
DEFAULT_THRESHOLD = 0.75


def _as_probability_list(probabilities: Sequence[float] | np.ndarray) -> list[float]:
    values = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    if values.size < 3:
        padded = np.zeros(3, dtype=np.float64)
        padded[: values.size] = values
        values = padded
    return [float(values[0]), float(values[1]), float(values[2])]


def _winner(scores: dict[str, float]) -> str:
    return max(scores, key=lambda name: scores[name])


def _format_record(
    timestamp: str,
    text: str,
    matched_keyword: str,
    predicted_label: str,
    scores: dict[str, float],
    status: str,
    threshold: float,
) -> str:
    score_line = " ".join(
        f"{name}={scores[name]:.4f} ({scores[name] * 100:.2f}%)"
        for name in LABEL_ORDER
    )
    compact_text = " ".join((text or "").split())
    return (
        f"---------- {timestamp} ----------\n"
        f"text: {compact_text}\n"
        f"matched_keyword: {matched_keyword}\n"
        f"predicted_label: {predicted_label}\n"
        f"scores: {score_line}\n"
        f"status: {status}\n"
        f"threshold: {threshold:.2f}\n"
        "\n"
    )


def log_inference(
    text: str,
    matched_keyword: str,
    probabilities: Sequence[float] | np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict | None:
    """
    Log one ONNX inference without interrupting the worker.

    Returns the record dict on success, otherwise None.
    """
    try:
        probs = _as_probability_list(probabilities)
        scores = {
            LABEL_ORDER[0]: round(probs[0], 4),
            LABEL_ORDER[1]: round(probs[1], 4),
            LABEL_ORDER[2]: round(probs[2], 4),
        }
        predicted_label = _winner(scores)
        winner_score = scores[predicted_label]
        sent = predicted_label == "HIRING_LEAD" and winner_score >= float(threshold)
        status = "SENT_NOTIFICATION" if sent else "REJECTED"
        timestamp = datetime.now(timezone.utc).isoformat()

        print(
            "[AI Tracker] "
            f"keyword={matched_keyword!r} | "
            f"winner={predicted_label} ({winner_score * 100:.2f}%) | "
            f"SPAM_OTHER={scores[LABEL_ORDER[0]] * 100:.2f}% "
            f"SEEKING_JOB={scores[LABEL_ORDER[1]] * 100:.2f}% "
            f"HIRING_LEAD={scores[LABEL_ORDER[2]] * 100:.2f}% | "
            f"{status} | threshold={float(threshold) * 100:.0f}%"
        )

        record = {
            "timestamp": timestamp,
            "text": text,
            "matched_keyword": matched_keyword,
            "predicted_label": predicted_label,
            "scores": scores,
            "status": status,
            "threshold": float(threshold),
        }

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with TXT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(_format_record(**record))
        return record
    except Exception:
        logger.exception("AI inference tracker failed; worker continues")
        return None
