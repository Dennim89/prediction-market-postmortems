"""Tick CSV writer."""

import csv

from collector.schema import TICK_COLUMNS
from collector.storage.csv_writer import CSVWriter


def _rows(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def test_header_once_missing_values_empty_and_extra_keys_dropped(tmp_path):
    w = CSVWriter(tmp_path)
    w.write_tick({"ts_utc": "t1", "market_id": "m1", "yes_bid": 0.48, "zscore_10m": None, "extra": "x"}, "m1")
    path = w.current_path
    w.close()
    w2 = CSVWriter(tmp_path)  # a second run appends to the same file
    w2.write_tick({"ts_utc": "t2", "market_id": "m1"}, "m1")
    w2.close()

    rows = _rows(path)
    assert path.parent.parent == tmp_path / "ticks"
    assert rows[0] == list(TICK_COLUMNS)
    assert len(rows) == 3
    first = dict(zip(rows[0], rows[1]))
    assert first["yes_bid"] == "0.48"
    assert first["zscore_10m"] == ""
    assert "extra" not in first


def test_each_market_gets_its_own_file(tmp_path):
    w = CSVWriter(tmp_path)
    w.write_tick({"ts_utc": "t1"}, "m1")
    first = w.current_path
    w.write_tick({"ts_utc": "t2"}, "m2")
    second = w.current_path
    w.close()
    assert (first.name, second.name) == ("m1.csv", "m2.csv")
    assert len(_rows(first)) == len(_rows(second)) == 2
