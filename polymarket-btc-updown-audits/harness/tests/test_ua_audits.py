import pandas as pd
import pytest
from ua_helpers import connect_with, market_rows, ts

from updown_audit import audits, db


def test_window_lengths_flag_a_start_taken_from_the_listing_time():
    m = market_rows([("a", "5m", 0, "Up"), ("b", "15m", 0, "Down"), ("c", "15m", 15, "Up")])
    m.loc[m["market_id"] == "c", "start_ts"] = m.loc[m["market_id"] == "c", "end_ts"] - pd.Timedelta(days=1)
    out = audits.window_lengths(connect_with(m)).set_index("tf")
    assert out.loc["15m", "wrong_length"] == 1 and out.loc["5m", "wrong_length"] == 0


def test_winner_balance_reads_yes_and_no_as_up_and_down():
    m = market_rows([("a", "5m", 0, "Yes"), ("b", "5m", 5, "No"), ("c", "5m", 10, "Up"), ("d", "5m", 15, "Up")])
    out = audits.winner_balance(connect_with(m))
    assert out.loc[0, "up_share"] == pytest.approx(0.75)


def test_book_sanity_finds_the_planted_crossed_rows(con24):
    out = audits.book_sanity(con24).set_index("tf")
    assert out["bids_over_1"].sum() == 3  # synthetic.generate plants 3 by default
    assert out["asks_under_1"].sum() == 0


def test_label_alignment_a_matches_best_and_misses_concentrate_on_small_moves(con24):
    for tf in ("5m", "15m"):
        agree = audits.label_agreement(con24, tf).set_index("alignment")["agree"]
        assert agree.idxmax() == "A"
        assert agree["A"] > 0.93
        assert agree["B"] < agree["A"] - 0.03
    by_move = audits.disagreement_by_move(con24, "5m")
    assert by_move["disagree"].iloc[0] > by_move["disagree"].iloc[-1]
    assert by_move["disagree"].iloc[-1] < 0.02
    assert by_move["markets"].sum() == 288


def test_tie_rule_decides_a_zero_move():
    m = market_rows([("a", "5m", 0, "Up")])
    candles = pd.DataFrame({"open_time": [ts(-1), ts(4)], "close": [100.0, 100.0]})
    con = connect_with(m, candles=candles)
    assert audits.label_agreement(con, "5m", tie="up").set_index("alignment").loc["A", "agree"] == 1.0
    assert audits.label_agreement(con, "5m", tie="down").set_index("alignment").loc["A", "agree"] == 0.0
    with pytest.raises(ValueError):
        audits.label_agreement(con, "5m", tie="sideways")
    with pytest.raises(ValueError):
        audits.label_agreement(con, "2m")


def test_same_end_agreement_on_hand_made_markets():
    m = market_rows([
        ("x1", "15m", 0, "Up"), ("x2", "15m", 15, "Down"),
        ("s1", "5m", 0, "Up"), ("s2", "5m", 5, "Down"), ("s3", "5m", 10, "Up"),
        ("s4", "5m", 15, "Down"), ("s5", "5m", 20, "Down"), ("s6", "5m", 25, "Up"),
    ])
    out = audits.same_end_agreement(connect_with(m))
    assert (out.loc[0, "pairs"], out.loc[0, "agree"]) == (2, 0.5)


def test_same_end_agreement_on_a_random_walk_is_far_from_one(con24):
    # Under a random walk the last 5 minutes and the whole 15 agree about 70% of the time.
    agree = audits.same_end_agreement(con24).loc[0, "agree"]
    assert 0.55 < agree < 0.85


def test_calibration_and_coverage(con24):
    cal = audits.calibration(con24, "15m")
    assert cal["markets"].sum() == 96
    assert cal["up_share"].iloc[-1] > 0.9 and cal["up_share"].iloc[0] < 0.1
    cov = audits.coverage(con24).set_index("tf")
    assert cov.loc["5m", "markets"] == 288 and cov.loc["15m", "markets_without_quotes"] == 0


def test_coverage_counts_markets_without_quotes_and_daily_density():
    m = market_rows([("a", "5m", 0, "Up"), ("b", "5m", 5, "Down")])
    q = pd.DataFrame({"market_id": ["a", "a"], "ts": [ts(0, 1), ts(0, 2)],
                      "yes_bid": [0.4, 0.4], "yes_ask": [0.42, 0.42], "no_bid": [0.58, 0.58], "no_ask": [0.6, 0.6]})
    con = connect_with(m, quotes=q)
    assert audits.coverage(con).loc[0, "markets_without_quotes"] == 1
    dens = audits.daily_density(con, "5m")
    assert dens.loc[0, "day"] == "2026-01-05" and dens.loc[0, "rows"] == 2 and dens.loc[0, "of_median"] == 1.0
    assert db.TF_MINUTES["1h"] == 60
