import pytest
from bc_helpers import T0, flat_market, market, tick

from backtest_checks import controls, synthetic
from backtest_checks.harness import by_day, run
from backtest_checks.model import NO, YES, Trade
from backtest_checks.strategies import best_tick_in_hindsight, naive


@pytest.fixture(scope="module")
def two_days():
    return synthetic.generate(markets_per_day=36, seed=3)


def test_do_nothing_gives_exactly_zero(two_days):
    r = run(controls.do_nothing, two_days)
    assert (r.trades, r.pnl) == (0, 0)


def test_random_side_is_reproducible_and_independent_of_order(two_days):
    strat = controls.random_side(seed=5)
    forward = {m.market_id: strat(m, {})[0].side for m in two_days}
    backward = {m.market_id: strat(m, {})[0].side for m in reversed(two_days)}
    assert forward == backward
    assert set(forward.values()) == {YES, NO}
    other = controls.random_side(seed=6)
    assert any(other(m, {})[0].side != forward[m.market_id] for m in two_days)


def test_cheaper_side_buys_the_lower_ask_in_the_window():
    m = flat_market(n=300, ya=0.30, na=0.72)
    (trade,) = controls.cheaper_side(m, {"window_sec": 10})
    assert (trade.side, trade.price, trade.t) == (YES, 0.30, T0 + 290)


def test_inverted_buys_the_other_side_at_the_same_tick():
    m = flat_market(n=300, ya=0.61, na=0.41)

    def strategy(mk, p):
        return [Trade(t=T0 + 295, side=YES, price=0.61, size=7)]

    (trade,) = controls.inverted(strategy)(m, {})
    assert (trade.t, trade.side, trade.price, trade.size) == (T0 + 295, NO, 0.41, 7)


def test_controls_lose_where_the_strategy_has_a_real_edge(two_days):
    day1 = list(by_day(two_days).values())[0]  # quotes lag the reference price on day 1
    edge = run(naive, day1).pnl_per_share
    assert edge > 0.05
    assert run(controls.inverted(naive), day1).pnl_per_share < 0
    assert run(controls.random_side(seed=1), two_days).pnl_per_share < edge
    assert run(controls.cheaper_side, two_days).pnl_per_share < edge


def test_future_leak_passes_a_causal_strategy(two_days):
    report = controls.future_leak(naive, two_days[:20])
    assert report.ok and report.markets_checked == 20 and report.checkpoints > 20 * 30


def test_future_leak_flags_the_best_tick_chosen_in_hindsight(two_days):
    report = controls.future_leak(best_tick_in_hindsight, two_days)
    assert not report.ok
    assert 0 < len(report.leaking) <= len(two_days)


def test_future_leak_flags_a_strategy_that_reads_the_outcome_or_the_last_tick():
    markets = [flat_market(outcome=YES, mid="a"), flat_market(outcome=NO, mid="b", start=T0 + 300)]

    def reads_outcome(m, p):
        return [Trade(t=m.ticks[0].t, side=m.outcome or YES, price=0.5, size=1)]

    def reads_last_tick(m, p):
        side = YES if m.ticks[-1].spot >= m.start_price else NO
        return [Trade(t=m.ticks[0].t, side=side, price=0.5, size=1)]

    assert controls.future_leak(reads_outcome, markets).leaking == ["b"]
    peeking = market([tick(i, spot=100.0 if i < 299 else 99.0) for i in range(300)])
    assert not controls.future_leak(reads_last_tick, [peeking]).ok


def test_hindsight_tick_choice_beats_the_causal_rule_on_the_same_data(two_days):
    assert run(best_tick_in_hindsight, two_days).pnl_per_share > run(naive, two_days).pnl_per_share
