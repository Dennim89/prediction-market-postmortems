"""The `validate` command."""

import json

from collector.main import main, validate_file

GOOD = {
    "ts_utc": "2026-01-01T00:00:00+00:00",
    "recv_ts_utc": "2026-01-01T00:00:00.100000+00:00",
    "source": "polymarket",
    "event_type": "orderbook_l1",
    "market_id": "fake-condition-0001",
    "market_slug": "btc-updown-15m-1767225600",
    "interval": "15m",
    "run_id": "test-run",
    "seq": 1,
    "payload": {"side": "yes"},
}


def _write(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_valid_file(tmp_path, capsys):
    path = tmp_path / "raw.jsonl"
    _write(path, [json.dumps(GOOD), "", json.dumps({**GOOD, "seq": 2})])
    assert main(["validate", str(path)]) == 0
    assert "OK: 2 events" in capsys.readouterr().out


def test_problems_are_reported_per_line(tmp_path):
    missing_payload = {k: v for k, v in GOOD.items() if k != "payload"}
    path = tmp_path / "raw.jsonl"
    _write(path, [json.dumps(missing_payload), "{not json", json.dumps({**GOOD, "event_type": "trades"}), "[1, 2]"])
    count, problems = validate_file(path)
    assert count == 4
    assert len(problems) == 4
    assert main(["validate", str(path)]) == 1


def test_empty_or_missing_file_fails(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert main(["validate", str(empty)]) == 1
    assert main(["validate", str(tmp_path / "missing.jsonl")]) == 1
