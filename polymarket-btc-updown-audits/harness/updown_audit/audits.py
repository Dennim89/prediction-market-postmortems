"""Data audits over the tables in db.py.  Each function returns a pandas DataFrame.

Run them before any strategy result.  They answer: is the data complete, are the labels
right, do the books make sense, and how do timeframes relate to each other.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from .db import TF_MINUTES, UP_DOWN


_BY_LENGTH = "CASE tf " + " ".join(f"WHEN '{tf}' THEN {m}" for tf, m in TF_MINUTES.items()) + " END"


def _tf(tf: str) -> int:
    if tf not in TF_MINUTES:
        raise ValueError(f"tf must be one of {', '.join(TF_MINUTES)}")
    return TF_MINUTES[tf]


def coverage(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Per timeframe: markets, quote rows, markets without quotes, first and last quote."""
    return con.execute(f"""
        SELECT m.tf, count(DISTINCT m.market_id) AS markets, count(q.market_id) AS quote_rows,
               count(DISTINCT m.market_id) - count(DISTINCT q.market_id) AS markets_without_quotes,
               min(q.ts) AS first_quote, max(q.ts) AS last_quote
        FROM markets m LEFT JOIN quotes q USING (market_id)
        GROUP BY m.tf ORDER BY any_value({_BY_LENGTH.replace("tf", "m.tf", 1)}), m.tf
    """).df()


