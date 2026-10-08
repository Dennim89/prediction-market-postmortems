"""RTDS spot feed: subscription and message parsing."""

import json
from datetime import datetime, timezone

from collector.providers.spotfeed import SpotFeedProvider


def at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def test_subscribe_message():
    msg = SpotFeedProvider().subscribe_message()
    sub = msg["subscriptions"][0]
    assert msg["action"] == "subscribe"
    assert sub["topic"] == "crypto_prices_chainlink"
    assert json.loads(sub["filters"]) == {"symbol": "btc/usd"}


def test_single_point_with_millisecond_timestamp(rtds_messages):
    feed = SpotFeedProvider()
    sp = feed.update_from_message(json.dumps(rtds_messages["single_ms"]))
    assert sp.price == 100000.5
    assert sp.ts == at(1767225600)
    assert feed.get_last() == sp


def test_batch_uses_newest_point(rtds_messages):
    sp = SpotFeedProvider().update_from_message(json.dumps(rtds_messages["batch"]))
    assert sp.price == 100003.0
    assert sp.ts == at(1767225603)


def test_seconds_timestamp_and_bytes_input(rtds_messages):
    sp = SpotFeedProvider().update_from_message(json.dumps(rtds_messages["single_seconds"]).encode())
    assert sp.price == 100004.0
    assert sp.ts == at(1767225604)


def test_rejects_other_symbols_bad_values_and_garbage(rtds_messages):
    feed = SpotFeedProvider()
    good = feed.update_from_message(json.dumps(rtds_messages["single_ms"]))
    for name in ("other_symbol", "out_of_range", "no_payload"):
        assert feed.update_from_message(json.dumps(rtds_messages[name])) is None
    for raw in ("not json", "PONG", "[]", ""):
        assert feed.update_from_message(raw) is None
    assert feed.get_last() == good


def test_older_point_does_not_replace_newer(rtds_messages):
    feed = SpotFeedProvider()
    newer = feed.update_from_message(json.dumps(rtds_messages["batch"]))
    assert feed.update_from_message(json.dumps(rtds_messages["single_ms"])) is None
    assert feed.get_last() == newer
