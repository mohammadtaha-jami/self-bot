"""Keyword-filter fallback when the AI classifier is unavailable."""

from __future__ import annotations

from modules.ai_engine.schemas import PredictionResult


def fallback_to_keywords(text: str) -> PredictionResult:
    """Switch back to Level-1 keyword matching if ONNX inference fails."""
    raise NotImplementedError(
        "Keyword fallback will be implemented in Phase 7.4"
    )