def window_lengths(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Markets whose end minus start is not their timeframe.

    In the project, the start field of the market data was the time a market was created,
    about a day before its window.  A start time loaded from such a field fails this check.
    """
    cases = " ".join(f"WHEN '{tf}' THEN {mins}" for tf, mins in TF_MINUTES.items())
    return con.execute(f"""
        SELECT tf, count(*) AS markets,
               count(*) FILTER (WHERE date_diff('second', start_ts, end_ts) <> 60 * (CASE tf {cases} END))
                   AS wrong_length
        FROM markets GROUP BY tf ORDER BY any_value({_BY_LENGTH})
    """).df()


def winner_balance(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Share of Up outcomes per timeframe.  Far from one half needs an explanation."""
    return con.execute(f"""
        SELECT tf, count(*) AS markets, avg(CASE WHEN {UP_DOWN} = 'Up' THEN 1.0 ELSE 0.0 END) AS up_share
        FROM markets WHERE winner IS NOT NULL GROUP BY tf ORDER BY any_value({_BY_LENGTH})
    """).df()


def _proxy_sql(tf: str, start_offset_min: int, end_offset_min: int, tie: str) -> str:
    """Venue winner next to a candle label: close of the candle opening at end + end_offset
    against close of the candle opening at end + start_offset."""
    if tie not in ("up", "down"):
        raise ValueError("tie must be 'up' or 'down'")
    up_if = ">=" if tie == "up" else ">"
    return f"""
        SELECT m.market_id, m.end_ts, {UP_DOWN} AS venue,
               ce.close - cs.close AS move,
               CASE WHEN ce.close {up_if} cs.close THEN 'Up' ELSE 'Down' END AS proxy
        FROM markets m
        JOIN candles cs ON cs.open_time = m.end_ts + INTERVAL '{int(start_offset_min)} minutes'
        JOIN candles ce ON ce.open_time = m.end_ts + INTERVAL '{int(end_offset_min)} minutes'
        WHERE m.tf = '{tf}' AND m.winner IS NOT NULL
    """


def label_agreement(con: duckdb.DuckDBPyConnection, tf: str, tie: str = "up") -> pd.DataFrame:
    """How often a candle label agrees with the venue's outcome, for four candle alignments.

    Candles are keyed by the minute they open.  For a window that ends at E and lasts D
    minutes, the candle that closes at the window start opens at E - D - 1, and the one
    that closes at the end opens at E - 1 (alignment A).  B, C and D are off by a minute at
    one end or both: the project tried all four to find the right one.
    `tie` says how a zero move resolves: the project's notes record ties going Up on
    Polymarket's 5-minute markets.
    """
    d = _tf(tf)
    schemes = [("A", -d - 1, -1), ("B", -d, 0), ("C", -d, -1), ("D", -d - 1, 0)]
    rows = []
    for name, s, e in schemes:
        n, agree = con.execute(f"""
            SELECT count(*), avg(CASE WHEN venue = proxy THEN 1.0 ELSE 0.0 END)
            FROM ({_proxy_sql(tf, s, e, tie)})
        """).fetchone()
        rows.append({"alignment": name, "start_candle_opens": f"end{s:+d}m", "end_candle_opens": f"end{e:+d}m",
                     "markets": n, "agree": agree})
    return pd.DataFrame(rows)


def disagreement_by_move(con: duckdb.DuckDBPyConnection, tf: str, edges: tuple[float, ...] = (5, 20, 60),
                         tie: str = "up") -> pd.DataFrame:
    """Label disagreement (alignment A) by the size of the candle move in the window."""
    d = _tf(tf)
    edges = sorted(edges)
    cases = " ".join(f"WHEN abs(move) < {float(x)} THEN {i}" for i, x in enumerate(edges))
    labels = [f"under {edges[0]:g}"] + [f"{lo:g} to {hi:g}" for lo, hi in zip(edges, edges[1:])] + [f"{edges[-1]:g} or more"]
    df = con.execute(f"""
        SELECT CASE {cases} ELSE {len(edges)} END AS bucket, count(*) AS markets,
               avg(CASE WHEN venue <> proxy THEN 1.0 ELSE 0.0 END) AS disagree
        FROM ({_proxy_sql(tf, -d - 1, -1, tie)}) GROUP BY bucket ORDER BY bucket
    """).df()
    df.insert(0, "abs_move", [labels[int(b)] for b in df.pop("bucket")])
    return df


def same_end_agreement(con: duckdb.DuckDBPyConnection, short: str = "5m", long: str = "15m") -> pd.DataFrame:
    """When a short and a long window end at the same time, how often their outcomes agree.

    They are different bets: the short one is about the last minutes only.  Scoring a
    position in one on the outcome of the other is a wrong-label error.
    """
    _tf(short), _tf(long)
    return con.execute(f"""
        WITH s AS (SELECT end_ts, {UP_DOWN} AS w FROM markets WHERE tf = '{short}' AND winner IS NOT NULL),
             l AS (SELECT end_ts, {UP_DOWN} AS w FROM markets WHERE tf = '{long}' AND winner IS NOT NULL)
        SELECT count(*) AS pairs, avg(CASE WHEN s.w = l.w THEN 1.0 ELSE 0.0 END) AS agree
        FROM s JOIN l USING (end_ts)
    """).df()


def book_sanity(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Rows where both best bids add to more than $1, or both best asks to less than $1."""
    return con.execute(f"""
        SELECT m.tf, count(*) AS rows,
               count(*) FILTER (WHERE q.yes_bid + q.no_bid > 1.0 + 1e-9) AS bids_over_1,
               count(*) FILTER (WHERE q.yes_ask + q.no_ask < 1.0 - 1e-9) AS asks_under_1,
               max(q.yes_bid + q.no_bid) AS max_bid_sum, min(q.yes_ask + q.no_ask) AS min_ask_sum
        FROM quotes q JOIN markets m USING (market_id)
        WHERE q.yes_bid IS NOT NULL AND q.no_bid IS NOT NULL AND q.yes_ask IS NOT NULL AND q.no_ask IS NOT NULL
        GROUP BY m.tf ORDER BY any_value({_BY_LENGTH.replace("tf", "m.tf", 1)})
    """).df()


def calibration(con: duckdb.DuckDBPyConnection, tf: str, seconds_before_end: int = 60,
                bucket: float = 0.1) -> pd.DataFrame:
    """Last mid price at or before `seconds_before_end` before the end, bucketed, against the
    share of Up outcomes.  A fair market's Up share sits inside each bucket."""
    _tf(tf)
    return con.execute(f"""
        WITH last AS (
            SELECT m.market_id, {UP_DOWN} AS w, arg_max((q.yes_bid + q.yes_ask) / 2, q.ts) AS mid
            FROM markets m JOIN quotes q USING (market_id)
            WHERE m.tf = '{tf}' AND q.yes_bid IS NOT NULL AND q.yes_ask IS NOT NULL
              AND q.ts <= m.end_ts - INTERVAL '{int(seconds_before_end)} seconds'
            GROUP BY m.market_id, w
        )
        SELECT least(floor(mid / {float(bucket)} + 1e-9) * {float(bucket)}, 1 - {float(bucket)}) AS bucket_from,
               count(*) AS markets, avg(mid) AS avg_mid, avg(CASE WHEN w = 'Up' THEN 1.0 ELSE 0.0 END) AS up_share
        FROM last GROUP BY bucket_from ORDER BY bucket_from
    """).df()


def daily_density(con: duckdb.DuckDBPyConnection, tf: str) -> pd.DataFrame:
    """Quote rows and markets per UTC day, with the share of the median day.  Thin days are
    holes in the data."""
    _tf(tf)
    df = con.execute(f"""
        SELECT strftime(CAST(q.ts AS DATE), '%Y-%m-%d') AS day, count(*) AS rows,
               count(DISTINCT q.market_id) AS markets
        FROM quotes q JOIN markets m USING (market_id) WHERE m.tf = '{tf}'
        GROUP BY day ORDER BY day
    """).df()
    if len(df):
        df["of_median"] = df["rows"] / df["rows"].median()
    return df
