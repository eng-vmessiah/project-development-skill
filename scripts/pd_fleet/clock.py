"""UTC wall-clock injection for auditable metadata timestamps.

Timeouts must continue to use monotonic clocks.  This helper is only for
persisted/audit timestamps and samples an injected clock exactly once per call.
The default is retained for backwards compatibility at the API boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

Clock = Callable[[], datetime | str]


def clock_now(clock: Clock | None = None) -> datetime:
    """Return one normalized UTC timestamp from ``clock`` or the wall clock.

    A clock may return an aware UTC ``datetime`` or an ISO-8601 UTC string.
    ``None`` means use the compatibility wall-clock default at this boundary.
    """
    value = (clock or (lambda: datetime.now(timezone.utc)))()
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("clock must return an aware UTC datetime")
        return value.astimezone(timezone.utc)
    if type(value) is str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("clock must return an ISO-8601 UTC value") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError("clock must return an ISO-8601 UTC value")
        return parsed.astimezone(timezone.utc)
    raise ValueError("clock must return an aware UTC datetime or ISO-8601 UTC value")


def clock_iso(clock: Clock | None = None) -> str:
    """Return one normalized UTC timestamp in the project's ISO form."""
    return clock_now(clock).isoformat()


__all__ = ["Clock", "clock_iso", "clock_now"]
