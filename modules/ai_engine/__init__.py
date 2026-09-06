"""AI engine — Phase 7 ParsBERT intent classification."""

from modules.ai_engine.classifier import (
    IntentClassifier,
    get_classifier,
    is_actionable_hiring_lead,
    predict_intent,
)
from modules.ai_engine.fallback import fallback_to_keywords
from modules.ai_engine.labels import IntentEnum
from modules.ai_engine.schemas import PredictionResult

__all__ = [
    "IntentClassifier",
    "IntentEnum",
    "PredictionResult",
    "fallback_to_keywords",
    "get_classifier",
    "is_actionable_hiring_lead",
    "predict_intent",
]
