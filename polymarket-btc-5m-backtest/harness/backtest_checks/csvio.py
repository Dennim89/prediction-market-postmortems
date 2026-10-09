"""Read and write ticks as CSV, one row per tick.

Columns:
  market_id      window id, the same on every row of a window
  window_start   window start: Unix seconds, or ISO 8601 (no offset means UTC)
  window_end     window end, same formats
  start_price    the price the window is measured against
  outcome        YES or NO (UP and DOWN also accepted) as the venue resolved it; empty if unknown
  t              tick time, same formats
  spot           reference price the strategy sees
  sigma          volatility of log returns per second known at the tick; empty = 0 (unknown)
  yes_bid, yes_ask, no_bid, no_ask           best prices; empty if missing
  yes_ask_size, no_ask_size                  shares shown at the best asks; empty if unknown
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .model import NO, YES, Market, Tick

COLUMNS = [
    "market_id", "window_start", "window_end", "start_price", "outcome", "t", "spot", "sigma",
    "yes_bid", "yes_ask", "no_bid", "no_ask", "yes_ask_size", "no_ask_size",
]
_OUTCOMES = {"YES": YES, "UP": YES, "NO": NO, "DOWN": NO, "": None}


def parse_time(value: str) -> float:
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def format_time(t: float) -> str:
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds" if t % 1 else "seconds").replace("+00:00", "Z")


def _num(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value)


def read_ticks_csv(path: str | Path) -> list[Market]:
    """Markets in the order they first appear in the file."""
    markets: dict[str, Market] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(missing)}")
        for n, row in enumerate(reader, start=2):
            outcome_text = row["outcome"].strip().upper()
            if outcome_text not in _OUTCOMES:
                raise ValueError(f"{path}, line {n}: outcome must be YES, NO, UP, DOWN or empty")
            header = (
                parse_time(row["window_start"]),
                parse_time(row["window_end"]),
                float(row["start_price"]),
                _OUTCOMES[outcome_text],
            )
            mid = row["market_id"].strip()
            market = markets.get(mid)
            if market is None:
                market = Market(mid, header[0], header[1], header[2], [], header[3])
                markets[mid] = market
            elif (market.start, market.end, market.start_price, market.outcome) != header:
                raise ValueError(f"{path}, line {n}: window fields differ from earlier rows of {mid}")
            market.ticks.append(
                Tick(
                    t=parse_time(row["t"]),
                    spot=float(row["spot"]),
                    sigma=_num(row["sigma"]) or 0.0,
                    yes_bid=_num(row["yes_bid"]),
                    yes_ask=_num(row["yes_ask"]),
                    no_bid=_num(row["no_bid"]),
                    no_ask=_num(row["no_ask"]),
                    yes_ask_size=_num(row["yes_ask_size"]),
                    no_ask_size=_num(row["no_ask_size"]),
                )
            )
    for market in markets.values():
        market.ticks.sort(key=lambda tk: tk.t)
    return list(markets.values())


def write_ticks_csv(markets: list[Market], path: str | Path) -> int:
    """Write `markets` to `path`.  Returns the number of tick rows."""

    def cell(x):
        return "" if x is None else repr(x) if isinstance(x, float) else str(x)

    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for m in markets:
            for tk in m.ticks:
                writer.writerow([
                    m.market_id, format_time(m.start), format_time(m.end), cell(m.start_price),
                    m.outcome or "", format_time(tk.t), cell(tk.spot), cell(tk.sigma),
                    cell(tk.yes_bid), cell(tk.yes_ask), cell(tk.no_bid), cell(tk.no_ask),
                    cell(tk.yes_ask_size), cell(tk.no_ask_size),
                ])
                rows += 1
    return rows
