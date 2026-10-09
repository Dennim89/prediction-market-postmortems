import math

import pytest
from bc_helpers import T0, flat_market, market, tick

from backtest_checks.fair import fair_p_up
from backtest_checks.model import NO, YES, Trade, proxy_outcome


def test_fair_value_is_one_half_at_the_start_price_and_rises_with_the_price():
    assert fair_p_up(100.0, 100.0, 0.001, 60) == pytest.approx(0.5)
    assert fair_p_up(100.1, 100.0, 0.001, 60) > fair_p_up(100.05, 100.0, 0.001, 60) > 0.5
    assert fair_p_up(99.9, 100.0, 0.001, 60) < 0.5


def test_fair_value_sharpens_as_time_runs_out():
    assert fair_p_up(100.05, 100.0, 0.001, 5) > fair_p_up(100.05, 100.0, 0.001, 200)


def test_fair_value_at_the_end_and_without_sigma():
    assert fair_p_up(100.0, 100.0, 0.001, 0) == 1.0  # a tie resolves YES
    assert fair_p_up(99.0, 100.0, 0.001, -1) == 0.0
    assert fair_p_up(101.0, 100.0, 0.0, 30) == 0.5


def test_fair_value_matches_the_normal_cdf():
    z = math.log(100.2 / 100.0) / (0.001 * math.sqrt(16))
    assert fair_p_up(100.2, 100.0, 0.001, 16) == pytest.approx(0.5 * (1 + math.erf(z / math.sqrt(2))))


def test_proxy_outcome_tie_rules():
    m = market([tick(0, spot=101.0), tick(1, spot=100.0)], outcome=None)
    assert proxy_outcome(m, "ge") == YES
    assert proxy_outcome(m, "gt") == NO
    assert proxy_outcome(m, "ge", noise=-0.01) == NO
    with pytest.raises(ValueError):
        proxy_outcome(m, "lt")


def test_index_at_never_returns_a_later_tick():
    m = flat_market(n=5)
    assert m.index_at(T0 - 1) is None
    assert m.index_at(T0) == 0
    assert m.index_at(T0 + 2.5) == 2
    assert m.index_at(T0 + 100) == 4


def test_truncated_copy_hides_the_future_and_the_outcome():
    m = flat_market(n=10, outcome=NO)
    cut = m.truncated(T0 + 3)
    assert [tk.t for tk in cut.ticks] == [T0, T0 + 1, T0 + 2, T0 + 3]
    assert cut.outcome is None
    assert (cut.start, cut.end, cut.start_price) == (m.start, m.end, m.start_price)
    assert len(m.ticks) == 10


def test_market_day_is_the_utc_date_of_the_start():
    assert flat_market(n=1).day == "2026-01-01"


def test_bad_values_are_rejected():
    with pytest.raises(ValueError):
        Trade(t=T0, side="UP", price=0.5, size=1)
    with pytest.raises(ValueError):
        Trade(t=T0, side=YES, price=0.5, size=0)
    with pytest.raises(ValueError):
        market([tick(0)], outcome="MAYBE")
