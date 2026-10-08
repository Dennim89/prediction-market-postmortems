"""Whole runs with the synthetic providers: no network, a few seconds each."""

import asyncio
import csv
import json

import httpx
import pytest

from collector.config import CollectorConfig
from collector.main import main
from collector.pipeline import scheduler
from collector.pipeline.scheduler import CollectorFailed, run_collector
from collector.providers.mock import MockPolymarketProvider, MockSpotFeedProvider
from collector.schema import TICK_COLUMNS


def fast_mock_config(out_dir) -> CollectorConfig:
    return CollectorConfig.model_validate(
        {
            "market_provider": "mock",
            "spot_provider": "mock",
            "output": {"dir": str(out_dir)},
            "intervals": {
                "tick_interval_sec": 0.2,
                "orderbook_poll_sec": 0.1,
                "spot_poll_sec": 0.1,
                "market_discovery_sec": 0.5,
            },
            "log_level": "WARNING",
        }
    )


def raw_events(out_dir):
    files = sorted((out_dir / "raw").glob("*/*.jsonl"))
    return files, [json.loads(line) for f in files for line in f.read_text(encoding="utf-8").splitlines()]


def tick_rows(files):
    rows = []
    for f in files:
        with f.open(encoding="utf-8", newline="") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def test_offline_run_writes_raw_events_and_ticks(tmp_path):
    asyncio.run(run_collector(cfg=fast_mock_config(tmp_path), duration_sec=1.5, handle_signals=False))

    files, events = raw_events(tmp_path)
    types = {e["event_type"] for e in events}
    assert {"market_open_detected", "market_snapshot", "orderbook_l1", "orderbook_l2", "btc_spot"} <= types
    snapshot = next(e for e in events if e["event_type"] == "market_snapshot")
    assert snapshot["payload"]["btc_open_price"] is not None  # the synthetic window starts with the run
    for f in files:
        assert main(["validate", str(f)]) == 0

    tick_files = sorted((tmp_path / "ticks").glob("*/*.csv"))
    assert tick_files
    with tick_files[0].open(encoding="utf-8", newline="") as fh:
        assert next(csv.reader(fh)) == list(TICK_COLUMNS)
    rows = tick_rows(tick_files)
    assert len(rows) >= 2
    last = rows[-1]
    assert float(last["yes_bid"]) < float(last["yes_ask"])
    assert abs(float(last["yes_mid"]) + float(last["no_mid"]) - 1.0) < 1e-9
    assert last["btc_open_price"] != ""
    assert float(last["yes_book_age_sec"]) >= 0


class _OfflineOutage(MockPolymarketProvider):
    async def find_current_15m_market(self, now=None):
        raise httpx.ConnectError("synthetic outage")


def test_network_errors_are_recorded_and_retried(tmp_path):
    providers = (_OfflineOutage(), MockSpotFeedProvider())
    asyncio.run(
        run_collector(cfg=fast_mock_config(tmp_path), duration_sec=1.2, handle_signals=False, providers=providers)
    )
    _, events = raw_events(tmp_path)
    errors = [e for e in events if e["event_type"] == "errors"]
    assert len(errors) >= 2  # retried, not given up
    assert errors[0]["payload"]["phase"] == "market_discovery"
    assert not (tmp_path / "ticks").exists()  # no market, no ticks


class _NoWindow(MockPolymarketProvider):
    async def find_current_15m_market(self, now=None):
        return None


def test_finding_no_window_is_reported_not_silent(tmp_path):
    providers = (_NoWindow(), MockSpotFeedProvider())
    asyncio.run(
        run_collector(cfg=fast_mock_config(tmp_path), duration_sec=1.2, handle_signals=False, providers=providers)
    )
    _, events = raw_events(tmp_path)
    errors = [e for e in events if e["event_type"] == "errors"]
    assert len(errors) == 1  # reported once, then at most once a minute
    assert "no current 15-minute BTC window" in errors[0]["payload"]["error"]


def test_a_crashing_loop_stops_the_run(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(scheduler, "build_tick", broken)
    with pytest.raises(CollectorFailed, match="ticks"):
        asyncio.run(run_collector(cfg=fast_mock_config(tmp_path), duration_sec=30, handle_signals=False))


def test_cli_rejects_a_duration_that_is_not_positive():
    with pytest.raises(SystemExit) as exc:
        main(["run", "--mock", "--duration-sec", "0"])
    assert exc.value.code == 2


def test_cli_mock_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("TICK_INTERVAL_SEC", "0.2")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    assert main(["run", "--mock", "--duration-sec", "1"]) == 0
    assert list((tmp_path / "out" / "ticks").glob("*/*.csv"))
