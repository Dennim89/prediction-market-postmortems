"""Polymarket provider: market discovery (Gamma API) and order book snapshots (CLOB REST).

Read-only: public endpoints, no keys, no orders.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from collector import __version__
from collector.providers.base import MarketInfo, OrderbookL1, OrderbookL2, OrderbookLevel
from collector.utils.time import parse_exchange_ts

SLUG_PREFIX = "btc-updown-15m-"
WINDOW = timedelta(minutes=15)
_SLUG_RE = re.compile(r"^btc-updown-15m-(\d+)$")
_UP_NAMES = ("up", "yes")
_DOWN_NAMES = ("down", "no")


def parse_15m_slug(slug: str) -> tuple[datetime | None, datetime | None]:
    """Start and end of the window encoded in a `btc-updown-15m-<unix start>` slug."""
    m = _SLUG_RE.match(slug or "")
    if not m:
        return None, None
    try:
        start = datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None, None
    return start, start + WINDOW


def _json_list(value: Any) -> list | None:
    """Gamma sends some list fields as JSON-encoded strings."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, list) else None


def _levels(raw: Any) -> list[OrderbookLevel]:
    """Read book levels given as {"price", "size"} objects or [price, size] pairs."""
    out: list[OrderbookLevel] = []
    for level in raw or []:
        try:
            if isinstance(level, dict):
                price, size = float(level.get("price", 0)), float(level.get("size", 0))
            else:
                price, size = float(level[0]), float(level[1])
        except (TypeError, ValueError, IndexError):
            continue
        if price > 0:
            out.append(OrderbookLevel(price=price, size=size))
    return out


def _sorted_book(data: dict) -> tuple[list[OrderbookLevel], list[OrderbookLevel]]:
    """Bids high to low, asks low to high, whatever order the response used."""
    bids = sorted(_levels(data.get("bids")), key=lambda lv: lv.price, reverse=True)
    asks = sorted(_levels(data.get("asks")), key=lambda lv: lv.price)
    return bids, asks


class PolymarketProvider:
    """Finds the current 15-minute BTC window and fetches its order books."""

    def __init__(
        self,
        gamma_url: str = "https://gamma-api.polymarket.com",
        clob_url: str = "https://clob.polymarket.com",
        bitcoin_tag_id: str = "235",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_sec: float = 10.0,
    ):
        self.gamma_url = gamma_url.rstrip("/")
        self.clob_url = clob_url.rstrip("/")
        self.bitcoin_tag_id = bitcoin_tag_id
        self._transport = transport
        self._timeout_sec = timeout_sec
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        # One client for the whole run, so polls reuse the connection.
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout_sec,
                transport=self._transport,
                headers={"User-Agent": f"pm-btc15m-collector/{__version__}"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def find_current_15m_market(self, now: datetime | None = None) -> MarketInfo | None:
        """Ask the Gamma API for open Bitcoin events and pick the window that contains `now`."""
        params = {
            "closed": "false",
            "limit": "500",
            "offset": "0",
            "order": "id",
            "ascending": "false",
            "tag_id": self.bitcoin_tag_id,
        }
        resp = await self._http().get(f"{self.gamma_url}/events", params=params)
        resp.raise_for_status()
        events = resp.json()
        return self.pick_current_market(events, now or datetime.now(timezone.utc))

    @staticmethod
    def pick_current_market(events: Any, now: datetime) -> MarketInfo | None:
        """The 15-minute BTC window that contains `now`, or None.

        Events whose outcomes are not exactly one Up/Yes and one Down/No are skipped.
        """
        best: MarketInfo | None = None
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            slug = str(event.get("slug", ""))
            start, end = parse_15m_slug(slug)
            if start is None or end is None or not (start <= now < end):
                continue
            markets = event.get("markets") or []
            if not markets or not isinstance(markets[0], dict):
                continue
            market = markets[0]
            outcomes = _json_list(market.get("outcomes"))
            tokens = _json_list(market.get("clobTokenIds"))
            if not outcomes or not tokens or len(outcomes) != 2 or len(tokens) != 2:
                continue
            names = [str(o).strip().lower() for o in outcomes]
            up = next((i for i, n in enumerate(names) if n in _UP_NAMES), None)
            down = next((i for i, n in enumerate(names) if n in _DOWN_NAMES), None)
            if up is None or down is None or up == down:
                continue
            condition_id = str(market.get("conditionId", ""))
            if best is None or start > best.start_time:
                best = MarketInfo(
                    market_id=condition_id,
                    slug=slug,
                    title=str(event.get("title", slug)),
                    condition_id=condition_id,
                    yes_up_id=str(tokens[up]),
                    no_down_id=str(tokens[down]),
                    start_time=start,
                    end_time=end,
                )
        return best

    async def fetch_orderbook(self, token_id: str, depth: int = 10) -> dict[str, Any] | None:
        """Full book for one outcome token (GET /book).  None on a non-200 answer.

        `depth` is not sent: the endpoint returns the whole book and the parsers cut it.
        """
        resp = await self._http().get(f"{self.clob_url}/book", params={"token_id": token_id})
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None

    @staticmethod
    def _book_ts(data: dict, recv_ts: datetime | None) -> datetime:
        return parse_exchange_ts(data.get("timestamp")) or recv_ts or datetime.now(timezone.utc)

    def parse_orderbook_l1(
        self, data: dict, asset_id: str, side: str, recv_ts: datetime | None = None
    ) -> OrderbookL1 | None:
        """Best bid and ask.  None when both sides are empty."""
        bids, asks = _sorted_book(data)
        if not bids and not asks:
            return None
        bid = bids[0] if bids else OrderbookLevel(0.0, 0.0)
        ask = asks[0] if asks else OrderbookLevel(0.0, 0.0)
        return OrderbookL1(
            asset_id=asset_id,
            side=side,
            bid_price=bid.price,
            bid_size=bid.size,
            ask_price=ask.price,
            ask_size=ask.size,
            ts=self._book_ts(data, recv_ts),
        )

    def parse_orderbook_l2(
        self, data: dict, asset_id: str, side: str, depth: int, recv_ts: datetime | None = None
    ) -> OrderbookL2:
        """Top `depth` levels per side, best price first."""
        bids, asks = _sorted_book(data)
        return OrderbookL2(
            asset_id=asset_id,
            side=side,
            bids=bids[:depth],
            asks=asks[:depth],
            ts=self._book_ts(data, recv_ts),
        )
