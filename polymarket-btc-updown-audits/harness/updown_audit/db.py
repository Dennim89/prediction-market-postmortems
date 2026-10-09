"""The three tables the audits read, and how to load them into DuckDB.

markets   one row per market
  market_id  VARCHAR    any unique id
  tf         VARCHAR    '5m', '15m' or '1h': the window length
  start_ts   TIMESTAMP  window start, UTC (not the time the market was listed)
  end_ts     TIMESTAMP  window end, UTC
  winner     VARCHAR    the venue's resolution: 'Up' or 'Down' ('Yes' and 'No' are read as Up and Down)

quotes    best prices of both outcomes, one row per market and time
  market_id  VARCHAR
  ts         TIMESTAMP  UTC
  yes_bid, yes_ask, no_bid, no_ask  DOUBLE, NULL when a side is empty

candles   1-minute candles of a reference price, for example an exchange's BTC price
  open_time  TIMESTAMP  start of the minute, UTC
  close      DOUBLE     last price of the minute

Only up/down markets are covered.  Multi-strike markets need their strike and are not.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd

TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60}

SCHEMA = {
    "markets": {"market_id": "VARCHAR", "tf": "VARCHAR", "start_ts": "TIMESTAMP", "end_ts": "TIMESTAMP",
                "winner": "VARCHAR"},
    "quotes": {"market_id": "VARCHAR", "ts": "TIMESTAMP", "yes_bid": "DOUBLE", "yes_ask": "DOUBLE",
               "no_bid": "DOUBLE", "no_ask": "DOUBLE"},
    "candles": {"open_time": "TIMESTAMP", "close": "DOUBLE"},
}

# SQL for the winner as 'Up' or 'Down'.
UP_DOWN = ("CASE WHEN winner IN ('Up', 'Yes') THEN 'Up' "
           "WHEN winner IN ('Down', 'No') THEN 'Down' END")


def connect(path: str | Path | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection: a database file, or in memory when `path` is None."""
    if path is None:
        return duckdb.connect()
    return duckdb.connect(str(path), read_only=read_only)


def load_frames(con: duckdb.DuckDBPyConnection, **frames: pd.DataFrame) -> None:
    """Create the tables from pandas frames, for example load_frames(con, markets=df1, ...).

    Columns are cast to the types in SCHEMA; extra columns are dropped.
    """
    for name, df in frames.items():
        if name not in SCHEMA:
            raise ValueError(f"unknown table {name!r}; expected one of {', '.join(SCHEMA)}")
        missing = [c for c in SCHEMA[name] if c not in df.columns]
        if missing:
            raise ValueError(f"{name}: missing columns {', '.join(missing)}")
        cols = ", ".join(f"CAST({c} AS {t}) AS {c}" for c, t in SCHEMA[name].items())
        con.register("_frame", df)
        try:
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT {cols} FROM _frame")
        finally:
            con.unregister("_frame")


def check_schema(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Problems with the tables, as sentences.  Empty when the schema is fine."""
    problems = []
    have = {r[0]: r[1] for r in con.execute(
        "SELECT table_name, list(column_name) FROM information_schema.columns GROUP BY table_name").fetchall()}
    for table, cols in SCHEMA.items():
        if table not in have:
            problems.append(f"table {table} is missing")
            continue
        missing = [c for c in cols if c not in have[table]]
        if missing:
            problems.append(f"table {table} has no column {', '.join(missing)}")
    if "markets" in have and not problems:
        bad = con.execute(
            "SELECT count(*) FROM markets WHERE tf NOT IN ('5m', '15m', '1h') "
            "OR winner IS NULL OR winner NOT IN ('Up', 'Down', 'Yes', 'No')").fetchone()[0]
        if bad:
            problems.append(f"{bad} markets have a tf other than 5m, 15m, 1h or no Up/Down winner")
    return problems


def load_dotenv(path: str | Path = ".env") -> None:
    """Read KEY=VALUE lines from `path` into the environment, without overriding it."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
