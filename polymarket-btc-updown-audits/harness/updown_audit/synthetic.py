"""Synthetic markets, quotes and candles in the layout of db.py.  Written from scratch.

- A reference price moves as a random walk, one step a second.  The candles are built
  from it.
- The venue settles each window on its own price: the reference price plus independent
  noise (`venue_noise`).  A label taken from the candles therefore disagrees with the
  venue now and then, mostly when the window ends close to where it started.
- 5-minute and 15-minute windows run back to back.  The book of each market is quoted
  every second at the fair probability of Up given the reference price, plus noise, with a
  spread that narrows once the price is within 5 cents of 0 or 1.
- A few quote rows are deliberately crossed (both best bids add up to more than $1) so
  the book audit has something to find.

The quotes are fair: nothing here can be traded at a profit.  The data is built to show
what the audits report, not to describe the real markets.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .db import TF_MINUTES

PRE_SEC = 180  # reference prices before the first window, so the first candles exist


def norm_cdf(x: np.ndarray) -> np.ndarray:
    """Standard normal CDF (Abramowitz and Stegun 7.1.26, error below 1e-6)."""
    x = np.asarray(x, dtype=float)
    z = np.abs(x) / np.sqrt(2.0)
    t = 1.0 / (1.0 + 0.3275911 * z)
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    erf = 1.0 - poly * np.exp(-z * z)
    return 0.5 * (1.0 + np.sign(x) * erf)


def _epoch(ts: pd.Timestamp) -> int:
    """Unix seconds of a naive UTC timestamp."""
    return int((ts - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1))


def _quotes_for_tf(tf, n_sec, ref, venue, start, sigma_usd, venue_noise, quote_noise, spreads, rng):
    dur = TF_MINUTES[tf] * 60
    s = np.arange(n_sec)  # seconds since the first window start
    a = (s // dur) * dur  # window start of each second
    t_left = (a + dur - s).astype(float)
    venue_start = venue[PRE_SEC + a]
    scale = np.sqrt(sigma_usd**2 * t_left + venue_noise**2)
    p_up = norm_cdf((ref[PRE_SEC + s] - venue_start) / scale)
    mid = np.clip(p_up + rng.normal(0.0, quote_noise, n_sec), 0.005, 0.995)
    spread = np.where((mid <= 0.05) | (mid >= 0.95), spreads[1], spreads[0])
    yes_bid = np.clip(np.floor((mid - spread / 2) * 100 + 1e-9) / 100, 0.01, 0.98)
    yes_ask = np.clip(np.ceil((mid + spread / 2) * 100 - 1e-9) / 100, 0.02, 0.99)
    yes_ask = np.where(yes_ask <= yes_bid, yes_bid + 0.01, yes_ask)
    return pd.DataFrame({
        "market_id": [f"btc-updown-{tf}-{e}" for e in _epoch(start) + a],
        "ts": start + pd.to_timedelta(s, unit="s"),
        "yes_bid": yes_bid.round(2),
        "yes_ask": yes_ask.round(2),
        "no_bid": (1.0 - yes_ask).round(2),
        "no_ask": (1.0 - yes_bid).round(2),
    })


def generate(
    hours: int = 72,
    seed: int = 0,
    start: str = "2026-01-05 00:00:00",
    sigma_usd: float = 5.0,
    venue_noise: float = 2.0,
    quote_noise: float = 0.01,
    spreads: tuple[float, float] = (0.02, 0.01),
    crossed_rows: int = 3,
    timeframes: tuple[str, ...] = ("5m", "15m"),
) -> dict[str, pd.DataFrame]:
    """Frames `markets`, `quotes` and `candles` covering `hours` hours from `start` (UTC).

    `spreads` is (spread, spread once the mid is within 5 cents of 0 or 1).
    """
    rng = np.random.default_rng(seed)
    n_sec = hours * 3600
    t0 = pd.Timestamp(start)
    steps = rng.normal(0.0, sigma_usd, n_sec + 2 * PRE_SEC)
    ref = 100_000.0 + np.concatenate([[0.0], np.cumsum(steps)])  # ref[PRE_SEC + s]: price at t0 + s
    venue = ref + rng.normal(0.0, venue_noise, ref.size)

    markets = []
    for tf in timeframes:
        dur = TF_MINUTES[tf] * 60
        a = np.arange(0, n_sec, dur)
        up = venue[PRE_SEC + a + dur] >= venue[PRE_SEC + a]
        starts = t0 + pd.to_timedelta(a, unit="s")
        markets.append(pd.DataFrame({
            "market_id": [f"btc-updown-{tf}-{e}" for e in _epoch(t0) + a],
            "tf": tf,
            "start_ts": starts,
            "end_ts": starts + pd.Timedelta(seconds=dur),
            "winner": np.where(up, "Up", "Down"),
        }))
    quotes = pd.concat(
        [_quotes_for_tf(tf, n_sec, ref, venue, t0, sigma_usd, venue_noise, quote_noise, spreads, rng)
         for tf in timeframes],
        ignore_index=True,
    )
    if crossed_rows:
        rows = rng.choice(len(quotes), size=crossed_rows, replace=False)
        quotes.loc[rows, "no_bid"] = (1.0 - quotes.loc[rows, "yes_bid"] + 0.01).round(2)

    minutes = np.arange(-PRE_SEC // 60, (n_sec + PRE_SEC) // 60 - 1)
    candles = pd.DataFrame({
        "open_time": t0 + pd.to_timedelta(minutes * 60, unit="s"),
        "close": ref[PRE_SEC + minutes * 60 + 59].round(2),
    })
    return {"markets": pd.concat(markets, ignore_index=True), "quotes": quotes, "candles": candles}
