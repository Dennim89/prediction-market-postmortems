import os

import pandas as pd
import pytest
from ua_helpers import connect_with, market_rows

from updown_audit import db, synthetic


def test_synthetic_tables_are_reproducible_and_complete():
    a = synthetic.generate(hours=2, seed=5)
    b = synthetic.generate(hours=2, seed=5)
    for name in ("markets", "quotes", "candles"):
        pd.testing.assert_frame_equal(a[name], b[name])
    m = a["markets"]
    assert (m["tf"].value_counts().to_dict()) == {"5m": 24, "15m": 8}
    assert ((m["end_ts"] - m["start_ts"]) == m["tf"].map({"5m": "5min", "15m": "15min"}).map(pd.Timedelta)).all()
    assert set(m["winner"]) <= {"Up", "Down"}
    assert len(a["quotes"]) == 2 * 2 * 3600  # one row a second per timeframe
    assert a["candles"]["open_time"].diff().dropna().eq(pd.Timedelta(minutes=1)).all()


def test_quotes_are_in_cents_and_only_the_planted_rows_are_crossed():
    q = synthetic.generate(hours=3, seed=2, crossed_rows=4)["quotes"]
    for col in ("yes_bid", "yes_ask", "no_bid", "no_ask"):
        assert ((q[col] * 100).round(6) % 1 == 0).all()
    assert (q["yes_bid"] < q["yes_ask"]).all()
    assert ((q["yes_bid"] + q["no_bid"]) > 1 + 1e-9).sum() == 4
    assert ((q["yes_ask"] + q["no_ask"]) < 1 - 1e-9).sum() == 0


def test_load_frames_casts_and_checks_columns():
    con = connect_with(market_rows([("m1", "5m", 0, "Yes")]))
    assert db.check_schema(con) == []
    assert con.execute("SELECT typeof(start_ts) FROM markets").fetchone()[0] == "TIMESTAMP"
    with pytest.raises(ValueError, match="missing columns"):
        db.load_frames(con, markets=pd.DataFrame({"market_id": ["x"]}))
    with pytest.raises(ValueError, match="unknown table"):
        db.load_frames(con, trades=pd.DataFrame())


def test_check_schema_reports_missing_tables_and_bad_values():
    con = db.connect()
    assert "table markets is missing" in db.check_schema(con)
    con2 = connect_with(market_rows([("m1", "5m", 0, "Maybe")]))
    assert any("tf other than" in p for p in db.check_schema(con2))


def test_load_dotenv_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nUPDOWN_DB=./data/x.duckdb\nOTHER_SETTING='kept'\n", encoding="utf-8")
    monkeypatch.setenv("OTHER_SETTING", "from-environment")
    monkeypatch.setenv("UPDOWN_DB", "placeholder")  # so monkeypatch restores the original state
    monkeypatch.delenv("UPDOWN_DB")
    db.load_dotenv(env)
    assert os.environ["UPDOWN_DB"] == "./data/x.duckdb"
    assert os.environ["OTHER_SETTING"] == "from-environment"
