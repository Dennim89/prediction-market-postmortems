"""Append-only JSONL writer for raw events: one file per market per UTC day."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

import orjson

from collector.schema import EVENT_TYPES

NO_MARKET = "_no_market"  # file name for events written before a market is known


class JSONLWriter:
    def __init__(self, base_dir: str | Path, run_id: str, raw_subdir: str = "raw"):
        self.base_dir = Path(base_dir)
        self.run_id = run_id
        self.raw_subdir = raw_subdir
        self._seq = 0
        self._file: IO[str] | None = None
        self._current_market_id: str | None = None
        self._current_date: str | None = None
        self.current_path: Path | None = None

    def _ensure_file(self, market_id: str) -> IO[str]:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._file is None or self._current_market_id != market_id or self._current_date != date_str:
            self.close()
            subdir = self.base_dir / self.raw_subdir / date_str
            subdir.mkdir(parents=True, exist_ok=True)
            self.current_path = subdir / f"{market_id or NO_MARKET}.jsonl"
            self._file = open(self.current_path, "a", encoding="utf-8")
            self._current_market_id = market_id
            self._current_date = date_str
        return self._file

    def write(
        self,
        event_type: str,
        market_id: str,
        market_slug: str,
        payload: dict[str, Any],
        source: str = "polymarket",
        ts_utc: datetime | None = None,
        recv_ts_utc: datetime | None = None,
    ) -> None:
        """Write one event line and flush it."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event_type: {event_type}")
        now = datetime.now(timezone.utc)
        self._seq += 1
        fh = self._ensure_file(market_id)
        obj = {
            "ts_utc": (ts_utc or now).isoformat(),
            "recv_ts_utc": (recv_ts_utc or now).isoformat(),
            "source": source,
            "event_type": event_type,
            "market_id": market_id,
            "market_slug": market_slug,
            "interval": "15m",
            "run_id": self.run_id,
            "seq": self._seq,
            "payload": payload,
        }
        fh.write(orjson.dumps(obj).decode("utf-8") + "\n")
        fh.flush()

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
        self._file = None
        self._current_market_id = None
        self._current_date = None
