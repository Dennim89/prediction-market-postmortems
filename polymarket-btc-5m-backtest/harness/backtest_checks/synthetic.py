"""Synthetic 5-minute markets with one tick per second.  Written from scratch; no real data.

Each day is a run of consecutive 5-minute windows.  The reference price is a random walk
in log space.  A market maker quotes the fair probability of YES, with a spread, from
what it knows:

- `lag_sec`: the maker sees the reference price this many seconds late.  A strategy that
  sees the current price then has a real edge, which friction can erase.
- `true_sigma_mult`: the true volatility, as a multiple of the `sigma` written on each
  tick (the value a strategy reads).  Above 1 the strategy is overconfident and the
  maker, who knows the true volatility, is right.

The venue settles each window on its own price: the last reference price plus noise
(`oracle_noise`), so a label taken from the reference price is sometimes wrong when the
window ends close to its start price.

Defaults: day 1 has a 3-second lag and the volatility the strategy assumes is right; day 2
has no lag and twice the assumed volatility.  The data is built to show what the checks
report, not to describe any real market.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from .fair import fair_p_up
from .model import NO, YES, Market, Tick

WINDOW_SEC = 300


@dataclass(frozen=True)
class DayRegime:
    lag_sec: int = 0
    true_sigma_mult: float = 1.0


DEFAULT_DAYS = (DayRegime(lag_sec=3, true_sigma_mult=1.0), DayRegime(lag_sec=0, true_sigma_mult=2.0))


def _cents_down(x: float) -> float:
    return math.floor(x * 100 + 1e-9) / 100


def _cents_up(x: float) -> float:
    return math.ceil(x * 100 - 1e-9) / 100


def _quote(mid: float, spread: float) -> tuple[float, float]:
    bid = min(0.98, max(0.01, _cents_down(mid - spread / 2)))
    ask = min(0.99, max(0.02, _cents_up(mid + spread / 2)))
    if ask <= bid:
        ask = round(bid + 0.01, 2)
    return bid, ask


def generate(
    days: tuple[DayRegime, ...] = DEFAULT_DAYS,
    markets_per_day: int = 144,
    seed: int = 7,
    sigma: float = 0.0001,
    spread: float = 0.02,
    quote_noise: float = 0.005,
    oracle_noise: float = 1.5,
    start_price: float = 100_000.0,
    first_day: str = "2026-01-01",
) -> list[Market]:
    """Markets for each day in `days`, starting at midnight UTC of `first_day`."""
    rng = random.Random(seed)
    day0 = datetime.fromisoformat(first_day).replace(tzinfo=timezone.utc).timestamp()
    markets: list[Market] = []
    for d, regime in enumerate(days):
        true_sigma = sigma * regime.true_sigma_mult
        price = start_price
        for k in range(markets_per_day):
            start = day0 + d * 86_400 + k * WINDOW_SEC
            # Path: index i is the price at start + i seconds, i = -lag .. WINDOW_SEC.
            history = [price]
            for _ in range(regime.lag_sec):
                history.insert(0, history[0] / math.exp(rng.gauss(0.0, true_sigma)))
            path = [price]
            for _ in range(WINDOW_SEC):
                path.append(path[-1] * math.exp(rng.gauss(0.0, true_sigma)))
            full = history[:-1] + path  # full[j] is the price at start + j - lag
            open_price = round(path[0], 2)
            ticks = []
            for i in range(WINDOW_SEC):
                t_left = WINDOW_SEC - i
                seen_by_maker = full[i]  # the price lag seconds ago
                p_up = fair_p_up(seen_by_maker, open_price, true_sigma, t_left + regime.lag_sec)
                mid = min(0.99, max(0.01, p_up + rng.gauss(0.0, quote_noise)))
                yes_bid, yes_ask = _quote(mid, spread)
                ticks.append(
                    Tick(
                        t=start + i,
                        spot=round(path[i], 2),
                        sigma=sigma,
                        yes_bid=yes_bid,
                        yes_ask=yes_ask,
                        no_bid=round(1.0 - yes_ask, 2),
                        no_ask=round(1.0 - yes_bid, 2),
                        yes_ask_size=float(rng.randint(5, 200)),
                        no_ask_size=float(rng.randint(5, 200)),
                    )
                )
            settle_price = path[-1] + rng.gauss(0.0, oracle_noise)
            outcome = YES if settle_price >= open_price else NO
            markets.append(
                Market(
                    market_id=f"btc-updown-5m-{int(start)}",
                    start=start,
                    end=start + WINDOW_SEC,
                    start_price=open_price,
                    ticks=ticks,
                    outcome=outcome,
                )
            )
            price = path[-1]
    return markets
