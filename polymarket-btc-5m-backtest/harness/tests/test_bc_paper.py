from pathlib import Path

import pytest

from backtest_checks import paper

SAMPLE = Path(__file__).parent / "fixtures" / "paper_sample.csv"  # synthetic, written by hand


def test_summary_of_the_synthetic_paper_log():
    s = paper.summarize(paper.read_paper_csv(SAMPLE))
    assert (s.resolved, s.open) == (8, 1)  # the repeated row counts once
    assert s.win_rate == pytest.approx(5 / 8)
    assert s.avg_price == pytest.approx(5.5 / 8)
    assert s.break_even == pytest.approx(s.avg_price)
    assert s.share_win_rate == pytest.approx(60 / 90)
    assert s.pnl_per_share_before_fees == pytest.approx((60 - 62.5) / 90)
    assert s.gap_to(0.85) == pytest.approx(22.5)


def test_fees_raise_the_break_even_win_rate():
    trades = paper.read_paper_csv(SAMPLE)
    assert paper.summarize(trades, fee_peak=0.018).break_even == pytest.approx(0.6875 + 0.12132 / 8)


def test_keeping_repeated_rows_counts_them_twice():
    s = paper.summarize(paper.read_paper_csv(SAMPLE), one_per_market=False)
    assert s.resolved == 9


def test_empty_and_bad_logs(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("ts,market_id,side,price,size,outcome\n", encoding="utf-8")
    assert paper.summarize(paper.read_paper_csv(empty)).resolved == 0
    bad = tmp_path / "bad.csv"
    bad.write_text("ts,market_id,side,price,size,outcome\nx,m,SIDEWAYS,0.5,1,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="side"):
        paper.read_paper_csv(bad)
