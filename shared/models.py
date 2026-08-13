"""ORM database models for the Telegram Lead Intelligence domain."""

# Placeholder module — full model definitions to be implemented in Phase 1.
#
# Planned models:
#   - User        : SaaS tenant / account owner
#   - Session     : Telethon StringSession per user
#   - Keyword     : User-defined matching rules
#   - Source      : Monitored Telegram channels/groups
#   - Person      : Identified contact / author profile
#   - Message     : Raw ingested Telegram message
#   - Lead        : Scored opportunity derived from a Message
#   - Feedback    : User quality signal on a Lead

from core.database import Base  # noqa: F401 — re-export for Alembic discovery
