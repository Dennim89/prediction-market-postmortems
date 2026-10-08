"""Collector state: window times, book imbalance, price history, z-score."""

from datetime import timedelta

from collector.pipeline.state import CollectorState
from collector.providers.base import OrderbookL2, OrderbookLevel, SpotPrice
from tests.helpers import START, make_market


def test_times_relative_to_the_window():
    state = CollectorState()
    assert state.t_since_open_sec() is None
    assert state.t_left_sec() is None
    state.set_market(make_market())
    now = START + timedelta(minutes=5)
    assert state.t_since_open_sec(now) == 300
    assert state.t_left_sec(now) == 600
    assert state.t_left_sec(START + timedelta(minutes=20)) == 0


def test_set_market_forgets_the_old_window():
    state = CollectorState(btc_open_price=100_000.0, open_price_decided=True)
    state.yes_l2 = OrderbookL2("fake-a", "yes", [], [], START)
    state.set_market(make_market())
    assert state.btc_open_price is None
    assert not state.open_price_decided
    assert state.yes_l2 is None


def test_book_imbalance_uses_top_levels():
    state = CollectorState()
    assert state.book_imbalance_yes() is None
    bids = [OrderbookLevel(0.48, 30), OrderbookLevel(0.47, 10)]
    asks = [OrderbookLevel(0.52, 10)]
    state.yes_l2 = OrderbookL2("fake-a", "yes", bids, asks, START)
    assert state.book_imbalance_yes() == (40 - 10) / 50
    assert state.book_imbalance_yes(top_n=1) == (30 - 10) / 40


def test_spot_history_skips_repeats_and_is_capped():
    state = CollectorState(max_spot_history=3)
    assert state.add_spot_to_history(START, 1.0)
    assert not state.add_spot_to_history(START, 1.0)
    for i in range(1, 5):
        state.add_spot_to_history(START + timedelta(seconds=i), float(i))
    assert [p for _, p in state.spot_history] == [2.0, 3.0, 4.0]


def test_first_spot_at_or_after():
    state = CollectorState()
    for sec, price in ((-2, 99.0), (1, 101.0), (3, 103.0)):
        state.add_spot_to_history(START + timedelta(seconds=sec), price)
    assert state.first_spot_at_or_after(START) == (START + timedelta(seconds=1), 101.0)
    assert state.first_spot_at_or_after(START + timedelta(seconds=10)) is None


def test_zscore_needs_history_then_matches_hand_computation():
    now = START + timedelta(minutes=10)
    short = CollectorState(spot=SpotPrice(103.0, now, "test"))
    short.add_spot_to_history(now, 103.0)
    assert short.zscore_10m(now) is None

    state = CollectorState(spot=SpotPrice(103.0, now, "test"))
    # 60 points in the last minute, alternating 100 and 102: mean 101, standard deviation 1.
    for i in range(60):
        state.add_spot_to_history(now - timedelta(seconds=60 - i), 100.0 if i % 2 == 0 else 102.0)
    assert state.zscore_10m(now) == 2.0
