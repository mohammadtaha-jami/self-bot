"""Rule engine and Level-1 keyword matching."""

from shared.enums import LeadLevelEnum

from core.logger import setup_logging

logger = setup_logging(__name__)


async def match_keywords(text: str, user_id: int) -> tuple[bool, LeadLevelEnum, list[str]]:
    """
    Run Level-1 keyword rules against message text.

    Args:
        text: Raw message body.
        user_id: Tenant owner whose keyword rules to apply.

    Returns:
        Tuple of (matched, lead_level, matched_keyword_ids).
    """
    # TODO: Load user keywords from DB and apply exact/contains/regex rules
    logger.debug("Keyword matching for user %d (placeholder)", user_id)
    raise NotImplementedError("Keyword matching not yet implemented")
