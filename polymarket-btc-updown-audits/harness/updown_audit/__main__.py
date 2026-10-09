"""Command line: python -m updown_audit {demo,audit,synth} --help"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

from . import db, synthetic
from .report import audit_report, demo_report


def main(argv: list[str] | None = None) -> int:
    db.load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m updown_audit",
                                     description="Data audits and an evaluation harness for up/down markets.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("demo", help="build synthetic data in memory and run everything (offline)")
    p.add_argument("--hours", type=int, default=72)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--threshold", type=float, default=0.9, help="pin threshold for the example rule")
    p.add_argument("--fee-rate", type=float, default=0.10, help="fee rate, see evaluate.fee_per_share")

    p = sub.add_parser("audit", help="run the data audits on a DuckDB file with the tables in db.py")
    p.add_argument("--db", default=os.environ.get("UPDOWN_DB"), help="DuckDB file (default: $UPDOWN_DB)")

    p = sub.add_parser("synth", help="write the synthetic tables to a DuckDB file")
    p.add_argument("--out", required=True)
    p.add_argument("--hours", type=int, default=72)
    p.add_argument("--seed", type=int, default=0)

    args = parser.parse_args(argv)

    if args.command == "demo":
        frames = synthetic.generate(hours=args.hours, seed=args.seed)
        con = db.connect()
        db.load_frames(con, **frames)
        start = frames["markets"]["start_ts"].min()
        split_at = start + pd.Timedelta(hours=args.hours / 2)
        print(f"Synthetic data, seed {args.seed}: {args.hours} hours, {len(frames['markets']):,} markets, "
              f"{len(frames['quotes']):,} quote rows.")
        print("The quotes are fair by construction: there is no edge to find. 3 quote rows are crossed on purpose.\n")
        print(demo_report(con, args.threshold, args.fee_rate, split_at))
    elif args.command == "audit":
        if not args.db:
            parser.error("give --db or set UPDOWN_DB")
        if not os.path.isfile(args.db):
            parser.error(f"no such file: {args.db}")
        con = db.connect(args.db, read_only=True)
        problems = db.check_schema(con)
        if problems:
            print("Schema problems:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        print(audit_report(con))
    elif args.command == "synth":
        frames = synthetic.generate(hours=args.hours, seed=args.seed)
        con = db.connect(args.out)
        db.load_frames(con, **frames)
        con.close()
        print(f"wrote {len(frames['markets']):,} markets, {len(frames['quotes']):,} quote rows and "
              f"{len(frames['candles']):,} candles to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
