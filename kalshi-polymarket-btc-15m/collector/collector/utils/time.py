"""Time helpers.  Everything is UTC."""

from __future__ import annotations

from datetime import datetime, timezone

# Unix times above this are taken as milliseconds (1e11 seconds is far in the future).
_MS_THRESHOLD = 1e11


def utc_now_iso() -> str:
    """Current UTC time as ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso_utc(s: str) -> datetime | None:
    """Parse an ISO 8601 string to an aware UTC datetime.  Naive input is taken as UTC."""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_exchange_ts(value: object) -> datetime | None:
    """Parse a timestamp as APIs send it: ISO 8601, or Unix seconds or milliseconds.

    Numbers may come as int, float or a string of digits.  Returns None for anything
    that cannot be read, so the caller can fall back to its own receive time.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return parse_iso_utc(text)
    else:
        return None
    if number <= 0:
        return None
    if number > _MS_THRESHOLD:
        number /= 1000.0
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
