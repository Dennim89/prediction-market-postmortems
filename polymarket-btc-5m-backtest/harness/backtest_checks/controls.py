"""Sanity controls.  Run them before you look at any strategy result.

- do_nothing: must give exactly zero.
- random_side and cheaper_side: rules with no information; on fair prices they lose about
  the spread and the fees.  If they make money, the evaluation is wrong (or the prices
  are stale).
- inverted(strategy): buys the other side at the same moment.  If the strategy has an
  edge, the inverted copy must lose.
- future_leak: re-runs a strategy on copies of each market that end at a checkpoint.
  Decisions made before the checkpoint must not change.

Passing the controls shows that the evaluation is consistent.  It does not show that an
edge will hold on new days, under real fills, or on the venue's own settlement.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable

from .harness import Strategy
from .model import NO, YES, Market, Trade, other


def do_nothing(market: Market, params: dict) -> list[Trade]:
    return []


def _first_quoted_tick(market: Market, window_sec: float):
    for tick in market.ticks:
        t_left = market.t_left(tick)
        if t_left > window_sec:
            continue
        if t_left <= 0:
            break
        if tick.yes_ask is not None and tick.no_ask is not None:
            return tick
    return None


def random_side(seed: int = 0) -> Strategy:
    """Coin flip at the first quoted tick in the window.  The flip depends only on the
    seed and the market id, so results do not depend on the order markets are run in."""

    def strategy(market: Market, params: dict) -> list[Trade]:
        tick = _first_quoted_tick(market, params.get("window_sec", 10))
        if tick is None:
            return []
        side = YES if random.Random(f"{seed}:{market.market_id}").random() < 0.5 else NO
        return [Trade(t=tick.t, side=side, price=tick.ask(side), size=params.get("size", 10))]

    return strategy


def cheaper_side(market: Market, params: dict) -> list[Trade]:
    """Buy whichever side has the lower ask, at the first quoted tick in the window."""
    tick = _first_quoted_tick(market, params.get("window_sec", 10))
    if tick is None:
        return []
    side = YES if tick.yes_ask <= tick.no_ask else NO
    return [Trade(t=tick.t, side=side, price=tick.ask(side), size=params.get("size", 10))]


def inverted(strategy: Strategy) -> Strategy:
    """For every trade of `strategy`, buy the other side at that tick's ask instead."""

    def wrapped(market: Market, params: dict) -> list[Trade]:
        out = []
        for trade in strategy(market, params):
            i = market.index_at(trade.t)
            if i is None:
                continue
            tick = market.ticks[i]
            side = other(trade.side)
            ask = tick.ask(side)
            if ask is not None:
                out.append(Trade(t=tick.t, side=side, price=ask, size=trade.size))
        return out

    return wrapped


@dataclass
class LeakReport:
    markets_checked: int = 0
    checkpoints: int = 0
    leaking: list[str] = field(default_factory=list)  # market ids whose decisions changed

    @property
    def ok(self) -> bool:
        return not self.leaking


def _key(trades: Iterable[Trade], until: float) -> list[tuple]:
    return sorted((t.t, t.side, t.price, t.size) for t in trades if t.t <= until)


def future_leak(strategy: Strategy, markets: Iterable[Market], params: dict | None = None,
                every: int = 10) -> LeakReport:
    """Check that `strategy` decides from the past only.

    For each market, the strategy runs on the full market and on copies that end at a
    checkpoint (every `every`-th tick, each trade time and the tick before it), with the
    outcome hidden.  Trades up to the checkpoint must be the same in both runs.
    """
    params = params or {}
    report = LeakReport()
    for market in markets:
        report.markets_checked += 1
        full = strategy(market, params)
        times = [tk.t for tk in market.ticks]
        points = set(times[::every])
        for trade in full:
            i = market.index_at(trade.t)
            if i is not None:
                points.add(times[i])
                if i > 0:
                    points.add(times[i - 1])
        for point in sorted(points):
            report.checkpoints += 1
            partial = strategy(market.truncated(point), params)
            if _key(full, point) != _key(partial, point):
                report.leaking.append(market.market_id)
                break
    return report
