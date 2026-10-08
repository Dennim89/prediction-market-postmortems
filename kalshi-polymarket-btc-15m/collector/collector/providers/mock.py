"""Synthetic providers for offline runs and tests.  No network calls.

The data is made up: a seeded random walk for the BTC price and a book whose YES
mid wanders around 0.50.  It exists to exercise the pipeline, not to look like a
real market.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from collector.providers.base import MarketInfo, SpotPrice
from collector.providers.polymarket import WINDOW, PolymarketProvider


class MockPolymarketProvider(PolymarketProvider):
    """Synthetic 15-minute windows and order books.  Parsing uses the real parsers."""

    def __init__(self, origin: datetime | None = None, seed: int = 7):
        super().__init__()
        # Windows start at `origin` (default: now) and follow each other every 15 minutes.
        self._origin = (origin or datetime.now(timezone.utc)).replace(microsecond=0)
        self._rng = random.Random(seed)
        self._yes_mid = 0.50
        self._market: MarketInfo | None = None

    def _window(self, now: datetime) -> MarketInfo:
        index = max(0, int((now - self._origin) / WINDOW))
        start = self._origin + index * WINDOW
        return MarketInfo(
            market_id=f"mock-market-{index:04d}",
            slug=f"btc-updown-15m-{int(start.timestamp())}",
            title="Bitcoin Up or Down, 15 minutes (synthetic)",
            condition_id=f"mock-market-{index:04d}",
            yes_up_id=f"mock-up-token-{index:04d}",
            no_down_id=f"mock-down-token-{index:04d}",
            start_time=start,
            end_time=start + WINDOW,
        )

    async def find_current_15m_market(self, now: datetime | None = None) -> MarketInfo | None:
        self._market = self._window(now or datetime.now(timezone.utc))
        return self._market

    async def fetch_orderbook(self, token_id: str, depth: int = 10) -> dict | None:
        market = self._market
        if market is None or token_id not in (market.yes_up_id, market.no_down_id):
            return None
        if token_id == market.yes_up_id:
            step = self._rng.choice((-0.01, 0.0, 0.01))
            self._yes_mid = min(0.95, max(0.05, round(self._yes_mid + step, 2)))
        mid = self._yes_mid if token_id == market.yes_up_id else round(1.0 - self._yes_mid, 2)
        bids = [{"price": f"{mid - 0.01 * (i + 1):.2f}", "size": str(100 + 50 * i)} for i in range(3)]
        asks = [{"price": f"{mid + 0.01 * (i + 1):.2f}", "size": str(120 + 40 * i)} for i in range(3)]
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        # Levels are listed worst price first, so the parser's sorting is exercised.
        return {
            "asset_id": token_id,
            "timestamp": str(now_ms),
            "bids": bids[::-1],
            "asks": asks[::-1],
        }

    async def aclose(self) -> None:
        return None


class MockSpotFeedProvider:
    """Seeded random walk; every call to get_last() is one step."""

    source = "mock"

    def __init__(self, start_price: float = 100_000.0, step_usd: float = 5.0, seed: int = 7):
        self._price = start_price
        self._step = step_usd
        self._rng = random.Random(seed)

    def update_from_message(self, raw: bytes | str) -> SpotPrice | None:
        return None

    def get_last(self) -> SpotPrice | None:
        self._price = round(self._price + self._rng.uniform(-self._step, self._step), 2)
        return SpotPrice(price=self._price, ts=datetime.now(timezone.utc), source=self.source)
