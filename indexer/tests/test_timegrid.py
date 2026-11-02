from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from loop_indexer.timegrid import ceil_to, floor_to, grid, parse_duration, parse_time

H = timedelta(hours=1)


def test_parse_duration() -> None:
    assert parse_duration("1h") == H
    assert parse_duration("15m") == timedelta(minutes=15)
    assert parse_duration("1d") == timedelta(days=1)
    for bad in ("", "1w", "h", "0h"):
        with pytest.raises(ValueError, match="duration"):
            parse_duration(bad)


def test_parse_time_defaults_to_utc() -> None:
    assert parse_time("2025-01-01") == datetime(2025, 1, 1, tzinfo=UTC)
    assert parse_time("2025-01-01T05:00:00Z").hour == 5


def test_floor_ceil_and_grid() -> None:
    t = datetime(2025, 1, 1, 10, 30, tzinfo=UTC)
    assert floor_to(t, H) == datetime(2025, 1, 1, 10, tzinfo=UTC)
    assert ceil_to(t, H) == datetime(2025, 1, 1, 11, tzinfo=UTC)
    assert ceil_to(floor_to(t, H), H) == floor_to(t, H)
    points = grid(t, t + 3 * H, H)
    assert [p.hour for p in points] == [11, 12, 13]
    assert grid(t, t, H) == []
