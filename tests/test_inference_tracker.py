"""Tests for the AI inference tracker."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from logger.tracker import log_inference


class TestTracker:
    def test_sent_when_hiring_above_threshold(self, tmp_path: Path) -> None:
        txt_path = tmp_path / "inference_tracker.txt"
        with patch("logger.tracker.TXT_PATH", txt_path), patch(
            "logger.tracker.LOGS_DIR", tmp_path
        ):
            record = log_inference(
                text="نیازمند برنامه‌نویس هستیم",
                matched_keyword="برنامه‌نویس",
                probabilities=[0.01, 0.04, 0.95],
                threshold=0.75,
            )
        assert record is not None
        assert record["status"] == "SENT_NOTIFICATION"
        assert record["predicted_label"] == "HIRING_LEAD"
        assert record["matched_keyword"] == "برنامه‌نویس"
        saved = txt_path.read_text(encoding="utf-8")
        assert "predicted_label: HIRING_LEAD" in saved
        assert "HIRING_LEAD=0.9500" in saved
        assert "status: SENT_NOTIFICATION" in saved

    def test_rejected_when_spam_wins(self, tmp_path: Path) -> None:
        txt_path = tmp_path / "inference_tracker.txt"
        with patch("logger.tracker.TXT_PATH", txt_path), patch(
            "logger.tracker.LOGS_DIR", tmp_path
        ):
            record = log_inference(
                text="ربات نیستم که جمعه هم برم",
                matched_keyword="ربات",
                probabilities=[0.82, 0.10, 0.08],
                threshold=0.75,
            )
        assert record is not None
        assert record["status"] == "REJECTED"
        assert record["predicted_label"] == "SPAM_OTHER"
        saved = txt_path.read_text(encoding="utf-8")
        assert "status: REJECTED" in saved
        assert "matched_keyword: ربات" in saved
