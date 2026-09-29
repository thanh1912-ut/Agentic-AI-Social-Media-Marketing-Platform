"""Small privacy-retention primitives shared by research workers and tests."""

from collections.abc import Sequence
from datetime import datetime, timedelta


MAX_RAW_QUARANTINE = timedelta(hours=24)


def raw_quarantine_expiry(stored_at: datetime) -> datetime:
    """Return the hard expiry for raw research payloads kept for quarantine.

    Raw payloads are not retained as source-of-truth records. An aware timestamp
    is required so the scheduler can compare expiry consistently in UTC.
    """

    if stored_at.tzinfo is None or stored_at.utcoffset() is None:
        raise ValueError("stored_at must be timezone-aware")
    return stored_at + MAX_RAW_QUARANTINE


def hold_comment_text(comments: Sequence[str]) -> tuple[list[str], int]:
    """Return no commenter text while privacy processing is not approved."""

    return [], len(comments)
