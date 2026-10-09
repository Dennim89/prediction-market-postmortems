"""Command line: python -m backtest_checks {demo,run,synth,paper} --help"""

from __future__ import annotations

import argparse
import sys

from . import csvio, paper, synthetic
from .report import full_report, pct
from .strategies import naive


def _strategy_params(args) -> dict:
    return {"window_sec": args.window_sec, "margin": args.margin, "size": args.size}


def _add_strategy_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--window-sec", type=float, default=10, help="act in the last N seconds (default 10)")
    p.add_argument("--margin", type=float, default=0.03, help="minimum edge over the ask (default 0.03)")
    p.add_argument("--size", type=float, default=10, help="shares per trade (default 10)")
    p.add_argument("--seeds", type=int, default=16, help="number of resamples (default 16)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backtest_checks",
                                     description="Friction model, sanity controls and a per-day split "
                                                 "for a taker backtest on 5-minute up/down markets.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("demo", help="run every check on synthetic data (offline)")
    p.add_argument("--markets-per-day", type=int, default=144)
    p.add_argument("--seed", type=int, default=7)
    _add_strategy_args(p)

    p = sub.add_parser("run", help="run every check on your own ticks (CSV)")
    p.add_argument("--ticks", required=True, help="CSV file, columns in backtest_checks/csvio.py")
    _add_strategy_args(p)

    p = sub.add_parser("synth", help="write the synthetic ticks to a CSV file")
    p.add_argument("--out", required=True)
    p.add_argument("--markets-per-day", type=int, default=144)
    p.add_argument("--seed", type=int, default=7)

    p = sub.add_parser("paper", help="summarise a paper-trading log (CSV)")
    p.add_argument("--log", required=True, help="CSV file: ts, market_id, side, price, size, outcome")
    p.add_argument("--fee-peak", type=float, default=0.0, help="fee per share at a price of 0.50 (default 0)")
    p.add_argument("--backtest-win-rate", type=float, help="the backtest's win rate, for example 0.85")

    args = parser.parse_args(argv)

    if args.command == "demo":
        markets = synthetic.generate(markets_per_day=args.markets_per_day, seed=args.seed)
        print("Synthetic data (seed %d). Day 1: quotes lag the reference price by 3 s; the volatility the\n"
              "strategy assumes is right. Day 2: no lag; true volatility is twice the assumed value.\n"
              % args.seed)
        print(full_report(markets, naive, _strategy_params(args), range(args.seeds)))
    elif args.command == "run":
        markets = csvio.read_ticks_csv(args.ticks)
        if not markets:
            print("no ticks in", args.ticks, file=sys.stderr)
            return 1
        print(full_report(markets, naive, _strategy_params(args), range(args.seeds)))
    elif args.command == "synth":
        markets = synthetic.generate(markets_per_day=args.markets_per_day, seed=args.seed)
        rows = csvio.write_ticks_csv(markets, args.out)
        print(f"wrote {rows:,} ticks of {len(markets)} synthetic markets to {args.out}")
    elif args.command == "paper":
        s = paper.summarize(paper.read_paper_csv(args.log), fee_peak=args.fee_peak)
        print(f"resolved trades: {s.resolved} (open: {s.open})")
        print(f"won: {pct(s.win_rate)} at an average price of {s.avg_price:.3f}")
        print(f"break-even win rate at these prices, fees included: {pct(s.break_even)}")
        print(f"pnl per share before fees: {s.pnl_per_share_before_fees * 100:+.1f}c")
        if args.backtest_win_rate is not None:
            print(f"backtest win rate minus paper win rate: {s.gap_to(args.backtest_win_rate):+.1f} points")
    return 0


if __name__ == "__main__":
    sys.exit(main())
