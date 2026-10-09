from pathlib import Path

from backtest_checks.__main__ import main

SAMPLE = Path(__file__).parent / "fixtures" / "paper_sample.csv"


def test_demo_prints_every_section(capsys):
    assert main(["demo", "--markets-per-day", "8", "--seeds", "2"]) == 0
    out = capsys.readouterr().out
    for heading in ("Data", "1. Controls", "2. Split by day", "3. Friction", "4. Lookahead"):
        assert heading in out
    assert "2026-01-01" in out and "2026-01-02" in out
    assert "best tick in hindsight" in out


def test_synth_then_run_on_the_csv(tmp_path, capsys):
    path = tmp_path / "ticks.csv"
    assert main(["synth", "--out", str(path), "--markets-per-day", "3"]) == 0
    assert "1,800 ticks of 6 synthetic markets" in capsys.readouterr().out
    assert main(["run", "--ticks", str(path), "--seeds", "2"]) == 0
    assert "6 markets over 2 day(s)" in capsys.readouterr().out


def test_paper_summary(capsys):
    assert main(["paper", "--log", str(SAMPLE), "--backtest-win-rate", "0.85"]) == 0
    out = capsys.readouterr().out
    assert "resolved trades: 8 (open: 1)" in out
    assert "won: 62.5%" in out
    assert "+22.5 points" in out
