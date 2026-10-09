"""The project's starting rule, built from the tables in db.py, with the time each input
became known.

Rule: when a 5-minute market inside a 15-minute window is about to close pinned near 1
(or 0), buy Up (or Down) on the 15-minute market at its ask and hold to expiry.  The
threshold is an argument with no default.

Every input comes with the time it became known (`*_ts` columns), so checks.lookahead
can test it against the entry time.  Two inputs are deliberately unusable, to show the
check at work: `lifetime_spread` (the 15-minute market's average spread over its whole
life, known only at its end) and `m5_vote` (the average close of all three 5-minute
markets in the window, known only near its end).
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from .db import UP_DOWN


def pin_candidates(con: duckdb.DuckDBPyConnection, lead_sec: int = 5) -> pd.DataFrame:
    """One row per (15-minute market, 5-minute market inside it).

    entry_ts is `lead_sec` seconds before the 5-minute market ends.  Prices are the last
    quotes at or before entry_ts (never later); entry_quote_age_sec says how old they are.
    slot is 1, 2 or 3 for the 5-minute market ending 10, 5 or 0 minutes before the
    15-minute one.
    """
    return con.execute(f"""
        WITH m15 AS (
            SELECT market_id AS m15_id, start_ts AS start15, end_ts AS end15, {UP_DOWN} AS winner15
            FROM markets WHERE tf = '15m'),
        m5 AS (
            SELECT market_id AS m5_id, start_ts AS start5, end_ts AS end5, {UP_DOWN} AS winner5
            FROM markets WHERE tf = '5m'),
        pairs AS (
            SELECT m15.*, m5.*,
                   CAST(3 - date_diff('minute', m5.end5, m15.end15) / 5 AS INTEGER) AS slot,
                   m5.end5 - INTERVAL '{int(lead_sec)} seconds' AS entry_ts
            FROM m15 JOIN m5 ON m5.start5 >= m15.start15 AND m5.end5 <= m15.end15),
        two_sided AS (
            SELECT * FROM quotes WHERE yes_bid IS NOT NULL AND yes_ask IS NOT NULL),
        sig AS (
            SELECT p.*, q.ts AS m5_close_ts, (q.yes_bid + q.yes_ask) / 2 AS m5_close
            FROM pairs p ASOF LEFT JOIN two_sided q ON p.m5_id = q.market_id AND p.entry_ts >= q.ts),
        ent AS (
            SELECT s.*, q.ts AS entry_quote_ts,
                   date_diff('second', q.ts, s.entry_ts) AS entry_quote_age_sec,
                   q.yes_bid AS yes_bid15, q.yes_ask AS yes_ask15, q.no_bid AS no_bid15, q.no_ask AS no_ask15
            FROM sig s ASOF LEFT JOIN quotes q ON s.m15_id = q.market_id AND s.entry_ts >= q.ts),
        life AS (
            SELECT market_id AS m15_id, avg(yes_ask - yes_bid) AS lifetime_spread
            FROM two_sided GROUP BY market_id),
        after AS (
            SELECT e.m15_id, e.m5_id, min(q.yes_bid) AS min_yes_bid_after, min(q.no_bid) AS min_no_bid_after
            FROM ent e JOIN quotes q ON q.market_id = e.m15_id AND q.ts > e.entry_ts AND q.ts < e.end15
            GROUP BY e.m15_id, e.m5_id),
        votes AS (
            SELECT m15_id, avg(m5_close) AS m5_vote, max(m5_close_ts) AS m5_vote_ts
            FROM sig GROUP BY m15_id)
        SELECT e.*, e.yes_ask15 - e.yes_bid15 AS spread_at_entry, l.lifetime_spread,
               a.min_yes_bid_after, a.min_no_bid_after, v.m5_vote, v.m5_vote_ts
        FROM ent e
        LEFT JOIN life l USING (m15_id)
        LEFT JOIN after a USING (m15_id, m5_id)
        LEFT JOIN votes v USING (m15_id)
        ORDER BY e.end15, e.slot
    """).df()


def _trades(c: pd.DataFrame, up: pd.Series, down: pd.Series) -> pd.DataFrame:
    t = c[up | down].copy()
    is_up = up[up | down].to_numpy()
    t["side"] = np.where(is_up, "Up", "Down")
    t["entry_price"] = np.where(is_up, t["yes_ask15"], t["no_ask15"])
    t["min_bid_after"] = np.where(is_up, t["min_yes_bid_after"], t["min_no_bid_after"])
    t["market_id"] = t["m15_id"]  # the market the position is in
    t["scored_market_id"] = t["m15_id"]  # the market whose outcome scores it
    t["won"] = t["side"] == t["winner15"]
    return t[t["entry_price"].notna()].reset_index(drop=True)


def pin_trades(candidates: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Trades of the pin rule: Up when the 5-minute close is at or above `threshold`,
    Down when it is at or below 1 - threshold."""
    if not 0.5 < threshold < 1:
        raise ValueError("threshold must be between 0.5 and 1")
    close = candidates["m5_close"]
    return _trades(candidates, close >= threshold, close <= 1 - threshold)


def vote_trades(candidates: pd.DataFrame, slot: int = 1) -> pd.DataFrame:
    """A lookahead example: at `slot`, trade the direction of the average close of all
    three 5-minute markets in the window.  Two of them close after the entry."""
    c = candidates[candidates["slot"] == slot]
    return _trades(c, c["m5_vote"] >= 0.5, c["m5_vote"] < 0.5)
