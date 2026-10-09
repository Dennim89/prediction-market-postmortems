"""Execution friction: fees, slippage, a depth cap, latency, settlement noise, the tie rule.

The harness is taker only.  A trade fills at the best ask of its side on the fill tick:
the tick the strategy acted on, or a later one when there is latency.  Fees and slippage
are added to the price per share.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .model import Market, Trade, proxy_outcome


def fee_per_share(price: float, peak: float) -> float:
    """A fee that is largest at a price of 0.50 and zero at 0 and 1.

    `peak` is the fee per share, in dollars, at a price of 0.50.  The shape is
    4 * peak * p * (1 - p).  Check the venue's current fee schedule before you choose it.
    """
    return peak * 4.0 * price * (1.0 - price)


@dataclass(frozen=True)
class Friction:
    slippage: float = 0.0  # dollars per share added to the ask
    depth_cap: float | None = None  # share of the shown ask size you can take; None = no cap
    latency_ticks: int = 0  # fill this many ticks after the signal tick
    fee_peak: float = 0.0  # see fee_per_share
    oracle_noise: float = 0.0  # std, in price units, added to the final price of proxy labels
    tie_rule: str = "ge"  # "ge": a tie resolves YES; "gt": a tie resolves NO

    def __post_init__(self) -> None:
        if self.slippage < 0 or self.fee_peak < 0 or self.oracle_noise < 0:
            raise ValueError("slippage, fee_peak and oracle_noise must not be negative")
        if self.depth_cap is not None and not 0 < self.depth_cap <= 1:
            raise ValueError("depth_cap must be in (0, 1] or None")
        if self.latency_ticks < 0:
            raise ValueError("latency_ticks must not be negative")
        if self.tie_rule not in ("ge", "gt"):
            raise ValueError("tie_rule must be 'ge' or 'gt'")


FRICTIONLESS = Friction()

# The scenarios in the project's log after its fee and settlement audit.  They are
# guesses, not measurements: fit them to your own paper or live fills before you trust
# them.  The fee peak is the value the log recorded for 5-minute crypto markets in
# April 2026; it was not checked again.
SCENARIOS: dict[str, Friction] = {
    "frictionless": FRICTIONLESS,
    "fee only": Friction(fee_peak=0.018),
    "realistic": Friction(slippage=0.01, depth_cap=0.3, latency_ticks=1, fee_peak=0.018, oracle_noise=1.5),
    "heavy": Friction(slippage=0.02, depth_cap=0.2, latency_ticks=2, fee_peak=0.018, oracle_noise=2.0),
    "pessimistic": Friction(slippage=0.03, depth_cap=0.1, latency_ticks=3, fee_peak=0.025, oracle_noise=3.0),
}


def fill(market: Market, trade: Trade, friction: Friction = FRICTIONLESS) -> Trade | None:
    """The trade as it would fill, or None if it cannot fill.

    The signal tick is the last tick at or before the trade time, never a later one.
    With a depth cap, a tick that does not show an ask size cannot fill.
    """
    i = market.index_at(trade.t)
    if i is None:
        return None
    j = min(i + friction.latency_ticks, len(market.ticks) - 1)
    tick = market.ticks[j]
    ask = tick.ask(trade.side)
    if ask is None:
        return None
    size = trade.size
    if friction.depth_cap is not None:
        shown = tick.ask_size(trade.side)
        if shown is None:
            return None
        size = min(size, math.floor(shown * friction.depth_cap))
    if size <= 0:
        return None
    price = min(1.0, ask + friction.slippage + fee_per_share(ask, friction.fee_peak))
    return Trade(t=tick.t, side=trade.side, price=price, size=size)


def settle(market: Market, friction: Friction, rng: random.Random) -> tuple[str, str]:
    """(outcome, source).  The venue's resolution when known; otherwise a proxy label."""
    if market.outcome is not None:
        return market.outcome, "venue"
    noise = rng.gauss(0.0, friction.oracle_noise) if friction.oracle_noise > 0 else 0.0
    return proxy_outcome(market, friction.tie_rule, noise), "proxy"
