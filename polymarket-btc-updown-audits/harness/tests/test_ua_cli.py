import pytest

from updown_audit.__main__ import main


def test_demo_prints_every_section(capsys):
    assert main(["demo", "--hours", "6"]) == 0
    out = capsys.readouterr().out
    for heading in ("1. Data audits", "2. Lookahead check", "3. What late inputs do",
                    "4. Fees and the time split", "5. Sizing fitted in-sample"):
        assert heading in out
    assert "lifetime_spread" in out and "100.0%" in out


def test_synth_then_audit_a_database_file(tmp_path, capsys):
    path = tmp_path / "updown.duckdb"
    assert main(["synth", "--out", str(path), "--hours", "2"]) == 0
    assert "32 markets, 14,400 quote rows" in capsys.readouterr().out
    assert main(["audit", "--db", str(path)]) == 0
    out = capsys.readouterr().out
    assert "Labels from 1-minute candles" in out and "Window lengths" in out


def test_audit_takes_the_database_from_a_dotenv_file(tmp_path, capsys, monkeypatch):
    path = tmp_path / "x.duckdb"
    main(["synth", "--out", str(path), "--hours", "1"])
    capsys.readouterr()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UPDOWN_DB", "placeholder")  # so monkeypatch restores the original state
    monkeypatch.delenv("UPDOWN_DB")
    (tmp_path / ".env").write_text("UPDOWN_DB=x.duckdb\n", encoding="utf-8")
    assert main(["audit"]) == 0
    assert "Coverage" in capsys.readouterr().out


def test_audit_reports_missing_inputs(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UPDOWN_DB", "placeholder")
    monkeypatch.delenv("UPDOWN_DB")
    with pytest.raises(SystemExit):
        main(["audit"])
    with pytest.raises(SystemExit):
        main(["audit", "--db", str(tmp_path / "missing.duckdb")])
    import duckdb
    empty = tmp_path / "empty.duckdb"
    duckdb.connect(str(empty)).close()
    assert main(["audit", "--db", str(empty)]) == 1
    assert "table markets is missing" in capsys.readouterr().err
