"""Raw event writer."""

import json
from datetime import timedelta

import pytest

from collector.schema import RAW_FIELDS
from collector.storage.jsonl_writer import JSONLWriter
from collector.utils.time import parse_iso_utc
from tests.helpers import START


def test_writes_one_complete_event_per_line(tmp_path):
    w = JSONLWriter(base_dir=tmp_path, run_id="test-run-123")
    w.write(event_type="heartbeat", market_id="m1", market_slug="btc-updown-15m-1767225600", payload={"x": 1})
    w.write(event_type="btc_spot", market_id="m1", market_slug="btc-updown-15m-1767225600", payload={"price": 1.0})
    path = w.current_path
    w.close()

    assert path.parent.parent == tmp_path / "raw"
    assert path.name == "m1.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [e["seq"] for e in events] == [1, 2]
    for e in events:
        assert set(RAW_FIELDS) <= set(e)
        assert e["run_id"] == "test-run-123"
        assert e["interval"] == "15m"


def test_exchange_time_and_receive_time_are_both_kept(tmp_path):
    w = JSONLWriter(base_dir=tmp_path, run_id="test-run")
    received = START + timedelta(seconds=2)
    w.write("orderbook_l1", "m1", "slug", {"side": "yes"}, ts_utc=START, recv_ts_utc=received)
    path = w.current_path
    w.close()
    event = json.loads(path.read_text(encoding="utf-8"))
    assert parse_iso_utc(event["recv_ts_utc"]) - parse_iso_utc(event["ts_utc"]) == timedelta(seconds=2)


def test_events_without_a_market_go_to_a_named_file(tmp_path):
    w = JSONLWriter(base_dir=tmp_path, run_id="test-run")
    w.write("errors", "", "", {"error": "synthetic"}, source="collector")
    assert w.current_path.name == "_no_market.jsonl"
    w.close()


def test_unknown_event_type_is_rejected(tmp_path):
    w = JSONLWriter(base_dir=tmp_path, run_id="test-run")
    with pytest.raises(ValueError):
        w.write("trades", "m1", "slug", {})
    w.close()
