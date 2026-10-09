"""Evaluation harness: fees from the first result, a time split, per-share and per-day
results, reproducible subsamples, and a check for sizing fitted in-sample.

A trades table needs: entry_ts, entry_price (the price paid per share), won (bool).
For a stop-loss exit it also needs min_bid_after: the lowest bid on your side after entry.
"""

from __future__ import annotations

import hashlib
from typing import Callable

import numpy as np
import pandas as pd

Sizing = Callable[[pd.DataFrame], pd.Series]


def fee_per_share(price, rate: float):
    """rate * p * (1 - p) per share and per side.

    This is how the project read Polymarket's fee fields for these markets in April 2026
    (rate 0.10).  Fee schedules change; look up the current one and pass its rate.
    """
    return rate * price * (1.0 - price)


def per_share(trades: pd.DataFrame, fee_rate: float, stop: float | None = None) -> pd.DataFrame:
    """Add gross, fee and net per share (dollars), and whether a stop fired.

    Hold to expiry: a winning share pays 1 - price, a losing one loses the price, and the
    entry fee is paid once.  With `stop`, a position whose bid fell below price - stop is
    sold there; that exit pays a second fee.  Selling exactly at the stop is optimistic.
    """
    out = trades.copy()
    p = out["entry_price"].astype(float).to_numpy()
    won = out["won"].astype(bool).to_numpy()
    hold = np.where(won, 1.0 - p, -p)
    fee = fee_per_share(p, fee_rate)
    stopped = np.zeros(len(out), dtype=bool)
    gross = hold
    if stop is not None:
        min_bid = out["min_bid_after"].astype(float).to_numpy()
        stopped = np.nan_to_num(min_bid, nan=np.inf) < p - stop
        gross = np.where(stopped, -stop, hold)
        fee = fee + np.where(stopped, fee_per_share(p - stop, fee_rate), 0.0)
    out["stopped"] = stopped
    out["gross"] = gross
    out["fee"] = fee
    out["net"] = gross - fee
    return out


def _shares(trades: pd.DataFrame, shares: Sizing | pd.Series | None) -> pd.Series:
    if shares is None:
        return pd.Series(1.0, index=trades.index)
    s = shares(trades) if callable(shares) else shares
    return pd.Series(s, index=trades.index).astype(float).clip(lower=0)


def _row(name: str, t: pd.DataFrame, w: pd.Series, days: float) -> dict:
    total = float(w.sum())
    traded = int((w > 0).sum())
    if not total:
        return {"part": name, "trades": 0, "shares": 0.0, "days": days}
    gross = float((t["gross"] * w).sum())
    fee = float((t["fee"] * w).sum())
    net = float((t["net"] * w).sum())
    return {
        "part": name,
        "trades": traded,
        "shares": total,
        "days": days,
        "hit": float((t["won"].astype(float) * w).sum() / total),
        "avg_price": float((t["entry_price"] * w).sum() / total),
        "gross_per_share": gross / total,
        "fee_per_share": fee / total,
        "net_per_share": net / total,
        "fees_of_gross": fee / gross if gross > 0 else np.nan,
        "net_per_day": net / days if days else np.nan,
    }


def evaluate(trades: pd.DataFrame, fee_rate: float, split_at, stop: float | None = None,
             shares: Sizing | pd.Series | None = None, start=None, end=None) -> pd.DataFrame:
    """Results for all trades, the part before `split_at` (train) and from it on (test).

    Per-day figures divide by the length of each period: from `start` (default: first
    entry) to `split_at`, and from `split_at` to `end` (default: last entry).  Comparing
    totals of periods of different length is a mistake this avoids.
    """
    t = per_share(trades, fee_rate, stop)
    w = _shares(t, shares)
    ts = pd.to_datetime(t["entry_ts"])
    split_at = pd.Timestamp(split_at)
    start = pd.Timestamp(start) if start is not None else ts.min()
    end = pd.Timestamp(end) if end is not None else ts.max()
    day = pd.Timedelta(days=1)
    train = ts < split_at
    return pd.DataFrame([
        _row("all", t, w, (end - start) / day),
        _row("train", t[train], w[train], (split_at - start) / day),
        _row("test", t[~train], w[~train], (end - split_at) / day),
    ])


def subsample(trades: pd.DataFrame, seed: int, frac: float = 0.8,
              keys: tuple[str, ...] = ("market_id", "entry_ts")) -> pd.DataFrame:
    """A reproducible subsample: a trade is kept when a hash of its keys and the seed falls
    below `frac`.  The same seed keeps the same trades in every run and on every machine.

    (The archived harness used Python's built-in hash(), which changes from one process to
    the next, so its seeds picked different trades on every run.)
    """
    def u(row) -> float:
        key = "|".join([str(seed)] + [str(row[k]) for k in keys])
        return int.from_bytes(hashlib.blake2b(key.encode(), digest_size=8).digest(), "big") / 2.0**64

    return trades[trades.apply(u, axis=1) < frac]


def fit_bucket_sizing(train: pd.DataFrame, fee_rate: float, by: tuple[str, ...] = ("slot", "side", "price_bucket"),
                      max_shares: float = 3.0, min_trades: int = 3) -> Sizing:
    """An example of sizing fitted to data: `max_shares` in buckets whose net per share was
    positive, none in buckets where it was negative, one share elsewhere.

    It is the kind of rule that looks good on the data it was fitted on.  It is here to
    show `sizing_check` at work, not as a way to size trades.
    """
    t = per_share(_with_bucket(train), fee_rate)
    stats = t.groupby(list(by))["net"].agg(["mean", "size"])

    def sizing(df: pd.DataFrame) -> pd.Series:
        d = _with_bucket(df)
        idx = pd.MultiIndex.from_frame(d[list(by)]) if len(by) > 1 else pd.Index(d[by[0]])
        s = stats.reindex(idx)
        size = np.where(s["size"].fillna(0).to_numpy() < min_trades, 1.0,
                        np.where(s["mean"].to_numpy() > 0, max_shares, 0.0))
        return pd.Series(size, index=df.index)

    return sizing


def _with_bucket(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["price_bucket"] = np.floor(d["entry_price"].astype(float) * 10 + 1e-9) / 10
    return d


def sizing_check(trades: pd.DataFrame, fee_rate: float, split_at,
                 fit: Callable[[pd.DataFrame, float], Sizing] = fit_bucket_sizing,
                 start=None, end=None) -> pd.DataFrame:
    """Compare flat one-share trades with a sizing rule fitted two ways:
    on all the data (in-sample, the test part included) and on the train part only.

    Only the train-only fit says anything about the test part.  If the in-sample fit looks
    much better on the test part, the sizing learned the test data.
    """
    split_at = pd.Timestamp(split_at)
    train = trades[pd.to_datetime(trades["entry_ts"]) < split_at]
    variants = [
        ("flat, one share", None),
        ("sized, fitted on all data", fit(trades, fee_rate)),
        ("sized, fitted on train only", fit(train, fee_rate)),
    ]
    rows = []
    for name, sizing in variants:
        r = evaluate(trades, fee_rate, split_at, shares=sizing, start=start, end=end).set_index("part")
        rows.append({
            "variant": name,
            "train_net_per_share": r.loc["train", "net_per_share"] if "net_per_share" in r else np.nan,
            "test_net_per_share": r.loc["test", "net_per_share"] if "net_per_share" in r else np.nan,
            "train_net_per_day": r.loc["train", "net_per_day"] if "net_per_day" in r else np.nan,
            "test_net_per_day": r.loc["test", "net_per_day"] if "net_per_day" in r else np.nan,
        })
    return pd.DataFrame(rows)
