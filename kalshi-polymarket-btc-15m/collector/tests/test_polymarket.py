"""Polymarket provider: slug parsing, market discovery, order book parsing.

HTTP calls go to httpx.MockTransport; nothing leaves the machine.
"""

import asyncio
import json
from datetime import timedelta

import httpx

from collector.providers.polymarket import PolymarketProvider, parse_15m_slug
from tests.helpers import NOW, START

pick = PolymarketProvider.pick_current_market


def test_parse_15m_slug():
    start, end = parse_15m_slug("btc-updown-15m-1767225600")
    assert start == START
    assert end - start == timedelta(minutes=15)
    for bad in ("invalid", "btc-updown-15m-abc", "btc-updown-1h-1767225600", "", "btc-updown-15m-1767225600-x"):
        assert parse_15m_slug(bad) == (None, None)


def test_pick_current_market_from_gamma_fixture(gamma_events):
    market = pick(gamma_events, NOW)
    assert market is not None
    assert market.slug == "btc-updown-15m-1767225600"
    assert market.market_id == market.condition_id == "fake-condition-0001"
    assert market.yes_up_id == "fake-token-up-0001"
    assert market.no_down_id == "fake-token-down-0001"
    assert market.start_time == START
    assert market.end_time == START + timedelta(minutes=15)


def test_pick_current_market_window_edges(gamma_events):
    assert pick(gamma_events, START).slug == "btc-updown-15m-1767225600"
    assert pick(gamma_events, START - timedelta(seconds=1)).slug == "btc-updown-15m-1767224700"
    assert pick(gamma_events, START + timedelta(minutes=15)).slug == "btc-updown-15m-1767226500"
    assert pick(gamma_events, START + timedelta(hours=3)) is None
    assert pick("not a list", NOW) is None


def _one_event(outcomes, tokens):
    return [
        {
            "slug": "btc-updown-15m-1767225600",
            "title": "synthetic",
            "markets": [
                {
                    "conditionId": "fake-condition-0009",
                    "outcomes": json.dumps(outcomes),
                    "clobTokenIds": json.dumps(tokens),
                }
            ],
        }
    ]


def test_pick_current_market_maps_reversed_outcomes():
    market = pick(_one_event(["Down", "Up"], ["fake-a", "fake-b"]), NOW)
    assert market.yes_up_id == "fake-b"
    assert market.no_down_id == "fake-a"


def test_pick_current_market_skips_events_it_cannot_map():
    assert pick(_one_event(["Foo", "Bar"], ["fake-a", "fake-b"]), NOW) is None
    assert pick(_one_event(["Up", "Up"], ["fake-a", "fake-b"]), NOW) is None
    assert pick(_one_event(["Up"], ["fake-a"]), NOW) is None


def _run(pm, coro_factory):
    async def go():
        try:
            return await coro_factory()
        finally:
            await pm.aclose()

    return asyncio.run(go())


def test_find_current_market_queries_gamma_events(gamma_events):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=gamma_events)

    pm = PolymarketProvider(gamma_url="https://gamma.test", transport=httpx.MockTransport(handler))
    market = _run(pm, lambda: pm.find_current_15m_market(now=NOW))
    assert market.slug == "btc-updown-15m-1767225600"
    assert seen["path"] == "/events"
    assert seen["params"]["tag_id"] == "235"
    assert seen["params"]["closed"] == "false"


def test_fetch_orderbook_returns_book_or_none(clob_book):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/book" and request.url.params.get("token_id") == "fake-token-up-0001":
            return httpx.Response(200, json=clob_book)
        return httpx.Response(404, json={"error": "not found"})

    pm = PolymarketProvider(clob_url="https://clob.test", transport=httpx.MockTransport(handler))

    async def both():
        return await pm.fetch_orderbook("fake-token-up-0001"), await pm.fetch_orderbook("fake-token-missing")

    found, missing = _run(pm, both)
    assert found == clob_book
    assert missing is None


def test_parse_orderbook_l1_from_price_size_pairs():
    data = {
        "bids": [["0.48", "100"], ["0.47", "200"]],
        "asks": [["0.52", "150"], ["0.53", "80"]],
        "timestamp": "2026-01-01T00:05:00Z",
    }
    l1 = PolymarketProvider().parse_orderbook_l1(data, "fake-token-up-0001", "yes")
    assert (l1.bid_price, l1.bid_size, l1.ask_price, l1.ask_size) == (0.48, 100, 0.52, 150)
    assert l1.ts == NOW


def test_best_prices_do_not_depend_on_level_order(clob_book):
    # The fixture lists the best prices last.
    l1 = PolymarketProvider().parse_orderbook_l1(clob_book, "fake-token-up-0001", "yes")
    assert (l1.bid_price, l1.bid_size) == (0.48, 120)
    assert (l1.ask_price, l1.ask_size) == (0.52, 90)
    assert l1.ts == NOW  # Unix milliseconds in the fixture


def test_parse_orderbook_l2_is_best_first_and_cut_to_depth(clob_book):
    l2 = PolymarketProvider().parse_orderbook_l2(clob_book, "fake-token-up-0001", "yes", depth=2)
    assert [lv.price for lv in l2.bids] == [0.48, 0.47]
    assert [lv.price for lv in l2.asks] == [0.52, 0.53]
    assert l2.ts == NOW


def test_book_without_timestamp_uses_receive_time():
    recv = START + timedelta(minutes=7)
    data = {"bids": [{"price": "0.40", "size": "10"}], "asks": []}
    l1 = PolymarketProvider().parse_orderbook_l1(data, "fake-token-up-0001", "yes", recv_ts=recv)
    assert l1.ts == recv
    assert l1.bid_price == 0.40
    assert l1.ask_price == 0.0  # empty side


def test_empty_book_has_no_l1():
    data = {"bids": [], "asks": [{"price": "0", "size": "5"}]}
    assert PolymarketProvider().parse_orderbook_l1(data, "fake-token-up-0001", "yes") is None


def test_malformed_levels_are_skipped():
    data = {"bids": [["0.30"], ["abc", "1"], {"price": "0.31", "size": "4"}, None], "asks": [{"size": "3"}]}
    l1 = PolymarketProvider().parse_orderbook_l1(data, "fake-token-up-0001", "yes")
    assert l1.bid_price == 0.31
    assert l1.ask_price == 0.0
