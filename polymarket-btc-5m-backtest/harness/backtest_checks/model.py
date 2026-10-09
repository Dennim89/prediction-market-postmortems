"""Data model: ticks, markets and trades for 5-minute up/down markets.

A market pays $1 per YES share if the reference price ends the window at or above
the window's start price, and $1 per NO share otherwise.  Times are Unix seconds (UTC).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime, timezone

YES = "YES"
NO = "NO"
SIDES = (YES, NO)


def other(side: str) -> str:
    return NO if side == YES else YES


@dataclass(frozen=True)
class Tick:
    """One observation of the reference price and the order book."""

    t: float  # Unix seconds, UTC
    spot: float  # reference price the strategy sees, for example an exchange's BTC price
    sigma: float = 0.0  # volatility of log returns per second known at this tick; 0 = unknown
    yes_bid: float | None = None
    yes_ask: float | None = None
    no_bid: float | None = None
    no_ask: float | None = None
    yes_ask_size: float | None = None  # shares shown at the best YES ask; None = unknown
    no_ask_size: float | None = None

    def ask(self, side: str) -> float | None:
        return self.yes_ask if side == YES else self.no_ask

    def ask_size(self, side: str) -> float | None:
        return self.yes_ask_size if side == YES else self.no_ask_size


@dataclass
class Market:
    """One window.  `outcome` is the venue's own resolution when you have it."""

    market_id: str
    start: float  # window start, Unix seconds
    end: float  # window end, Unix seconds
    start_price: float  # the price the window is measured against
    ticks: list[Tick] = field(default_factory=list)
    outcome: str | None = None  # YES or NO as the venue resolved it; None = unknown

    def __post_init__(self) -> None:
        if self.outcome is not None and self.outcome not in SIDES:
            raise ValueError(f"{self.market_id}: outcome must be YES, NO or None")
        self.ticks.sort(key=lambda tk: tk.t)

    @property
    def day(self) -> str:
        """UTC date of the window start, as YYYY-MM-DD."""
        return datetime.fromtimestamp(self.start, tz=timezone.utc).date().isoformat()

    def t_left(self, tick: Tick) -> float:
        return self.end - tick.t

    def index_at(self, t: float) -> int | None:
        """Index of the last tick at or before `t`, or None.  Never a later tick."""
        times = [tk.t for tk in self.ticks]
        i = bisect.bisect_right(times, t) - 1
        return i if i >= 0 else None

    def truncated(self, t: float) -> "Market":
        """A copy that knows only the ticks at or before `t`, and not the outcome."""
        return Market(
            market_id=self.market_id,
            start=self.start,
            end=self.end,
            start_price=self.start_price,
            ticks=[tk for tk in self.ticks if tk.t <= t],
            outcome=None,
        )


@dataclass(frozen=True)
class Trade:
    """A taker order: buy `size` shares of `side`.  `price` is what the strategy saw."""

    t: float
    side: str
    price: float
    size: float

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise ValueError("side must be YES or NO")
        if self.size <= 0:
            raise ValueError("size must be positive")


def proxy_outcome(market: Market, tie_rule: str = "ge", noise: float = 0.0) -> str:
    """Outcome from the last tick's reference price against the start price.

    This is a proxy, not the venue's resolution: the venue may settle on another price
    source.  `noise` shifts the final price to model that difference.  `tie_rule` "ge"
    resolves a tie to YES, "gt" to NO.
    """
    if not market.ticks:
        raise ValueError(f"{market.market_id}: no ticks")
    last = market.ticks[-1].spot + noise
    if tie_rule == "ge":
        return YES if last >= market.start_price else NO
    if tie_rule == "gt":
        return YES if last > market.start_price else NO
    raise ValueError("tie_rule must be 'ge' or 'gt'")
