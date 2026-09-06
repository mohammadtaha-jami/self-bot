"""ONNX Intent classifier (ParsBERT) — skeleton for Phase 7.4."""

from __future__ import annotations

from modules.ai_engine.schemas import PredictionResult


class IntentClassifier:
    """Singleton wrapper around the ONNX session and tokenizer."""

    _instance: IntentClassifier | None = None

    def __new__(cls) -> IntentClassifier:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def predict(self, text: str) -> PredictionResult:
        raise NotImplementedError(
            "IntentClassifier.predict will be implemented in Phase 7.4"
        )
