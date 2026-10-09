"""Checks on a table of trades, one per error the project made.

- lookahead: an input known after the entry time.  This also catches filters built from
  a market's whole life, such as an average spread that includes the minutes after entry.
- duplicate_keys: a join that multiplied rows.
- wrong_market: a position scored on another market's outcome.
"""

from __future__ import annotations

import pandas as pd


def lookahead(trades: pd.DataFrame, known_at: dict[str, str], entry_col: str = "entry_ts") -> pd.DataFrame:
    """For each input, how many trades used it before it was known.

    `known_at` maps an input column to the column with the time it became known.  An
    input with no known time (NULL) counts as unknown, not as late.
    """
    rows = []
    entry = pd.to_datetime(trades[entry_col])
    for feature, ts_col in known_at.items():
        known = pd.to_datetime(trades[ts_col])
        late = int((known > entry).sum())
        rows.append({"input": feature, "known_from": ts_col, "trades": len(trades),
                     "known_after_entry": late, "unknown_time": int(known.isna().sum()),
                     "share_late": late / len(trades) if len(trades) else 0.0})
    return pd.DataFrame(rows)


def duplicate_keys(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Keys that appear on more than one row, with their counts.  Empty is good."""
    counts = df.groupby(keys, dropna=False).size().rename("rows").reset_index()
    return counts[counts["rows"] > 1].reset_index(drop=True)


def wrong_market(trades: pd.DataFrame, traded_col: str = "market_id",
                 scored_col: str = "scored_market_id") -> pd.DataFrame:
    """Trades scored on the outcome of a market other than the one they were bought in."""
    return trades[trades[traded_col] != trades[scored_col]]
