"""Rule engine and Level-1 keyword matching."""

from dataclasses import dataclass, field
from rapidfuzz import fuzz

from core.logger import setup_logging
from modules.processor.nlp import clean_text
from shared.enums import LeadLevelEnum

logger = setup_logging(__name__)


@dataclass
class MatchConfig:
    """پیکربندی کلمات کلیدی و تنظیمات تطبیق کاربر."""

    keywords: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)
    fuzzy_threshold: float = 85.0


@dataclass
class MatchResult:
    """خروجی تفصیلی الگوریتم تطبیق."""

    matched: bool
    lead_level: LeadLevelEnum = LeadLevelEnum.LOW
    matched_keywords: list[str] = field(default_factory=list)
    score: float = 0.0
    reason: str = ""


def check_negative_keywords(text: str, negative_keywords: list[str]) -> bool:
    """بررسی وجود کلمات منفی در متن جهت رد سریع پیام."""
    for neg_kw in negative_keywords:
        cleaned_neg = clean_text(neg_kw)
        if cleaned_neg and cleaned_neg in text:
            return True
    return False


def match_keywords(text: str, config: MatchConfig) -> MatchResult:
    """
    اجرای قوانین تطبیق سطح ۱ روی متن پیام.

    Args:
        text: متن خام پیام دریافتی.
        config: تنظیمات و لیست کلمات کلیدی مثبت/منفی کاربر.

    Returns:
        MatchResult شامل وضعیت تطبیق، سطح لید و کلمات پیدا شده.
    """
    cleaned_text = clean_text(text)

    if not cleaned_text or not config.keywords:
        return MatchResult(
            matched=False,
            lead_level=LeadLevelEnum.LOW,
            reason="Empty text or no keywords configured",
        )

    # ۱. فیلتر کلمات منفی
    if check_negative_keywords(cleaned_text, config.negative_keywords):
        logger.debug("Message matched negative keywords; skipped.")
        return MatchResult(
            matched=False,
            lead_level=LeadLevelEnum.LOW,
            reason="Matched negative keyword",
        )

    matched_found: list[str] = []
    highest_score: float = 0.0

    # ۲. بررسی کلمات کلیدی مثبت
    for kw in config.keywords:
        cleaned_kw = clean_text(kw)
        if not cleaned_kw:
            continue

        # تطبیق مستقیم (Exact Substring)
        if cleaned_kw in cleaned_text:
            matched_found.append(kw)
            highest_score = 100.0
            continue

        # ۳. تطبیق فازی (Fuzzy Search)
        similarity = fuzz.partial_ratio(cleaned_kw, cleaned_text)
        if similarity >= config.fuzzy_threshold:
            matched_found.append(kw)
            if similarity > highest_score:
                highest_score = similarity

    if matched_found:
        lead_level = (
            LeadLevelEnum.HOT if highest_score >= 90.0 else LeadLevelEnum.WARM
        )
        return MatchResult(
            matched=True,
            lead_level=lead_level,
            matched_keywords=matched_found,
            score=highest_score,
            reason=f"Matched keywords with max score {highest_score:.1f}%",
        )

    return MatchResult(
        matched=False,
        lead_level=LeadLevelEnum.LOW,
        reason="No keyword match found",
    )

