"""Rule engine and Level-1 keyword matching."""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from core.logger import setup_logging
from modules.processor.nlp import (
    clean_text,
    count_meaningful_tokens,
    has_phrase_match,
)
from shared.enums import LeadLevelEnum

logger = setup_logging(__name__)

# آستانه‌های پیش‌فرض — از طریق MatchConfig قابل‌تغییرند
DEFAULT_MIN_TEXT_LEN = 8
DEFAULT_MIN_MEANINGFUL_TOKENS = 2
DEFAULT_MIN_FUZZY_LEN = 5
DEFAULT_MIN_LEN_RATIO = 0.5
DEFAULT_MIN_DISTINCT_KEYWORDS_FOR_HOT = 2
DEFAULT_MIN_EXACT_CHARS_FOR_HOT = 3
DEFAULT_FUZZY_THRESHOLD = 85.0


@dataclass
class MatchConfig:
    """پیکربندی کلمات کلیدی و تنظیمات تطبیق کاربر."""

    keywords: list[str] = field(default_factory=list)
    negative_keywords: list[str] = field(default_factory=list)
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD
    min_text_len: int = DEFAULT_MIN_TEXT_LEN
    min_meaningful_tokens: int = DEFAULT_MIN_MEANINGFUL_TOKENS
    require_min_tokens: bool = True
    min_fuzzy_len: int = DEFAULT_MIN_FUZZY_LEN
    min_text_to_keyword_ratio: float = DEFAULT_MIN_LEN_RATIO
    min_distinct_keywords_for_hot: int = DEFAULT_MIN_DISTINCT_KEYWORDS_FOR_HOT
    min_exact_chars_for_hot: int = DEFAULT_MIN_EXACT_CHARS_FOR_HOT


@dataclass
class MatchResult:
    """خروجی تفصیلی الگوریتم تطبیق."""

    matched: bool
    lead_level: LeadLevelEnum = LeadLevelEnum.LOW
    matched_keywords: list[str] = field(default_factory=list)
    score: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class KeywordHit:
    """یک برخورد معتبر کلیدواژه با متن."""

    keyword: str
    cleaned: str
    score: float
    is_exact: bool


def _cleaned_keyword_len(cleaned_kw: str) -> int:
    return len(cleaned_kw.replace(" ", "").replace("\u200c", ""))


def is_fuzzy_eligible(cleaned_kw: str, cleaned_text: str, config: MatchConfig) -> bool:
    """آیا partial_ratio برای این جفت متن/کلیدواژه مجاز است؟"""
    if len(cleaned_kw) < config.min_fuzzy_len or len(cleaned_text) < config.min_fuzzy_len:
        return False
    if not cleaned_kw:
        return False
    ratio = len(cleaned_text) / len(cleaned_kw)
    return ratio >= config.min_text_to_keyword_ratio


def determine_lead_level(hits: list[KeywordHit], config: MatchConfig) -> LeadLevelEnum:
    """سطح HOT فقط با تطابق دقیق به‌اندازهٔ کافی بلند، یا چند کلیدواژهٔ متمایز."""
    if not hits:
        return LeadLevelEnum.LOW

    distinct_count = len({hit.keyword for hit in hits})
    has_long_exact = any(
        hit.is_exact and _cleaned_keyword_len(hit.cleaned) >= config.min_exact_chars_for_hot
        for hit in hits
    )
    if has_long_exact or distinct_count >= config.min_distinct_keywords_for_hot:
        return LeadLevelEnum.HOT
    return LeadLevelEnum.WARM


def check_negative_keywords(
    text: str,
    negative_keywords: list[str],
) -> bool:
    """بررسی وجود عبارت منفی با مرز کلمه در متن پاک‌شده."""
    for neg_kw in negative_keywords:
        cleaned_neg = clean_text(neg_kw)
        if cleaned_neg and has_phrase_match(text, cleaned_neg):
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

    if len(cleaned_text) < config.min_text_len:
        return MatchResult(
            matched=False,
            lead_level=LeadLevelEnum.LOW,
            reason="Text shorter than min_text_len",
        )

    if config.require_min_tokens:
        token_count = count_meaningful_tokens(cleaned_text)
        if token_count < config.min_meaningful_tokens:
            return MatchResult(
                matched=False,
                lead_level=LeadLevelEnum.LOW,
                reason="Too few meaningful tokens",
            )

    if check_negative_keywords(cleaned_text, config.negative_keywords):
        logger.debug("Message matched negative keywords; skipped.")
        return MatchResult(
            matched=False,
            lead_level=LeadLevelEnum.LOW,
            reason="Matched negative keyword",
        )

    hits: list[KeywordHit] = []
    seen: set[str] = set()

    for kw in config.keywords:
        cleaned_kw = clean_text(kw)
        if not cleaned_kw or kw in seen:
            continue

        if has_phrase_match(cleaned_text, cleaned_kw):
            seen.add(kw)
            hits.append(
                KeywordHit(keyword=kw, cleaned=cleaned_kw, score=100.0, is_exact=True)
            )
            continue

        if not is_fuzzy_eligible(cleaned_kw, cleaned_text, config):
            continue

        similarity = float(fuzz.partial_ratio(cleaned_kw, cleaned_text))
        if similarity >= config.fuzzy_threshold:
            seen.add(kw)
            hits.append(
                KeywordHit(
                    keyword=kw,
                    cleaned=cleaned_kw,
                    score=similarity,
                    is_exact=False,
                )
            )

    if hits:
        highest_score = max(hit.score for hit in hits)
        lead_level = determine_lead_level(hits, config)
        matched_keywords = [hit.keyword for hit in hits]
        return MatchResult(
            matched=True,
            lead_level=lead_level,
            matched_keywords=matched_keywords,
            score=highest_score,
            reason=f"Matched keywords with max score {highest_score:.1f}%",
        )

    return MatchResult(
        matched=False,
        lead_level=LeadLevelEnum.LOW,
        reason="No keyword match found",
    )
