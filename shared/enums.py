"""Domain enumerations for lead scoring, keywords, and feedback strictly aligned with Phase 1 Postgres Schema."""

import enum


class LeadLevelEnum(str, enum.Enum):
    """Lead priority tier matching PostgreSQL lead_level_enum."""

    LOW = "low"
    WARM = "warm"
    HOT = "hot"


class KeywordTypeEnum(str, enum.Enum):
    """Classification of keyword matching rules matching PostgreSQL keyword_type_enum."""

    POSITIVE = "positive"
    NEGATIVE = "negative"


class FeedbackTypeEnum(str, enum.Enum):
    """User feedback on lead quality matching PostgreSQL feedback_type_enum."""

    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    NOT_SURE = "not_sure"


class BusinessTypeEnum(str, enum.Enum):
    """Suggested business types stored on User.business_type (custom strings also allowed)."""

    GENERAL = "general"
    REAL_ESTATE = "real_estate"
    CRYPTO = "crypto"