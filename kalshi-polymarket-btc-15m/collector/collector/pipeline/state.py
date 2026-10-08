"""Mutable state of one collector run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from collector.providers.base import MarketInfo, OrderbookL1, OrderbookL2, SpotPrice

ZSCORE_WINDOW = timedelta(minutes=10)
ZSCORE_MIN_HISTORY = 60  # points kept in total
ZSCORE_MIN_RECENT = 30  # points inside the window


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


@dataclass
class CollectorState:
    market: MarketInfo | None = None
    btc_open_price: float | None = None
    btc_open_ts: datetime | None = None
    open_price_decided: bool = False  # captured, or known to be missing for this window
    yes_l1: OrderbookL1 | None = None
    no_l1: OrderbookL1 | None = None
    yes_l2: OrderbookL2 | None = None
    no_l2: OrderbookL2 | None = None
    spot: SpotPrice | None = None
    spot_history: list[tuple[datetime, float]] = field(default_factory=list)
    max_spot_history: int = 600  # about 10 minutes at one point per second

    def set_market(self, market: MarketInfo) -> None:
        """Switch to a new window and forget everything that belonged to the old one."""
        self.market = market
        self.btc_open_price = None
        self.btc_open_ts = None
        self.open_price_decided = False
        self.yes_l1 = self.no_l1 = None
        self.yes_l2 = self.no_l2 = None

    def t_since_open_sec(self, now: datetime | None = None) -> float | None:
        if self.market is None:
            return None
        return max(0.0, (_now(now) - self.market.start_time).total_seconds())

    def t_left_sec(self, now: datetime | None = None) -> float | None:
        if self.market is None:
            return None
        return max(0.0, (self.market.end_time - _now(now)).total_seconds())

    def book_imbalance_yes(self, top_n: int = 5) -> float | None:
        """(bid size - ask size) / (bid size + ask size) over the top N YES levels."""
        if self.yes_l2 is None:
            return None
        bid_sum = sum(lv.size for lv in self.yes_l2.bids[:top_n])
        ask_sum = sum(lv.size for lv in self.yes_l2.asks[:top_n])
        total = bid_sum + ask_sum
        if total <= 0:
            return None
        return (bid_sum - ask_sum) / total

    def zscore_10m(self, now: datetime | None = None) -> float | None:
        """Z-score of the current price against the last 10 minutes, if there is enough history."""
        if self.spot is None or len(self.spot_history) < ZSCORE_MIN_HISTORY:
            return None
        cutoff = _now(now) - ZSCORE_WINDOW
        prices = [p for t, p in self.spot_history if t > cutoff]
        if len(prices) < ZSCORE_MIN_RECENT:
            return None
        mean = sum(prices) / len(prices)
        std = (sum((p - mean) ** 2 for p in prices) / len(prices)) ** 0.5
        if std < 1e-6:
            return 0.0
        return (self.spot.price - mean) / std

    def add_spot_to_history(self, ts: datetime, price: float) -> bool:
        """Append a point.  A point with the same timestamp as the last one is skipped."""
        if self.spot_history and self.spot_history[-1][0] == ts:
            return False
        self.spot_history.append((ts, price))
        if len(self.spot_history) > self.max_spot_history:
            del self.spot_history[: len(self.spot_history) - self.max_spot_history]
        return True

    def first_spot_at_or_after(self, start: datetime) -> tuple[datetime, float] | None:
        """Earliest point stamped at or after `start`, or None."""
        after = [entry for entry in self.spot_history if entry[0] >= start]
        return min(after, key=lambda entry: entry[0]) if after else None
