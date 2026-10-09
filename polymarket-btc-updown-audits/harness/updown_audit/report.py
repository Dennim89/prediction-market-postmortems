"""Plain-text reports for `python -m updown_audit audit` and `demo`."""

from __future__ import annotations

import math

import duckdb
import pandas as pd

from . import audits, checks, evaluate, signals


def pct(x) -> str:
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.1f}%"


def cents(x) -> str:
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:+.2f}c"


def table(df: pd.DataFrame, formats: dict | None = None, indent: str = "    ") -> str:
    """Fixed-width text table.  `formats` maps a column to a function of one value."""
    formats = formats or {}
    cols = list(df.columns)
    fmts = [formats.get(c) or _default_for(df[c]) for c in cols]
    cells = [cols] + [[f(v) for f, v in zip(fmts, row)] for row in df.itertuples(index=False)]
    widths = [max(len(r[i]) for r in cells) for i in range(len(cols))]
    return "\n".join(indent + "  ".join(v.ljust(w) if i == 0 else v.rjust(w)
                                        for i, (v, w) in enumerate(zip(r, widths))).rstrip()
                     for r in cells)


def _default_for(col: pd.Series):
    if pd.api.types.is_bool_dtype(col):
        return str
    if pd.api.types.is_integer_dtype(col):
        return lambda v: f"{int(v):,}"
    if pd.api.types.is_float_dtype(col):
        return lambda v: "-" if pd.isna(v) else f"{v:,.2f}"
    if pd.api.types.is_datetime64_any_dtype(col):
        return lambda v: "-" if pd.isna(v) else pd.Timestamp(v).strftime("%Y-%m-%d %H:%M:%S")
    return lambda v: "-" if v is None else str(v)


def audit_report(con: duckdb.DuckDBPyConnection) -> str:
    """Every data audit, for the timeframes present."""
    tfs = [r[0] for r in con.execute("SELECT DISTINCT tf FROM markets ORDER BY tf").fetchall()]
    parts = ["Coverage", table(audits.coverage(con)),
             "Window lengths (end - start must equal the timeframe)", table(audits.window_lengths(con)),
             "Share of Up outcomes", table(audits.winner_balance(con), {"up_share": pct}),
             "Books: both bids over $1, both asks under $1", table(audits.book_sanity(con))]
    for tf in tfs:
        parts += [f"Labels from 1-minute candles against the venue's outcome, {tf}",
                  table(audits.label_agreement(con, tf), {"agree": pct}),
                  f"Disagreement by the size of the candle move, {tf} (alignment A)",
                  table(audits.disagreement_by_move(con, tf), {"disagree": pct}),
                  f"Calibration, {tf}: last mid 60 s before the end",
                  table(audits.calibration(con, tf), {"bucket_from": lambda v: f"{v:.1f}",
                                                      "avg_mid": lambda v: f"{v:.3f}", "up_share": pct}),
                  f"Quote rows per day, {tf}",
                  table(audits.daily_density(con, tf), {"of_median": lambda v: f"{v:.2f}"})]
    if "5m" in tfs and "15m" in tfs:
        parts += ["5- and 15-minute windows that end together", table(audits.same_end_agreement(con), {"agree": pct})]
    return "\n".join(p if p.startswith("    ") else "\n  " + p for p in parts).lstrip("\n")


def _rule_row(name: str, t: pd.DataFrame) -> dict:
    if not len(t):
        return {"rule": name, "trades": 0, "hit": math.nan, "avg_price": math.nan, "hit_minus_price": math.nan}
    hit = t["won"].mean()
    price = t["entry_price"].mean()
    return {"rule": name, "trades": len(t), "hit": hit, "avg_price": price, "hit_minus_price": hit - price}


def demo_report(con: duckdb.DuckDBPyConnection, threshold: float, fee_rate: float, split_at) -> str:
    """Audits, the lookahead check, the effect of late inputs, fees, split and sizing."""
    cand = signals.pin_candidates(con)
    pins = signals.pin_trades(cand, threshold)
    votes = signals.vote_trades(cand, slot=1)
    lowest = pins["lifetime_spread"].quantile(0.10)
    lowest_entry = pins["spread_at_entry"].quantile(0.10)
    known_at = {"m5_close": "m5_close_ts", "spread_at_entry": "entry_quote_ts",
                "lifetime_spread": "end15", "m5_vote": "m5_vote_ts"}
    rules = pd.DataFrame([
        _rule_row("pin rule", pins),
        _rule_row("pin rule, lifetime spread in lowest 10%", pins[pins["lifetime_spread"] <= lowest]),
        _rule_row("pin rule, spread at entry in lowest 10%", pins[pins["spread_at_entry"] <= lowest_entry]),
        _rule_row("vote of all three 5-minute markets, slot 1", votes),
    ])
    fmt_rules = {"hit": pct, "avg_price": pct, "hit_minus_price": lambda v: f"{v * 100:+.1f} pts"}
    ev = evaluate.evaluate(pins, fee_rate, split_at)[
        ["part", "trades", "days", "hit", "avg_price", "gross_per_share", "fee_per_share", "net_per_share",
         "fees_of_gross"]]
    fmt_ev = {"hit": pct, "avg_price": pct, "gross_per_share": cents, "fee_per_share": cents,
              "net_per_share": cents, "fees_of_gross": pct, "days": lambda v: f"{v:.1f}"}
    sizing = evaluate.sizing_check(pins, fee_rate, split_at)[["variant", "train_net_per_share", "test_net_per_share"]]
    fmt_sz = {"train_net_per_share": cents, "test_net_per_share": cents}
    return "\n".join([
        "1. Data audits",
        audit_report(con),
        "",
        f"2. Lookahead check: when each input of the pin rule (threshold {threshold}) became known",
        table(checks.lookahead(pins, known_at), {"share_late": pct}),
        f"   duplicate (market, slot) rows after the joins: {len(checks.duplicate_keys(pins, ['m15_id', 'slot']))}",
        f"   trades scored on another market's outcome: {len(checks.wrong_market(pins))}",
        "",
        "3. What late inputs do to the hit rate (on fair prices the hit rate should match the price)",
        table(rules, fmt_rules),
        "",
        f"4. Fees and the time split: pin rule, fee rate {fee_rate}, split at {pd.Timestamp(split_at)}",
        table(ev, fmt_ev),
        "",
        "5. Sizing fitted in-sample: one rule fitted on all data and on the train part only",
        table(sizing, fmt_sz),
    ])
