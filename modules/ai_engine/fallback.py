"""Keyword-filter fallback when the AI classifier is unavailable."""

from __future__ import annotations

import time

from modules.ai_engine.labels import IntentEnum
from modules.ai_engine.schemas import SOURCE_KEYWORDS, PredictionResult
from modules.processor.matching import MatchConfig, match_keywords

DEFAULT_HIRING_KEYWORDS = [
    "استخدام",
    "نیازمند",
    "نیازمندیم",
    "جذب نیرو",
    "موقعیت شغلی",
    "آگهی استخدام",
    "دعوت به همکاری",
    "کارفرما",
    "#استخدام",
    "#کارفرما",
    "حقوق ثابت",
    "همکاری بلندمدت",
]

DEFAULT_SEEKING_KEYWORDS = [
    "جویای کار",
    "آماده همکاری",
    "فریلنسر",
    "انجام میدم",
    "سفارش میپذیرم",
    "نمونه کار",
    "انجام دهنده",
    "#انجام_دهنده",
    "رزومه دارم",
]


def _confidence_from_score(score: float) -> float:
    return max(0.0, min(score / 100.0, 1.0))


def _match(text: str, keywords: list[str], negative_keywords: list[str] | None = None):
    return match_keywords(
        text,
        MatchConfig(
            keywords=keywords,
            negative_keywords=negative_keywords or [],
        ),
    )


def fallback_to_keywords(
    text: str,
    keywords: list[str] | None = None,
    negative_keywords: list[str] | None = None,
) -> PredictionResult:
    """Map Level-1 keyword matching onto the three intent classes."""
    started = time.perf_counter()

    if keywords:
        hiring = _match(text, keywords, negative_keywords)
        if hiring.matched:
            return PredictionResult(
                label=IntentEnum.HIRING_LEAD,
                confidence=_confidence_from_score(hiring.score),
                latency_ms=(time.perf_counter() - started) * 1000,
                source=SOURCE_KEYWORDS,
            )

    hiring = _match(text, DEFAULT_HIRING_KEYWORDS)
    seeking = _match(text, DEFAULT_SEEKING_KEYWORDS)

    if hiring.matched and seeking.matched:
        label = (
            IntentEnum.HIRING_LEAD
            if hiring.score >= seeking.score
            else IntentEnum.SEEKING_JOB
        )
        score = max(hiring.score, seeking.score)
        return PredictionResult(
            label=label,
            confidence=_confidence_from_score(score),
            latency_ms=(time.perf_counter() - started) * 1000,
            source=SOURCE_KEYWORDS,
        )

    if hiring.matched:
        return PredictionResult(
            label=IntentEnum.HIRING_LEAD,
            confidence=_confidence_from_score(hiring.score),
            latency_ms=(time.perf_counter() - started) * 1000,
            source=SOURCE_KEYWORDS,
        )

    if seeking.matched:
        return PredictionResult(
            label=IntentEnum.SEEKING_JOB,
            confidence=_confidence_from_score(seeking.score),
            latency_ms=(time.perf_counter() - started) * 1000,
            source=SOURCE_KEYWORDS,
        )

    return PredictionResult(
        label=IntentEnum.SPAM_OTHER,
        confidence=1.0,
        latency_ms=(time.perf_counter() - started) * 1000,
        source=SOURCE_KEYWORDS,
    )
