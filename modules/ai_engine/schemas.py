"""Result types for AI intent prediction."""

from __future__ import annotations

from dataclasses import dataclass

from modules.ai_engine.labels import IntentEnum

SOURCE_ONNX = "onnx"
SOURCE_KEYWORDS = "keywords"
SOURCE_DISABLED = "disabled"
SOURCE_EMPTY = "empty"
SOURCE_ERROR = "error"


@dataclass(frozen=True)
class PredictionResult:
    """Single classifier output for one message."""

    label: IntentEnum
    confidence: float
    latency_ms: float
    source: str
