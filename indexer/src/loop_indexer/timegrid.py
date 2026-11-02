"""The UTC sampling grid every chain is snapshotted on."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

_DURATION = re.compile(r"^(\d+)([smhd])$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_duration(text: str) -> timedelta:
    """Parse ``30m``, ``1h``, ``1d``..."""
    match = _DURATION.match(text.strip())
    if not match:
        raise ValueError(f"invalid duration {text!r} (expected e.g. 1h, 30m, 1d)")
    value, unit = int(match.group(1)), match.group(2)
    delta = timedelta(**{_UNITS[unit]: value})
    if delta <= timedelta(0):
        raise ValueError("duration must be positive")
    return delta


def parse_time(text: str) -> datetime:
    """Parse an ISO-8601 date/time; naive values are interpreted as UTC."""
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def from_unix(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


def to_unix(value: datetime) -> int:
    return int(value.timestamp())


def floor_to(value: datetime, interval: timedelta) -> datetime:
    step = int(interval.total_seconds())
    return from_unix(to_unix(value) // step * step)


def ceil_to(value: datetime, interval: timedelta) -> datetime:
    floored = floor_to(value, interval)
    return floored if floored == value else floored + interval


def grid(start: datetime, end: datetime, interval: timedelta) -> list[datetime]:
    """Grid points in ``[ceil(start), floor(end)]``."""
    out: list[datetime] = []
    current, last = ceil_to(start, interval), floor_to(end, interval)
    while current <= last:
        out.append(current)
        current += interval
    return out
