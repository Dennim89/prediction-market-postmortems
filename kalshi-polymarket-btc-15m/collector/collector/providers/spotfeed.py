"""BTC/USD reference price from Polymarket's real-time data socket (RTDS).

Topic `crypto_prices_chainlink`, symbol `btc/usd`.  No keys.  The scheduler owns the
WebSocket connection; this class builds the subscription and parses messages.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from collector.providers.base import SpotPrice
from collector.utils.time import parse_exchange_ts

# Sanity bounds for a BTC/USD price.  Values outside are treated as garbage.
MIN_PRICE = 10_000.0
MAX_PRICE = 1_000_000.0


class SpotFeedProvider:
    source = "polymarket_rtds"

    def __init__(self, rtds_url: str = "wss://ws-live-data.polymarket.com", symbol: str = "btc/usd"):
        self.rtds_url = rtds_url
        self.symbol = symbol
        self._last: SpotPrice | None = None

    def subscribe_message(self) -> dict:
        return {
            "action": "subscribe",
            "subscriptions": [
                {
                    "topic": "crypto_prices_chainlink",
                    "type": "*",
                    "filters": json.dumps({"symbol": self.symbol}, separators=(",", ":")),
                }
            ],
        }

    def update_from_message(self, raw: bytes | str) -> SpotPrice | None:
        """Parse one RTDS message.  Returns the new price, or None.

        A message carries either one point (`payload.value`, `payload.timestamp`) or a
        batch (`payload.data` = [{value, timestamp}, ...]).  From a batch the newest
        point is used.  A point older than the last one returned is ignored.
        """
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        payload = data.get("payload")
        if not isinstance(payload, dict):
            return None
        symbol = payload.get("symbol")
        if symbol is not None and str(symbol).lower() != self.symbol:
            return None

        points: list[tuple[object, object]] = []
        for item in payload.get("data") or []:
            if isinstance(item, dict):
                points.append((item.get("value"), item.get("timestamp")))
        if payload.get("value") is not None:
            points.append((payload.get("value"), payload.get("timestamp")))

        best: SpotPrice | None = None
        for value, ts_raw in points:
            try:
                price = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if not (MIN_PRICE < price < MAX_PRICE):
                continue
            ts = parse_exchange_ts(ts_raw) or datetime.now(timezone.utc)
            if best is None or ts > best.ts:
                best = SpotPrice(price=price, ts=ts, source=self.source)

        if best is None or (self._last is not None and best.ts < self._last.ts):
            return None
        self._last = best
        return best

    def get_last(self) -> SpotPrice | None:
        """Last good price seen, or None."""
        return self._last
