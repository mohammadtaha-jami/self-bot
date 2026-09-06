"""Unit and smoke tests for the Phase 7.4 AI engine."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import get_settings
from modules.ai_engine.classifier import (
    IntentClassifier,
    get_classifier,
    is_actionable_hiring_lead,
    predict_intent,
)
from modules.ai_engine.fallback import fallback_to_keywords
from modules.ai_engine.labels import IntentEnum
from modules.ai_engine.schemas import (
    SOURCE_DISABLED,
    SOURCE_EMPTY,
    SOURCE_ERROR,
    SOURCE_KEYWORDS,
    SOURCE_ONNX,
    PredictionResult,
)
from modules.ai_engine.tokenizer import Tokenizer

REPO_ROOT = Path(__file__).resolve().parents[1]
ONNX_PATH = REPO_ROOT / "models" / "parsbert_classifier" / "model_quantized.onnx"
TOKENIZER_PATH = REPO_ROOT / "models" / "parsbert_classifier" / "tokenizer.json"


class FallbackTests(unittest.TestCase):
    def test_hiring_keywords_map_to_hiring_lead(self) -> None:
        result = fallback_to_keywords("استخدام برنامه‌نویس پایتون تمام‌وقت با بیمه")
        self.assertEqual(result.label, IntentEnum.HIRING_LEAD)
        self.assertEqual(result.source, SOURCE_KEYWORDS)
        self.assertGreater(result.confidence, 0.8)

    def test_seeking_keywords_map_to_seeking_job(self) -> None:
        result = fallback_to_keywords("فریلنسر هستم و آماده همکاری پروژه‌ای می‌باشم")
        self.assertEqual(result.label, IntentEnum.SEEKING_JOB)
        self.assertEqual(result.source, SOURCE_KEYWORDS)

    def test_unrelated_text_is_spam(self) -> None:
        result = fallback_to_keywords("امشب استریم بازی داریم بیاین باهم بازی کنیم")
        self.assertEqual(result.label, IntentEnum.SPAM_OTHER)
        self.assertEqual(result.source, SOURCE_KEYWORDS)

    def test_custom_keywords_win_as_hiring_lead(self) -> None:
        result = fallback_to_keywords(
            "کسی میتونه ربات تلگرام برام بزنه؟",
            keywords=["کسی میتونه ربات"],
        )
        self.assertEqual(result.label, IntentEnum.HIRING_LEAD)
        self.assertEqual(result.source, SOURCE_KEYWORDS)


class TokenizerTests(unittest.TestCase):
    @unittest.skipUnless(TOKENIZER_PATH.is_file(), "tokenizer files are not present")
    def test_encode_shapes_and_special_tokens(self) -> None:
        tokenizer = Tokenizer(TOKENIZER_PATH.parent)
        encoded = tokenizer.encode("استخدام برنامه‌نویس")
        self.assertEqual(encoded["input_ids"].shape, (1, 128))
        self.assertEqual(encoded["attention_mask"].shape, (1, 128))
        self.assertEqual(int(encoded["input_ids"][0, 0]), 2)
        self.assertEqual(encoded["input_ids"].dtype, encoded["attention_mask"].dtype)


class ClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        IntentClassifier.reset_instance()
        get_settings.cache_clear()

    def tearDown(self) -> None:
        IntentClassifier.reset_instance()
        get_settings.cache_clear()
        os.environ.pop("AI_ENABLED", None)
        os.environ.pop("AI_FALLBACK_TO_KEYWORDS", None)

    def test_singleton_identity(self) -> None:
        self.assertIs(IntentClassifier(), get_classifier())
        self.assertIs(get_classifier(), get_classifier())

    def test_empty_text_skips_model(self) -> None:
        result = get_classifier().predict("   ")
        self.assertEqual(result.label, IntentEnum.SPAM_OTHER)
        self.assertEqual(result.source, SOURCE_EMPTY)
        self.assertGreaterEqual(result.latency_ms, 0.0)

    def test_disabled_without_fallback(self) -> None:
        os.environ["AI_ENABLED"] = "false"
        os.environ["AI_FALLBACK_TO_KEYWORDS"] = "false"
        get_settings.cache_clear()
        IntentClassifier.reset_instance()
        result = get_classifier().predict("استخدام برنامه‌نویس")
        self.assertEqual(result.label, IntentEnum.SPAM_OTHER)
        self.assertEqual(result.source, SOURCE_DISABLED)

    def test_disabled_uses_keyword_fallback(self) -> None:
        os.environ["AI_ENABLED"] = "false"
        os.environ["AI_FALLBACK_TO_KEYWORDS"] = "true"
        get_settings.cache_clear()
        IntentClassifier.reset_instance()
        result = get_classifier().predict("استخدام ادمین اینستاگرام تمام‌وقت")
        self.assertEqual(result.label, IntentEnum.HIRING_LEAD)
        self.assertEqual(result.source, SOURCE_KEYWORDS)

    def test_inference_error_falls_back_to_keywords(self) -> None:
        classifier = get_classifier()
        with patch.object(classifier, "_predict_onnx", side_effect=RuntimeError("boom")):
            result = classifier.predict("نیازمند متخصص سئو هستیم")
        self.assertEqual(result.label, IntentEnum.HIRING_LEAD)
        self.assertEqual(result.source, SOURCE_KEYWORDS)

    def test_inference_error_without_fallback(self) -> None:
        os.environ["AI_FALLBACK_TO_KEYWORDS"] = "false"
        get_settings.cache_clear()
        IntentClassifier.reset_instance()
        classifier = get_classifier()
        with patch.object(classifier, "_predict_onnx", side_effect=RuntimeError("boom")):
            result = classifier.predict("نیازمند متخصص سئو هستیم")
        self.assertEqual(result.label, IntentEnum.SPAM_OTHER)
        self.assertEqual(result.source, SOURCE_ERROR)

    @unittest.skipUnless(ONNX_PATH.is_file(), "ONNX weights are not present")
    def test_onnx_predicts_three_classes(self) -> None:
        classifier = get_classifier()
        cases = [
            (IntentEnum.SPAM_OTHER, "سلام بچه‌ها کسی میدونه بهترین لپ‌تاپ برای ادیت ویدیو چیه؟"),
            (
                IntentEnum.SEEKING_JOB,
                "برنامه‌نویس بک‌اند هستم با ۲ سال تجربه. آماده همکاری پروژه‌ای هستم.",
            ),
            (
                IntentEnum.HIRING_LEAD,
                "استخدام ادمین حرفه‌ای اینستاگرام، تمام‌وقت، حقوق توافقی + بیمه.",
            ),
        ]
        for expected, text in cases:
            with self.subTest(expected=expected.name):
                result = classifier.predict(text)
                self.assertEqual(result.source, SOURCE_ONNX)
                self.assertEqual(result.label, expected)
                self.assertGreater(result.confidence, 0.9)
                self.assertGreater(result.latency_ms, 0.0)


class ActionableHiringLeadTests(unittest.TestCase):
    def test_hiring_at_threshold_is_actionable(self) -> None:
        result = PredictionResult(
            label=IntentEnum.HIRING_LEAD,
            confidence=0.75,
            latency_ms=10.0,
            source=SOURCE_ONNX,
        )
        self.assertTrue(is_actionable_hiring_lead(result, threshold=0.75))

    def test_hiring_below_threshold_is_rejected(self) -> None:
        result = PredictionResult(
            label=IntentEnum.HIRING_LEAD,
            confidence=0.749,
            latency_ms=10.0,
            source=SOURCE_ONNX,
        )
        self.assertFalse(is_actionable_hiring_lead(result, threshold=0.75))

    def test_seeking_job_is_never_actionable(self) -> None:
        result = PredictionResult(
            label=IntentEnum.SEEKING_JOB,
            confidence=0.99,
            latency_ms=10.0,
            source=SOURCE_ONNX,
        )
        self.assertFalse(is_actionable_hiring_lead(result, threshold=0.75))

    def test_spam_is_never_actionable(self) -> None:
        result = PredictionResult(
            label=IntentEnum.SPAM_OTHER,
            confidence=0.99,
            latency_ms=8.0,
            source=SOURCE_ONNX,
        )
        self.assertFalse(is_actionable_hiring_lead(result, threshold=0.75))


class PredictIntentTests(unittest.TestCase):
    def tearDown(self) -> None:
        IntentClassifier.reset_instance()

    def test_predict_intent_uses_singleton_classifier(self) -> None:
        classifier = get_classifier()
        expected = PredictionResult(
            label=IntentEnum.HIRING_LEAD,
            confidence=0.91,
            latency_ms=11.0,
            source=SOURCE_ONNX,
        )
        with patch.object(classifier, "predict", return_value=expected) as predict:
            result = predict_intent("استخدام برنامه‌نویس", keywords=["استخدام"])
        self.assertIs(result, expected)
        predict.assert_called_once_with(
            "استخدام برنامه‌نویس",
            keywords=["استخدام"],
            negative_keywords=None,
        )


class SampleSeparationTests(unittest.TestCase):
    @unittest.skipUnless(ONNX_PATH.is_file(), "ONNX weights are not present")
    def test_separates_hiring_seeking_and_spam(self) -> None:
        samples = [
            (
                IntentEnum.HIRING_LEAD,
                "استخدام ادمین حرفه‌ای اینستاگرام، تمام‌وقت، حقوق توافقی + بیمه.",
            ),
            (
                IntentEnum.HIRING_LEAD,
                "نیازمند یک متخصص سئو برای بهبود رتبه سایت فروشگاهی هستیم.",
            ),
            (
                IntentEnum.SEEKING_JOB,
                "برنامه‌نویس بک‌اند هستم با ۲ سال تجربه. آماده همکاری پروژه‌ای هستم.",
            ),
            (
                IntentEnum.SEEKING_JOB,
                "طراح UI/UX با ۳ سال سابقه هستم. نمونه کار در پیوی موجوده.",
            ),
            (
                IntentEnum.SPAM_OTHER,
                "سلام بچه‌ها کسی میدونه بهترین لپ‌تاپ برای ادیت ویدیو چیه؟",
            ),
            (
                IntentEnum.SPAM_OTHER,
                "فروش ویژه فالوور اینستاگرام + لایک ایرانی، تحویل فوری.",
            ),
        ]
        classifier = get_classifier()
        for expected, text in samples:
            with self.subTest(expected=expected.name, text=text[:40]):
                result = classifier.predict(text)
                self.assertEqual(result.source, SOURCE_ONNX)
                self.assertEqual(result.label, expected)
                self.assertGreaterEqual(result.confidence, 0.75)


if __name__ == "__main__":
    unittest.main()

