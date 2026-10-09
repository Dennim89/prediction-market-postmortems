"""Two example strategies: the project's untuned baseline, and the same rule with the
tick choice that later versions used.

Parameters (all optional):
  window_sec  act only in the last this many seconds of the window (default 10)
  margin      minimum edge, fair probability minus ask (default 0.03)
  size        shares per trade (default 10)

These are the baseline's starting values, not tuned settings.
"""

from __future__ import annotations

from typing import Iterator

from .fair import fair_p_up
from .model import NO, YES, Market, Tick, Trade


def _candidates(market: Market, params: dict) -> Iterator[tuple[Tick, str, float, float]]:
    """(tick, side, ask, edge) for each tick in the window where one side clears the margin."""
    window = params.get("window_sec", 10)
    margin = params.get("margin", 0.03)
    for tick in market.ticks:
        t_left = market.t_left(tick)
        if t_left > window:
            continue
        if t_left <= 0:
            break
        if tick.yes_ask is None or tick.no_ask is None:
            continue
        p_up = fair_p_up(tick.spot, market.start_price, tick.sigma, t_left)
        yes_edge = p_up - tick.yes_ask
        no_edge = (1.0 - p_up) - tick.no_ask
        if yes_edge >= margin and yes_edge >= no_edge:
            yield tick, YES, tick.yes_ask, yes_edge
        elif no_edge >= margin:
            yield tick, NO, tick.no_ask, no_edge


def naive(market: Market, params: dict) -> list[Trade]:
    """Baseline (v0 in the project): take the first tick where the ask of one side is at
    least `margin` below the fair probability of that side.  One trade per market."""
    size = params.get("size", 10)
    for tick, side, ask, _edge in _candidates(market, params):
        return [Trade(t=tick.t, side=side, price=ask, size=size)]
    return []


def best_tick_in_hindsight(market: Market, params: dict) -> list[Trade]:
    """The same rule, but trade at the tick with the largest edge in the window.

    From v5 on, the project's strategies chose their tick this way.  It reads the future:
    at any tick a live bot cannot know whether a later tick will offer a larger edge.
    `controls.future_leak` flags it.  It is here as a test case, not as a strategy.
    """
    size = params.get("size", 10)
    best = None
    for tick, side, ask, edge in _candidates(market, params):
        if best is None or edge > best[3]:
            best = (tick, side, ask, edge)
    if best is None:
        return []
    tick, side, ask, _edge = best
    return [Trade(t=tick.t, side=side, price=ask, size=size)]
