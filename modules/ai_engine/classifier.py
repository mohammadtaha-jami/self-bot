"""ONNX Intent classifier (ParsBERT) with keyword fallback."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import onnxruntime as ort

from core.config import get_settings
from core.logger import setup_logging
from modules.ai_engine.fallback import fallback_to_keywords
from modules.ai_engine.labels import IntentEnum
from modules.ai_engine.schemas import (
    SOURCE_DISABLED,
    SOURCE_EMPTY,
    SOURCE_ERROR,
    SOURCE_ONNX,
    PredictionResult,
)
from modules.ai_engine.tokenizer import Tokenizer

logger = setup_logging(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_model_dir(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return REPO_ROOT / path


def _find_onnx_file(model_dir: Path) -> Path:
    preferred = model_dir / "model_quantized.onnx"
    if preferred.is_file():
        return preferred
    matches = sorted(model_dir.glob("*.onnx"))
    if not matches:
        raise FileNotFoundError(f"No .onnx model found in {model_dir}")
    return matches[0]


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)
    exp = np.exp(shifted)
    return exp / exp.sum()


class IntentClassifier:
    """Singleton wrapper around the ONNX session and tokenizer."""

    _instance: IntentClassifier | None = None
    _lock = threading.Lock()

    def __new__(cls) -> IntentClassifier:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._session: ort.InferenceSession | None = None
            self._tokenizer: Tokenizer | None = None
            self._input_names: list[str] = []
            self._output_names: list[str] = []
            self._load_error: str | None = None
            self._initialized: bool = True

    @classmethod
    def reset_instance(cls) -> None:
        """Drop the singleton so the next call reloads settings and weights."""
        with cls._lock:
            cls._instance = None

    def _ensure_loaded(self) -> None:
        if self._session is not None and self._tokenizer is not None:
            return
        if self._load_error is not None:
            raise RuntimeError(self._load_error)

        settings = get_settings()
        model_dir = _resolve_model_dir(settings.ai_model_dir)
        try:
            onnx_path = _find_onnx_file(model_dir)
            options = ort.SessionOptions()
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            session = ort.InferenceSession(
                str(onnx_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
            tokenizer = Tokenizer(model_dir)
        except Exception as exc:
            self._load_error = str(exc)
            raise

        self._session = session
        self._tokenizer = tokenizer
        self._input_names = [item.name for item in session.get_inputs()]
        self._output_names = [item.name for item in session.get_outputs()]
        logger.info("Loaded ONNX intent classifier from %s", onnx_path)

    def _predict_onnx(self, text: str) -> PredictionResult:
        self._ensure_loaded()
        assert self._session is not None
        assert self._tokenizer is not None

        encoded = self._tokenizer.encode(text)
        feeds = {
            name: encoded[name]
            for name in self._input_names
            if name in encoded
        }
        raw = self._session.run(self._output_names, feeds)[0]
        logits = np.asarray(raw, dtype=np.float64)
        if logits.ndim > 1:
            logits = logits[0]

        probabilities = _softmax(logits)
        predicted = int(np.argmax(probabilities))
        try:
            label = IntentEnum(predicted)
        except ValueError as exc:
            raise RuntimeError(f"Unexpected class index {predicted}") from exc

        return PredictionResult(
            label=label,
            confidence=float(probabilities[predicted]),
            latency_ms=0.0,
            source=SOURCE_ONNX,
        )

    def _fallback(
        self,
        text: str,
        keywords: list[str] | None,
        negative_keywords: list[str] | None,
        reason: str,
    ) -> PredictionResult:
        logger.warning("AI classifier falling back to keywords: %s", reason)
        return fallback_to_keywords(
            text,
            keywords=keywords,
            negative_keywords=negative_keywords,
        )

    def predict(
        self,
        text: str,
        *,
        keywords: list[str] | None = None,
        negative_keywords: list[str] | None = None,
    ) -> PredictionResult:
        started = time.perf_counter()
        settings = get_settings()

        def finish(result: PredictionResult) -> PredictionResult:
            return replace(result, latency_ms=(time.perf_counter() - started) * 1000)

        stripped = (text or "").strip()
        if not stripped:
            return finish(
                PredictionResult(
                    label=IntentEnum.SPAM_OTHER,
                    confidence=1.0,
                    latency_ms=0.0,
                    source=SOURCE_EMPTY,
                )
            )

        if not settings.ai_enabled:
            if settings.ai_fallback_to_keywords:
                return finish(
                    self._fallback(
                        stripped,
                        keywords,
                        negative_keywords,
                        "AI_ENABLED is false",
                    )
                )
            return finish(
                PredictionResult(
                    label=IntentEnum.SPAM_OTHER,
                    confidence=0.0,
                    latency_ms=0.0,
                    source=SOURCE_DISABLED,
                )
            )

        try:
            return finish(self._predict_onnx(stripped))
        except Exception as exc:
            logger.exception("ONNX intent prediction failed")
            if settings.ai_fallback_to_keywords:
                return finish(
                    self._fallback(stripped, keywords, negative_keywords, str(exc))
                )
            return finish(
                PredictionResult(
                    label=IntentEnum.SPAM_OTHER,
                    confidence=0.0,
                    latency_ms=0.0,
                    source=SOURCE_ERROR,
                )
            )


def get_classifier() -> IntentClassifier:
    """Return the process-wide classifier singleton."""
    return IntentClassifier()


def predict_intent(
    text: str,
    *,
    keywords: list[str] | None = None,
    negative_keywords: list[str] | None = None,
) -> PredictionResult:
    """Run the singleton classifier on one message."""
    return get_classifier().predict(
        text,
        keywords=keywords,
        negative_keywords=negative_keywords,
    )


def is_actionable_hiring_lead(
    result: PredictionResult,
    threshold: float | None = None,
) -> bool:
    """True when the model calls a real hiring lead at or above the threshold."""
    if threshold is None:
        threshold = get_settings().ai_confidence_threshold
    return (
        result.label == IntentEnum.HIRING_LEAD
        and result.confidence >= threshold
    )
