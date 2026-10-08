"""Time helpers."""

from datetime import datetime, timezone

import pytest

from collector.utils.time import parse_exchange_ts, parse_iso_utc, utc_now_iso

JAN1 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_utc_now_iso():
    s = utc_now_iso()
    assert "T" in s
    assert s.endswith("+00:00")


def test_parse_iso_utc():
    assert parse_iso_utc("2026-01-01T00:00:00+00:00") == JAN1
    assert parse_iso_utc("2026-01-01T00:00:00Z") == JAN1
    assert parse_iso_utc("2026-01-01T00:00:00") == JAN1  # naive is taken as UTC
    assert parse_iso_utc("2026-01-01T02:00:00+02:00") == JAN1
    assert parse_iso_utc("invalid") is None


@pytest.mark.parametrize(
    "value",
    ["1767225600000", 1767225600000, "1767225600", 1767225600, 1767225600.0, "2026-01-01T00:00:00Z"],
)
def test_parse_exchange_ts_reads_iso_seconds_and_milliseconds(value):
    assert parse_exchange_ts(value) == JAN1


@pytest.mark.parametrize("value", [None, "", "   ", "not a time", True, 0, -5, [], {}])
def test_parse_exchange_ts_returns_none_for_garbage(value):
    assert parse_exchange_ts(value) is None
