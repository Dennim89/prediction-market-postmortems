"""CSV writer for tick rows: one file per market per UTC day."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

from collector.schema import TICK_COLUMNS


class CSVWriter:
    def __init__(self, base_dir: str | Path, ticks_subdir: str = "ticks"):
        self.base_dir = Path(base_dir)
        self.ticks_subdir = ticks_subdir
        self._file: IO[str] | None = None
        self._writer: csv.DictWriter | None = None
        self._current_market_id: str | None = None
        self._current_date: str | None = None
        self.current_path: Path | None = None

    def _ensure_file(self, market_id: str) -> csv.DictWriter:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._writer is None or self._current_market_id != market_id or self._current_date != date_str:
            self.close()
            subdir = self.base_dir / self.ticks_subdir / date_str
            subdir.mkdir(parents=True, exist_ok=True)
            path = subdir / f"{market_id}.csv"
            new_file = not path.exists() or path.stat().st_size == 0
            self._file = open(path, "a", newline="", encoding="utf-8")
            self._writer = csv.DictWriter(self._file, fieldnames=list(TICK_COLUMNS), extrasaction="ignore")
            if new_file:
                self._writer.writeheader()
            self._current_market_id = market_id
            self._current_date = date_str
            self.current_path = path
        return self._writer

    def write_tick(self, tick: dict[str, Any], market_id: str) -> None:
        """Write one row.  None becomes an empty cell."""
        writer = self._ensure_file(market_id)
        writer.writerow({k: tick.get(k) for k in TICK_COLUMNS})
        if self._file is not None:
            self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
        self._file = None
        self._writer = None
        self._current_market_id = None
        self._current_date = None
