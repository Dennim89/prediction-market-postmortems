"""Tick rows built from state."""

from datetime import timedelta

from collector.pipeline.aggregator import build_tick
from collector.pipeline.state import CollectorState
from collector.providers.base import OrderbookL1, SpotPrice
from collector.schema import TICK_COLUMNS
from tests.helpers import NOW, START, make_market


def test_empty_state_gives_an_empty_row():
    tick = build_tick(CollectorState(), now=NOW)
    assert list(tick) == list(TICK_COLUMNS)
    assert tick["ts_utc"] == NOW.isoformat()
    assert all(tick[c] is None for c in TICK_COLUMNS if c != "ts_utc")


def test_open_and_spot_give_delta_direction_and_impulse():
    state = CollectorState(
        market=make_market(),
        btc_open_price=100_000.0,
        spot=SpotPrice(100_030.0, NOW, "test"),
    )
    tick = build_tick(state, now=NOW)  # five minutes in, ten minutes left
    assert tick["market_id"] == "fake-condition-0001"
    assert tick["t_since_open_sec"] == 300
    assert tick["t_left_sec"] == 600
    assert tick["delta_spot_from_open"] == 30.0
    assert tick["dir"] == 1
    assert tick["impulse_per_min"] == 3.0  # 30 USD over 10 minutes left


def test_falling_price_near_the_end_of_the_window():
    state = CollectorState(
        market=make_market(),
        btc_open_price=100_000.0,
        spot=SpotPrice(99_990.0, NOW, "test"),
    )
    tick = build_tick(state, now=START + timedelta(minutes=14, seconds=50))
    assert tick["dir"] == -1
    assert tick["impulse_per_min"] == 20.0  # 10 USD over the 0.5-minute floor


def test_no_open_price_means_no_delta():
    state = CollectorState(market=make_market(), spot=SpotPrice(100_030.0, NOW, "test"))
    tick = build_tick(state, now=NOW)
    assert tick["btc_spot_price"] == 100_030.0
    assert tick["btc_open_price"] is None
    assert tick["delta_spot_from_open"] is None
    assert tick["dir"] is None


def test_book_fields_and_book_age():
    book_ts = NOW - timedelta(seconds=1.5)
    state = CollectorState(
        yes_l1=OrderbookL1("fake-up", "yes", 0.48, 100, 0.52, 150, book_ts),
        no_l1=OrderbookL1("fake-down", "no", 0.46, 80, 0.0, 0.0, book_ts),
    )
    tick = build_tick(state, now=NOW)
    assert (tick["yes_bid"], tick["yes_ask"], tick["yes_mid"], tick["spread_yes"]) == (0.48, 0.52, 0.5, 0.04)
    assert tick["yes_book_age_sec"] == 1.5
    assert tick["no_bid"] == 0.46
    assert tick["no_ask"] is None  # empty side is missing, not zero
    assert tick["no_mid"] is None
    assert tick["spread_no"] is None
