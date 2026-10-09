import pandas as pd
import pytest
from ua_helpers import connect_with, market_rows, ts

from updown_audit import checks, signals


def _quote(mid, t, yb, ya):
    return {"market_id": mid, "ts": t, "yes_bid": yb, "yes_ask": ya, "no_bid": round(1 - ya, 2),
            "no_ask": round(1 - yb, 2)}


@pytest.fixture
def tiny():
    m = market_rows([("w15", "15m", 0, "Up"), ("w5", "5m", 0, "Up")])
    q = pd.DataFrame([
        _quote("w5", ts(4, 50), 0.95, 0.97),
        _quote("w5", ts(4, 58), 0.10, 0.12),  # after the entry: must not be used
        _quote("w15", ts(4, 40), 0.80, 0.82),
        _quote("w15", ts(4, 57), 0.50, 0.52),  # after the entry
        _quote("w15", ts(9, 0), 0.60, 0.62),
        _quote("w15", ts(14, 0), 0.97, 0.99),
    ])
    return connect_with(m, quotes=q)


def test_candidates_use_the_last_quotes_at_or_before_entry(tiny):
    (row,) = signals.pin_candidates(tiny).to_dict("records")
    assert row["slot"] == 1 and row["entry_ts"] == ts(4, 55)
    assert row["m5_close"] == pytest.approx(0.96) and row["m5_close_ts"] == ts(4, 50)
    assert (row["yes_ask15"], row["no_ask15"]) == (0.82, 0.20)
    assert row["entry_quote_age_sec"] == 15
    assert row["spread_at_entry"] == pytest.approx(0.02)
    assert row["min_yes_bid_after"] == 0.50 and row["lifetime_spread"] == pytest.approx(0.02)


def test_pin_trades_pick_side_price_and_outcome(tiny):
    (t,) = signals.pin_trades(signals.pin_candidates(tiny), threshold=0.9).to_dict("records")
    assert (t["side"], t["entry_price"], t["won"], t["min_bid_after"]) == ("Up", 0.82, True, 0.50)
    assert t["market_id"] == t["scored_market_id"] == "w15"
    assert signals.pin_trades(signals.pin_candidates(tiny), threshold=0.97).empty
    with pytest.raises(ValueError):
        signals.pin_trades(signals.pin_candidates(tiny), threshold=0.4)


def test_three_slots_per_window_and_entries_never_use_later_quotes(con24):
    c = signals.pin_candidates(con24)
    assert all(tuple(sorted(slots)) == (1, 2, 3) for _, slots in c.groupby("m15_id")["slot"])
    assert (c["entry_ts"] == c["end5"] - pd.Timedelta(seconds=5)).all()
    assert (c["m5_close_ts"] <= c["entry_ts"]).all() and (c["entry_quote_ts"] <= c["entry_ts"]).all()
    assert (c["entry_quote_age_sec"] >= 0).all()


def test_lookahead_check_flags_the_late_inputs_only(con24):
    pins = signals.pin_trades(signals.pin_candidates(con24), threshold=0.9)
    out = checks.lookahead(pins, {"m5_close": "m5_close_ts", "spread_at_entry": "entry_quote_ts",
                                  "lifetime_spread": "end15", "m5_vote": "m5_vote_ts"}).set_index("input")
    assert out.loc["m5_close", "known_after_entry"] == 0
    assert out.loc["spread_at_entry", "known_after_entry"] == 0
    assert out.loc["lifetime_spread", "share_late"] == 1.0
    late_votes = out.loc["m5_vote", "known_after_entry"]
    assert late_votes == (pins["slot"] < 3).sum()


def test_late_inputs_inflate_the_hit_rate_against_the_price(con24):
    c = signals.pin_candidates(con24)
    pins = signals.pin_trades(c, threshold=0.9)
    edge = lambda t: t["won"].mean() - t["entry_price"].mean()  # noqa: E731
    lifetime = pins[pins["lifetime_spread"] <= pins["lifetime_spread"].quantile(0.1)]
    assert edge(lifetime) > edge(pins) + 0.02
    assert edge(signals.vote_trades(c)) > 0.15
    assert abs(edge(pins)) < 0.03  # fair quotes: no edge


def test_duplicate_keys_catch_a_join_that_multiplies_rows(con24, frames24):
    pins = signals.pin_trades(signals.pin_candidates(con24), threshold=0.9)
    assert checks.duplicate_keys(pins, ["m15_id", "slot"]).empty
    m = frames24["markets"]
    # Joining on the end time alone also matches the 5-minute market that ends with the window.
    bad = pins.merge(m[["end_ts", "winner"]], left_on="end15", right_on="end_ts", how="left")
    dups = checks.duplicate_keys(bad, ["m15_id", "slot"])
    assert len(bad) == 2 * len(pins) and (dups["rows"] == 2).all()


def test_wrong_market_flags_a_leg_scored_on_another_market():
    t = pd.DataFrame({"market_id": ["a", "b"], "scored_market_id": ["a", "c"]})
    assert checks.wrong_market(t)["market_id"].tolist() == ["b"]


def test_lookahead_counts_unknown_times_separately():
    t = pd.DataFrame({"entry_ts": [ts(1), ts(2)], "x": [1, 2], "x_ts": [ts(0), None]})
    row = checks.lookahead(t, {"x": "x_ts"}).iloc[0]
    assert (row["known_after_entry"], row["unknown_time"]) == (0, 1)
