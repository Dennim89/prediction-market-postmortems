"""Summarise a paper-trading log and compare it with the backtest.

CSV columns: ts, market_id, side (YES or NO), price, size, outcome (YES or NO, UP or
DOWN; empty while the market is open).  Extra columns are ignored.

A win rate means nothing on its own.  A share bought at p (plus fee f) and held to
expiry breaks even at a win rate of p + f, so compare the win rate with that.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from .friction import fee_per_share
from .model import NO, YES

_SIDES = {"YES": YES, "UP": YES, "NO": NO, "DOWN": NO}


@dataclass(frozen=True)
class PaperTrade:
    ts: str
    market_id: str
    side: str
    price: float
    size: float
    outcome: str | None

    @property
    def resolved(self) -> bool:
        return self.outcome is not None

    @property
    def won(self) -> bool:
        return self.outcome == self.side


def read_paper_csv(path: str | Path) -> list[PaperTrade]:
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            side = _SIDES.get(row["side"].strip().upper())
            if side is None:
                raise ValueError(f"{path}, line {n}: side must be YES or NO")
            outcome_text = (row.get("outcome") or "").strip().upper()
            if outcome_text and outcome_text not in _SIDES:
                raise ValueError(f"{path}, line {n}: unknown outcome")
            out.append(PaperTrade(
                ts=row["ts"].strip(),
                market_id=row["market_id"].strip(),
                side=side,
                price=float(row["price"]),
                size=float(row["size"]),
                outcome=_SIDES.get(outcome_text),
            ))
    return out


@dataclass(frozen=True)
class PaperSummary:
    resolved: int
    open: int
    win_rate: float  # share of resolved trades that won
    avg_price: float  # average price per trade
    break_even: float  # win rate needed at these prices, fees included
    share_win_rate: float  # share of shares that won
    pnl_per_share_before_fees: float

    def gap_to(self, backtest_win_rate: float) -> float:
        """Backtest win rate minus paper win rate, in points."""
        return (backtest_win_rate - self.win_rate) * 100


def summarize(trades: list[PaperTrade], fee_peak: float = 0.0, one_per_market: bool = True) -> PaperSummary:
    """Summary of resolved trades.  With `one_per_market`, only the first resolved trade of
    each market counts (logs often repeat a position on several rows)."""
    resolved = [t for t in trades if t.resolved]
    if one_per_market:
        seen, kept = set(), []
        for t in resolved:
            if t.market_id not in seen:
                seen.add(t.market_id)
                kept.append(t)
        resolved = kept
    n = len(resolved)
    shares = sum(t.size for t in resolved)
    if not n or not shares:
        nan = math.nan
        return PaperSummary(0, len(trades) - len(resolved), nan, nan, nan, nan, nan)
    avg_price = sum(t.price for t in resolved) / n
    break_even = sum(t.price + fee_per_share(t.price, fee_peak) for t in resolved) / n
    win_shares = sum(t.size for t in resolved if t.won)
    price_shares = sum(t.price * t.size for t in resolved)
    return PaperSummary(
        resolved=n,
        open=sum(1 for t in trades if not t.resolved),
        win_rate=sum(t.won for t in resolved) / n,
        avg_price=avg_price,
        break_even=break_even,
        share_win_rate=win_shares / shares,
        pnl_per_share_before_fees=(win_shares - price_shares) / shares,
    )
