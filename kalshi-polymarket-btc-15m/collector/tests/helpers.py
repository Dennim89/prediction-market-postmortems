"""Constants and builders shared by the tests."""

from datetime import datetime, timedelta, timezone

from collector.providers.base import MarketInfo

# 2026-01-01 00:00:00 UTC, the start of the current window in the fixtures.
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW = START + timedelta(minutes=5)


def make_market(start: datetime = START) -> MarketInfo:
    return MarketInfo(
        market_id="fake-condition-0001",
        slug=f"btc-updown-15m-{int(start.timestamp())}",
        title="synthetic",
        condition_id="fake-condition-0001",
        yes_up_id="fake-token-up-0001",
        no_down_id="fake-token-down-0001",
        start_time=start,
        end_time=start + timedelta(minutes=15),
    )
