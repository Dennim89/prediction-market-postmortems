"""Build one tick row from the current state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from collector.schema import TICK_COLUMNS

if TYPE_CHECKING:
    from collector.pipeline.state import CollectorState


def _r(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def build_tick(state: CollectorState, now: datetime | None = None) -> dict[str, Any]:
    """One row with the columns in TICK_COLUMNS.  Unknown values are None."""
    now = now or datetime.now(timezone.utc)
    tick: dict[str, Any] = dict.fromkeys(TICK_COLUMNS)
    tick["ts_utc"] = now.isoformat()

    if state.market is not None:
        tick["market_id"] = state.market.market_id
        tick["t_since_open_sec"] = _r(state.t_since_open_sec(now), 3)
        tick["t_left_sec"] = _r(state.t_left_sec(now), 3)

    open_price = state.btc_open_price
    spot_price = state.spot.price if state.spot else None
    tick["btc_open_price"] = open_price
    tick["btc_spot_price"] = spot_price
    if open_price and spot_price and state.market is not None:
        delta = spot_price - open_price
        minutes_left = max((state.t_left_sec(now) or 0.0) / 60.0, 0.5)
        tick["delta_spot_from_open"] = _r(delta)
        # Distance from the open price divided by the minutes left (floored at 0.5).
        tick["impulse_per_min"] = _r(abs(delta) / minutes_left)
        tick["dir"] = (delta > 0) - (delta < 0)

    for side, l1 in (("yes", state.yes_l1), ("no", state.no_l1)):
        if l1 is None:
            continue
        bid = l1.bid_price if l1.bid_price > 0 else None
        ask = l1.ask_price if l1.ask_price > 0 else None
        tick[f"{side}_bid"] = bid
        tick[f"{side}_ask"] = ask
        if bid is not None and ask is not None:
            tick[f"{side}_mid"] = _r((bid + ask) / 2)
            tick[f"spread_{side}"] = _r(ask - bid)
        # How old the best prices are at tick time.
        tick[f"{side}_book_age_sec"] = _r((now - l1.ts).total_seconds(), 3)

    tick["book_imbalance_yes"] = _r(state.book_imbalance_yes())
    tick["zscore_10m"] = _r(state.zscore_10m(now))
    return tick
