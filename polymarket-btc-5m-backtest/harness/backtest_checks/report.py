"""The plain-text report printed by `python -m backtest_checks demo` and `run`."""

from __future__ import annotations

import math
import statistics
from typing import Iterable

from . import controls
from .friction import FRICTIONLESS, SCENARIOS
from .harness import Result, Strategy, bootstrap, by_day, run
from .model import Market, proxy_outcome
from .strategies import best_tick_in_hindsight, naive


def pct(x: float) -> str:
    return "-" if x is None or math.isnan(x) else f"{x * 100:.1f}%"


def cents(x: float) -> str:
    return "-" if x is None or math.isnan(x) else f"{x * 100:+.1f}c"


def table(headers: list[str] | None, rows: list[list[str]], indent: str = "  ", left: tuple[int, ...] = (0,)) -> str:
    """Fixed-width text table; the columns in `left` are left-aligned, the rest right-aligned."""
    all_rows = ([headers] if headers else []) + rows
    widths = [max(len(str(c)) for c in col) for col in zip(*all_rows)]
    lines = []
    for r in all_rows:
        cells = [str(c).ljust(w) if i in left else str(c).rjust(w) for i, (c, w) in enumerate(zip(r, widths))]
        lines.append(indent + "  ".join(cells).rstrip())
    return "\n".join(lines)


def _mean(values: Iterable[float]) -> float:
    vals = [v for v in values if not math.isnan(v)]
    return statistics.mean(vals) if vals else math.nan


def _resample_row(name: str, results: list[Result]) -> list[str]:
    if not any(r.trades for r in results):
        return [name, "0", "-", "-", "-", "-"]
    losing = sum(r.pnl < 0 for r in results)
    return [
        name,
        f"{_mean(r.trades for r in results):.0f}",
        pct(_mean(r.share_win_rate for r in results)),
        pct(_mean(r.avg_price for r in results)),
        cents(_mean(r.pnl_per_share for r in results)),
        f"{losing}/{len(results)}",
    ]


def data_section(markets: list[Market]) -> str:
    days = list(by_day(markets))
    ticks = sum(len(m.ticks) for m in markets)
    known = [m for m in markets if m.outcome is not None and m.ticks]
    differ = sum(proxy_outcome(m) != m.outcome for m in known)
    lines = [
        "Data",
        f"  {len(markets)} markets over {len(days)} day(s): {', '.join(days)}; {ticks:,} ticks",
        f"  venue outcome known for {len(known)} of {len(markets)} markets"
        + ("" if len(known) == len(markets) else "; the others are scored on a proxy label"),
    ]
    if known:
        lines.append(
            f"  proxy label (last tick's price against the start price) differs from the venue's outcome "
            f"in {differ} of {len(known)} markets"
        )
    return "\n".join(lines)


def controls_section(markets: list[Market], strategy: Strategy, params: dict, seeds: list[int],
                     name: str) -> str:
    rows = []
    for label, strat in [
        ("do nothing", controls.do_nothing),
        (name, strategy),
        ("random side", controls.random_side(seed=1)),
        ("cheaper side", controls.cheaper_side),
        (f"{name}, inverted", controls.inverted(strategy)),
    ]:
        rows.append(_resample_row(label, bootstrap(strat, markets, params, seeds)))
    head = ["", "trades", "won", "break-even", "pnl/share", "losing"]
    return (f"1. Controls: all days, no friction, mean of {len(seeds)} resamples of the markets\n"
            "   (won = share of shares that won; break-even = average price paid; "
            "losing = resamples with a loss)\n" + table(head, rows))


def day_section(markets: list[Market], strategy: Strategy, params: dict, name: str) -> str:
    rows = []
    for day, group in by_day(markets).items():
        for i, (label, strat) in enumerate([(name, strategy), ("best tick in hindsight", best_tick_in_hindsight)]):
            r = run(strat, group, params, FRICTIONLESS)
            rows.append([day if i == 0 else "", str(len(group)) if i == 0 else "",
                         label, str(r.trades), pct(r.share_win_rate), pct(r.avg_price), cents(r.pnl_per_share)])
    head = ["day", "markets", "", "trades", "won", "break-even", "pnl/share"]
    return "2. Split by day, no friction\n" + table(head, rows, left=(0, 2))


def friction_section(markets: list[Market], strategy: Strategy, params: dict, seeds: list[int],
                     name: str) -> str:
    groups = by_day(markets)
    rows = []
    for scenario, fr in SCENARIOS.items():
        row = [scenario]
        for group in groups.values():
            results = bootstrap(strategy, group, params, seeds, fr)
            losing = sum(r.pnl < 0 for r in results)
            row.append(f"{cents(_mean(r.pnl_per_share for r in results))} ({losing}/{len(results)})")
        rows.append(row)
    head = ["scenario"] + list(groups)
    return (f"3. Friction, {name}, by day: pnl per share, mean of {len(seeds)} resamples (losing resamples)\n"
            + table(head, rows))


def leak_section(markets: list[Market], strategy: Strategy, params: dict, name: str) -> str:
    rows = []
    for label, strat in [(name, strategy), ("best tick in hindsight", best_tick_in_hindsight)]:
        rep = controls.future_leak(strat, markets, params)
        verdict = (f"OK ({rep.markets_checked} markets, {rep.checkpoints:,} checkpoints)" if rep.ok
                   else f"LEAKS: decisions changed in {len(rep.leaking)} of {rep.markets_checked} markets")
        rows.append([label, verdict])
    return "4. Lookahead: each market re-run on copies cut at checkpoints\n" + table(None, rows)


def full_report(markets: list[Market], strategy: Strategy = naive, params: dict | None = None,
                seeds: Iterable[int] = range(16), name: str = "naive rule") -> str:
    params = params or {}
    seeds = list(seeds)
    parts = [
        data_section(markets),
        controls_section(markets, strategy, params, seeds, name),
        day_section(markets, strategy, params, name),
        friction_section(markets, strategy, params, seeds, name),
        leak_section(markets, strategy, params, name),
    ]
    return "\n\n".join(parts)
