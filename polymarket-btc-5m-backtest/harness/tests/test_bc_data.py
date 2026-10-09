import pytest

from backtest_checks import csvio, synthetic
from backtest_checks.model import NO, YES


def test_synthetic_markets_are_reproducible_and_well_formed():
    a = synthetic.generate(markets_per_day=4, seed=11)
    b = synthetic.generate(markets_per_day=4, seed=11)
    assert [m.ticks for m in a] == [m.ticks for m in b]
    assert [m.outcome for m in a] == [m.outcome for m in b]
    assert len(a) == 8 and all(len(m.ticks) == 300 for m in a)
    assert [m.day for m in a] == ["2026-01-01"] * 4 + ["2026-01-02"] * 4
    for m in a:
        assert m.end - m.start == 300 and m.outcome in (YES, NO)
        for tk in m.ticks:
            assert 0 < tk.yes_bid < tk.yes_ask < 1
            assert tk.yes_bid + tk.no_bid <= 1 <= tk.yes_ask + tk.no_ask


def test_a_different_seed_gives_different_data():
    a = synthetic.generate(markets_per_day=2, seed=1)
    b = synthetic.generate(markets_per_day=2, seed=2)
    assert [m.start_price for m in a] != [m.start_price for m in b]


def test_csv_round_trip(tmp_path):
    markets = synthetic.generate(markets_per_day=2, seed=4)
    path = tmp_path / "ticks.csv"
    assert csvio.write_ticks_csv(markets, path) == 4 * 300
    back = csvio.read_ticks_csv(path)
    assert [m.market_id for m in back] == [m.market_id for m in markets]
    assert [m.outcome for m in back] == [m.outcome for m in markets]
    assert back[0].ticks == markets[0].ticks
    assert back[-1].start_price == markets[-1].start_price


HEADER = ",".join(csvio.COLUMNS)


def test_csv_accepts_unix_and_iso_times_and_empty_cells(tmp_path):
    path = tmp_path / "t.csv"
    path.write_text(
        HEADER + "\n"
        "w1,1767225600,2026-01-01T00:05:00Z,100.0,UP,2026-01-01T00:04:59,100.5,,0.6,0.62,0.38,0.4,,\n"
        "w1,1767225600,2026-01-01T00:05:00Z,100.0,UP,1767225898,100.4,0.001,,,,,,\n",
        encoding="utf-8",
    )
    (m,) = csvio.read_ticks_csv(path)
    assert m.outcome == YES and m.end - m.start == 300
    first, second = m.ticks  # sorted by time
    assert first.t == 1767225898 and first.yes_ask is None and first.sigma == 0.001
    assert second.yes_ask == 0.62 and second.sigma == 0.0 and second.yes_ask_size is None


def test_csv_errors_name_the_problem(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("market_id,t\nw1,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        csvio.read_ticks_csv(bad)
    mixed = tmp_path / "mixed.csv"
    mixed.write_text(
        HEADER + "\n"
        "w1,0,300,100.0,YES,1,100,,,,,,,\n"
        "w1,0,300,101.0,YES,2,100,,,,,,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="differ"):
        csvio.read_ticks_csv(mixed)
    outcome = tmp_path / "outcome.csv"
    outcome.write_text(HEADER + "\nw1,0,300,100.0,MAYBE,1,100,,,,,,,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outcome"):
        csvio.read_ticks_csv(outcome)
