"""Celery pipeline tests for Phase 7.5 AI gate and metadata persistence."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from modules.ai_engine.labels import IntentEnum
from modules.ai_engine.schemas import SOURCE_ONNX, PredictionResult
from modules.processor.matching import MatchResult
from modules.processor.persist import build_lead_evidence
from modules.processor.tasks import process_raw_message
from shared.enums import LeadLevelEnum


def _payload(**overrides) -> dict:
    data = {
        "message_id": 42,
        "text": "استخدام برنامه‌نویس پایتون تمام‌وقت با بیمه",
        "chat_title": "گروه تست",
        "chat_id": -1001234567890,
        "sender_id": 987654321,
        "sender_username": "employer",
        "user_id": 7,
        "keywords": ["استخدام", "برنامه‌نویس"],
        "negative_keywords": [],
        "date": "2026-09-06T09:00:00+00:00",
    }
    data.update(overrides)
    return data


def _prediction(
    label: IntentEnum,
    confidence: float,
    latency_ms: float = 12.5,
) -> PredictionResult:
    return PredictionResult(
        label=label,
        confidence=confidence,
        latency_ms=latency_ms,
        source=SOURCE_ONNX,
    )


class ProcessRawMessageAIGateTests(unittest.TestCase):
    def _run(self, payload: dict, prediction: PredictionResult):
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
                "modules.processor.tasks.predict_intent",
                return_value=prediction,
            ) as predict,
            patch(
                "modules.processor.tasks.persist_matched_lead",
                new=MagicMock(),
            ) as persist_fn,
            patch(
                "modules.processor.tasks.run_async_isolated",
                return_value=(101, 555000, True),
            ) as isolated,
            patch("modules.processor.tasks.celery_app.send_task") as send_task,
            patch(
                "modules.processor.tasks.format_lead_message",
                return_value="formatted",
            ),
            patch(
                "modules.processor.tasks.build_inline_keyboard",
                return_value={"inline_keyboard": []},
            ),
        ):
            result = process_raw_message.run(payload)
        return result, predict, persist_fn, isolated, send_task

    def test_hiring_lead_above_threshold_persists_and_notifies(self) -> None:
        prediction = _prediction(IntentEnum.HIRING_LEAD, 0.92, latency_ms=18.0)
        result, predict, persist_fn, isolated, send_task = self._run(
            _payload(),
            prediction,
        )

        self.assertEqual(result["status"], "lead_created")
        self.assertEqual(result["lead_id"], 101)
        self.assertEqual(result["ai_label"], 2)
        self.assertEqual(result["ai_label_name"], "HIRING_LEAD")
        self.assertEqual(result["ai_confidence"], 0.92)
        self.assertEqual(result["ai_latency_ms"], 18.0)
        predict.assert_called_once()
        persist_fn.assert_called_once()
        isolated.assert_called_once()
        _payload_arg, match_result, stored_prediction = persist_fn.call_args.args
        self.assertTrue(match_result.matched)
        self.assertIs(stored_prediction, prediction)
        send_task.assert_called_once()
        self.assertEqual(send_task.call_args.args[0], "tasks.publish_lead_notification")

    def test_hiring_lead_at_threshold_is_accepted(self) -> None:
        result, _predict, persist_fn, isolated, send_task = self._run(
            _payload(),
            _prediction(IntentEnum.HIRING_LEAD, 0.75),
        )
        self.assertEqual(result["status"], "lead_created")
        persist_fn.assert_called_once()
        isolated.assert_called_once()
        send_task.assert_called_once()

    def test_hiring_lead_below_threshold_is_ignored(self) -> None:
        result, predict, persist_fn, isolated, send_task = self._run(
            _payload(),
            _prediction(IntentEnum.HIRING_LEAD, 0.749),
        )
        self.assertEqual(result["status"], "ignored")
        self.assertEqual(result["reason"], "ai_not_hiring_lead")
        self.assertEqual(result["ai_label_name"], "HIRING_LEAD")
        self.assertEqual(result["ai_confidence"], 0.749)
        predict.assert_called_once()
        persist_fn.assert_not_called()
        isolated.assert_not_called()
        send_task.assert_not_called()

    def test_seeking_job_is_ignored_even_with_high_confidence(self) -> None:
        result, _predict, persist_fn, isolated, send_task = self._run(
            _payload(),
            _prediction(IntentEnum.SEEKING_JOB, 0.99),
        )
        self.assertEqual(result["status"], "ignored")
        self.assertEqual(result["reason"], "ai_not_hiring_lead")
        self.assertEqual(result["ai_label"], 1)
        self.assertEqual(result["ai_label_name"], "SEEKING_JOB")
        persist_fn.assert_not_called()
        isolated.assert_not_called()
        send_task.assert_not_called()

    def test_spam_other_is_ignored(self) -> None:
        result, _predict, persist_fn, isolated, send_task = self._run(
            _payload(),
            _prediction(IntentEnum.SPAM_OTHER, 0.99),
        )
        self.assertEqual(result["status"], "ignored")
        self.assertEqual(result["ai_label_name"], "SPAM_OTHER")
        persist_fn.assert_not_called()
        isolated.assert_not_called()
        send_task.assert_not_called()

    def test_keyword_miss_does_not_call_ai(self) -> None:
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
            patch("modules.processor.tasks.predict_intent") as predict,
            patch(
                "modules.processor.tasks.persist_matched_lead",
                new=MagicMock(),
            ) as persist_fn,
            patch("modules.processor.tasks.run_async_isolated") as isolated,
            patch("modules.processor.tasks.celery_app.send_task") as send_task,
        ):
            result = process_raw_message.run(
                _payload(text="امشب استریم بازی داریم", keywords=["استخدام"])
            )
        self.assertEqual(result["status"], "ignored")
        predict.assert_not_called()
        persist_fn.assert_not_called()
        isolated.assert_not_called()
        send_task.assert_not_called()


class LeadEvidenceTests(unittest.TestCase):
    def test_build_lead_evidence_includes_ai_fields(self) -> None:
        match_result = MatchResult(
            matched=True,
            lead_level=LeadLevelEnum.HOT,
            matched_keywords=["استخدام"],
            score=100.0,
            reason="matched",
        )
        prediction = _prediction(IntentEnum.HIRING_LEAD, 0.81, latency_ms=22.0)
        evidence = build_lead_evidence(
            {
                "chat_title": "گروه تست",
                "sender_username": "employer",
            },
            match_result,
            prediction,
        )
        self.assertEqual(evidence["matched_keywords"], ["استخدام"])
        self.assertEqual(evidence["ai_label"], 2)
        self.assertEqual(evidence["ai_label_name"], "HIRING_LEAD")
        self.assertEqual(evidence["ai_confidence"], 0.81)
        self.assertEqual(evidence["ai_latency_ms"], 22.0)
        self.assertEqual(evidence["ai_source"], SOURCE_ONNX)

    def test_build_lead_evidence_without_prediction(self) -> None:
        match_result = MatchResult(
            matched=True,
            lead_level=LeadLevelEnum.WARM,
            matched_keywords=["ربات"],
            score=90.0,
        )
        evidence = build_lead_evidence({"chat_title": "A"}, match_result)
        self.assertNotIn("ai_label", evidence)
        self.assertEqual(evidence["chat_title"], "A")


if __name__ == "__main__":
    unittest.main()
