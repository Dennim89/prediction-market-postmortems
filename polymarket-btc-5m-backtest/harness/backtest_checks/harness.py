"""Taker backtest: run a strategy, settle its trades, resample markets, split by day.

A strategy is a function `strategy(market, params) -> list[Trade]`.  It may read the
market's ticks and its start price, end time and start time.  It must not read
`market.outcome`; `controls.future_leak` checks that it does not use the future.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Iterable

from .friction import FRICTIONLESS, Friction, fee_per_share, fill, settle
from .model import Market, Trade

Strategy = Callable[[Market, dict], list[Trade]]


@dataclass(frozen=True)
class Result:
    trades: int = 0
    wins: int = 0
    shares: float = 0.0
    win_shares: float = 0.0  # shares on winning trades
    stake: float = 0.0  # dollars paid, with fees and slippage
    pnl: float = 0.0
    proxy_markets: int = 0  # traded markets scored on a proxy label, not the venue's outcome

    @property
    def win_rate(self) -> float:
        """Share of trades that won."""
        return self.wins / self.trades if self.trades else math.nan

    @property
    def share_win_rate(self) -> float:
        """Share of shares that won.  Compare it with avg_price, not with 50%."""
        return self.win_shares / self.shares if self.shares else math.nan

    @property
    def avg_price(self) -> float:
        """Average price paid per share, costs included: the break-even share win rate."""
        return self.stake / self.shares if self.shares else math.nan

    @property
    def pnl_per_share(self) -> float:
        """Equals share_win_rate - avg_price."""
        return self.pnl / self.shares if self.shares else math.nan


def run(
    strategy: Strategy,
    markets: Iterable[Market],
    params: dict | None = None,
    friction: Friction = FRICTIONLESS,
    seed: int = 0,
) -> Result:
    """Run `strategy` on each market, fill its trades with `friction`, and settle them."""
    params = params or {}
    rng = random.Random(seed)
    trades = wins = proxy = 0
    shares = win_shares = stake = pnl = 0.0
    for market in markets:
        raw = strategy(market, params)
        if not raw:
            continue
        filled = [f for f in (fill(market, tr, friction) for tr in raw) if f is not None]
        if not filled:
            continue
        outcome, source = settle(market, friction, rng)
        proxy += source == "proxy"
        for f in filled:
            won = f.side == outcome
            trades += 1
            wins += won
            shares += f.size
            win_shares += f.size if won else 0.0
            stake += f.price * f.size
            pnl += ((1.0 if won else 0.0) - f.price) * f.size
    return Result(trades, wins, shares, win_shares, stake, pnl, proxy)


@dataclass(frozen=True)
class Summary:
    seeds: int
    mean: float
    std: float
    min: float
    max: float
    negative_seeds: int


def summarize(values: list[float]) -> Summary:
    vals = [v for v in values if not math.isnan(v)]
    if not vals:
        return Summary(len(values), math.nan, math.nan, math.nan, math.nan, 0)
    return Summary(
        seeds=len(values),
        mean=statistics.mean(vals),
        std=statistics.stdev(vals) if len(vals) > 1 else 0.0,
        min=min(vals),
        max=max(vals),
        negative_seeds=sum(v < 0 for v in vals),
    )


def bootstrap(
    strategy: Strategy,
    markets: list[Market],
    params: dict | None = None,
    seeds: Iterable[int] = range(16),
    friction: Friction = FRICTIONLESS,
) -> list[Result]:
    """One result per seed, each on a resample of the markets (with replacement).

    This measures sampling noise inside the period you have.  It does not tell you how
    the strategy does on days it has not seen: for that, split by day.
    """
    out = []
    n = len(markets)
    for s in seeds:
        rng = random.Random(s)
        sample = [markets[rng.randrange(n)] for _ in range(n)] if n else []
        out.append(run(strategy, sample, params, friction, seed=s))
    return out


def by_day(markets: Iterable[Market]) -> "OrderedDict[str, list[Market]]":
    """Markets grouped by the UTC date of their window start, in date order."""
    groups: dict[str, list[Market]] = {}
    for m in markets:
        groups.setdefault(m.day, []).append(m)
    return OrderedDict(sorted(groups.items()))


def break_even_win_rate(prices: list[float], sizes: list[float], fee_peak: float = 0.0) -> float:
    """Win rate at which buying these shares and holding them to expiry breaks even.

    A share bought at p (plus fee f) wins 1 - p - f or loses p + f, so it breaks even at
    a win rate of p + f.  Across trades, weight by size.
    """
    total = sum(sizes)
    if not total:
        return math.nan
    return sum((p + fee_per_share(p, fee_peak)) * s for p, s in zip(prices, sizes)) / total
