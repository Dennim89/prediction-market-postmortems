import random

import pytest
from bc_helpers import T0, flat_market, market, tick

from backtest_checks.friction import FRICTIONLESS, SCENARIOS, Friction, fee_per_share, fill, settle
from backtest_checks.harness import run
from backtest_checks.model import NO, YES, Trade


def test_fee_peaks_at_one_half_and_vanishes_at_the_ends():
    assert fee_per_share(0.5, 0.018) == pytest.approx(0.018)
    assert fee_per_share(0.0, 0.018) == 0 and fee_per_share(1.0, 0.018) == 0
    assert fee_per_share(0.9, 0.018) == pytest.approx(0.018 * 4 * 0.9 * 0.1)
    assert fee_per_share(0.3, 0.018) == pytest.approx(fee_per_share(0.7, 0.018))


def test_frictionless_fill_is_the_ask_at_the_signal_tick():
    m = market([tick(0, ya=0.40), tick(1, ya=0.45), tick(2, ya=0.50)])
    f = fill(m, Trade(t=T0 + 1, side=YES, price=0.0, size=10))
    assert (f.t, f.price, f.size) == (T0 + 1, 0.45, 10)


def test_a_trade_between_ticks_uses_the_earlier_tick_and_latency_moves_it_later():
    m = market([tick(0, ya=0.40), tick(1, ya=0.45), tick(2, ya=0.50)])
    assert fill(m, Trade(t=T0 + 1.5, side=YES, price=0.0, size=1)).price == 0.45
    late = fill(m, Trade(t=T0, side=YES, price=0.0, size=1), Friction(latency_ticks=1))
    assert (late.t, late.price) == (T0 + 1, 0.45)
    last = fill(m, Trade(t=T0, side=YES, price=0.0, size=1), Friction(latency_ticks=10))
    assert last.t == T0 + 2  # never past the last tick


def test_slippage_and_fee_are_added_per_share():
    m = market([tick(0, na=0.50)])
    f = fill(m, Trade(t=T0, side=NO, price=0.0, size=4), Friction(slippage=0.01, fee_peak=0.02))
    assert f.price == pytest.approx(0.50 + 0.01 + 0.02)


def test_depth_cap_limits_size_and_unknown_depth_cannot_fill():
    m = market([tick(0, ys=25.0), tick(1, ys=None)])
    capped = fill(m, Trade(t=T0, side=YES, price=0.0, size=100), Friction(depth_cap=0.3))
    assert capped.size == 7  # floor(25 * 0.3)
    assert fill(m, Trade(t=T0 + 1, side=YES, price=0.0, size=100), Friction(depth_cap=0.3)) is None
    assert fill(m, Trade(t=T0 + 1, side=YES, price=0.0, size=100)).size == 100  # no cap


def test_missing_ask_or_early_trade_cannot_fill():
    m = market([tick(0, ya=None)])
    assert fill(m, Trade(t=T0, side=YES, price=0.0, size=1)) is None
    assert fill(m, Trade(t=T0 - 5, side=NO, price=0.0, size=1)) is None


def test_settle_prefers_the_venue_outcome():
    m = market([tick(0, spot=200.0)], outcome=NO)
    assert settle(m, Friction(oracle_noise=50.0), random.Random(0)) == (NO, "venue")


def test_proxy_settlement_noise_is_reproducible_and_can_flip_close_calls():
    m = market([tick(0, spot=100.01)], outcome=None)
    assert settle(m, FRICTIONLESS, random.Random(0)) == (YES, "proxy")
    flips = {settle(m, Friction(oracle_noise=1.0), random.Random(s))[0] for s in range(20)}
    assert flips == {YES, NO}
    assert settle(m, Friction(oracle_noise=1.0), random.Random(3)) == settle(m, Friction(oracle_noise=1.0), random.Random(3))


def test_friction_lowers_the_result_of_the_same_trades():
    markets = [flat_market(outcome=YES, mid=f"m{k}", start=T0 + 300 * k, ya=0.55) for k in range(5)]

    def strategy(m, p):
        return [Trade(t=m.start + 295, side=YES, price=0.55, size=10)]

    clean = run(strategy, markets).pnl_per_share
    costly = run(strategy, markets, friction=SCENARIOS["realistic"]).pnl_per_share
    assert clean == pytest.approx(0.45)
    assert costly < clean


def test_bad_friction_values_are_rejected():
    for kwargs in ({"slippage": -0.01}, {"depth_cap": 0}, {"depth_cap": 1.5}, {"latency_ticks": -1},
                   {"tie_rule": "lt"}, {"fee_peak": -1}):
        with pytest.raises(ValueError):
            Friction(**kwargs)
