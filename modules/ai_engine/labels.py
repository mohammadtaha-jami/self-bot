"""Intent class labels for the ParsBERT classifier."""

from enum import IntEnum


class IntentEnum(IntEnum):
    """Three-class output of the fine-tuned ParsBERT model."""

    SPAM_OTHER = 0
    SEEKING_JOB = 1
    HIRING_LEAD = 2
