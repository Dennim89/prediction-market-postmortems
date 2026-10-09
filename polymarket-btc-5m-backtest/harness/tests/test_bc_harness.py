import math

import pytest
from bc_helpers import T0, flat_market, market, tick

from backtest_checks.harness import bootstrap, break_even_win_rate, by_day, run
from backtest_checks.model import NO, YES, Trade


def buy(side, i=290, size=10):
    def strategy(m, params):
        return [Trade(t=m.start + i, side=side, price=0.0, size=size)]  # price is what it saw
    return strategy


def test_a_winning_and_a_losing_trade_settle_at_the_ask():
    m = flat_market(outcome=YES, ya=0.60, na=0.42)
    win = run(buy(YES), [m])
    assert (win.trades, win.wins, win.shares) == (1, 1, 10)
    assert win.pnl == pytest.approx((1 - 0.60) * 10)
    lose = run(buy(NO), [m])
    assert lose.pnl == pytest.approx(-0.42 * 10)
    assert lose.win_rate == 0


def test_pnl_per_share_is_share_win_rate_minus_price_paid():
    markets = [flat_market(outcome=YES, mid="a", ya=0.7), flat_market(outcome=NO, mid="b", ya=0.6, start=T0 + 300)]
    r = run(buy(YES, size=10), markets)
    assert r.avg_price == pytest.approx(0.65)
    assert r.share_win_rate == pytest.approx(0.5)
    assert r.pnl_per_share == pytest.approx(r.share_win_rate - r.avg_price)


def test_no_trades_gives_an_empty_result():
    r = run(lambda m, p: [], [flat_market()])
    assert r.trades == 0 and r.pnl == 0
    assert math.isnan(r.win_rate)


def test_markets_without_a_venue_outcome_are_counted_as_proxy_labels():
    m = market([tick(i, spot=101.0) for i in range(300)], outcome=None)
    r = run(buy(YES), [m])
    assert r.proxy_markets == 1 and r.wins == 1


def test_bootstrap_is_reproducible_and_resamples_markets():
    markets = [flat_market(outcome=YES if k % 3 else NO, mid=f"m{k}", start=T0 + 300 * k) for k in range(30)]
    a = bootstrap(buy(YES), markets, seeds=[1, 2, 3])
    b = bootstrap(buy(YES), markets, seeds=[1, 2, 3])
    assert a == b
    assert len({r.wins for r in a}) > 1  # different resamples, different results
    assert all(r.trades == 30 for r in a)


def test_by_day_groups_by_utc_date_in_order():
    late = flat_market(mid="late", start=T0 + 86_400 + 600)
    early = flat_market(mid="early", start=T0)
    groups = by_day([late, early])
    assert list(groups) == ["2026-01-01", "2026-01-02"]
    assert groups["2026-01-02"][0].market_id == "late"


def test_break_even_win_rate_is_the_average_price_plus_fees():
    assert break_even_win_rate([0.7, 0.6], [1, 1]) == pytest.approx(0.65)
    assert break_even_win_rate([0.7, 0.6], [3, 1]) == pytest.approx(0.675)
    assert break_even_win_rate([0.5], [1], fee_peak=0.02) == pytest.approx(0.52)
