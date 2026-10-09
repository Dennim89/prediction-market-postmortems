"""Hand-made tables for the tests.  Everything here is made up."""

import pandas as pd

from updown_audit import db

T0 = pd.Timestamp("2026-01-05 00:00:00")


def ts(minutes=0, seconds=0):
    return T0 + pd.Timedelta(minutes=minutes, seconds=seconds)


def connect_with(markets, quotes=None, candles=None):
    """An in-memory database with hand-made tables (empty quotes and candles by default)."""
    con = db.connect()
    if quotes is None:
        quotes = pd.DataFrame({"market_id": pd.Series(dtype=str), "ts": pd.Series(dtype="datetime64[ns]"),
                               "yes_bid": [], "yes_ask": [], "no_bid": [], "no_ask": []})
    if candles is None:
        candles = pd.DataFrame({"open_time": pd.Series(dtype="datetime64[ns]"), "close": []})
    db.load_frames(con, markets=markets, quotes=quotes, candles=candles)
    return con


def market_rows(rows):
    """rows: (market_id, tf, start minute, winner)."""
    out = []
    for mid, tf, start_min, winner in rows:
        start = ts(start_min)
        out.append({"market_id": mid, "tf": tf, "start_ts": start,
                    "end_ts": start + pd.Timedelta(minutes=db.TF_MINUTES[tf]), "winner": winner})
    return pd.DataFrame(out)
