"""Command line: `run` the collector, or `validate` a raw JSONL file."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from collector.schema import EVENT_TYPES, RAW_FIELDS


def cmd_run(args: argparse.Namespace) -> int:
    import yaml
    from dotenv import find_dotenv, load_dotenv
    from pydantic import ValidationError

    from collector.config import load_config
    from collector.pipeline.scheduler import CollectorFailed, run_collector

    load_dotenv(find_dotenv(usecwd=True))  # ./.env or a parent's; never overrides real env vars
    try:
        cfg = load_config(args.config)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    if args.mock:
        cfg = cfg.model_copy(update={"market_provider": "mock", "spot_provider": "mock"})
    try:
        asyncio.run(run_collector(cfg=cfg, duration_sec=args.duration_sec))
    except CollectorFailed as exc:
        print(f"collector stopped with an error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


def validate_file(path: Path) -> tuple[int, list[str]]:
    """Check a raw JSONL file.  Returns (number of events, list of problems)."""
    problems: list[str] = []
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            count += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"line {lineno}: not JSON ({exc.msg})")
                continue
            if not isinstance(obj, dict):
                problems.append(f"line {lineno}: not a JSON object")
                continue
            missing = [f for f in RAW_FIELDS if f not in obj]
            if missing:
                problems.append(f"line {lineno}: missing fields {missing}")
            if obj.get("event_type") not in EVENT_TYPES:
                problems.append(f"line {lineno}: unknown event_type {obj.get('event_type')!r}")
    if count == 0:
        problems.append("no events in file")
    return count, problems


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"file not found: {path}", file=sys.stderr)
        return 1
    count, problems = validate_file(path)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"OK: {count} events")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m collector",
        description="Read-only collector for Polymarket 15-minute BTC Up/Down markets.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="collect until Ctrl+C (or --duration-sec)")
    run_p.add_argument("--config", "-c", default=None, help="YAML config (default: ./config.yaml if present)")
    run_p.add_argument("--mock", action="store_true", help="synthetic market and price, no network")
    run_p.add_argument("--duration-sec", type=float, default=None, help="stop after this many seconds")
    run_p.set_defaults(func=cmd_run)

    val_p = sub.add_parser("validate", help="check a raw JSONL file")
    val_p.add_argument("file", help="path to a raw .jsonl file")
    val_p.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    if getattr(args, "duration_sec", None) is not None and args.duration_sec <= 0:
        parser.error("--duration-sec must be greater than 0")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
