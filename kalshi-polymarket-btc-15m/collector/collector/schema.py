"""Output schema shared by the writers and the `validate` command."""

from __future__ import annotations

# Every raw event (one JSON object per line) has these fields.
RAW_FIELDS: tuple[str, ...] = (
    "ts_utc",  # when the event happened: the exchange or feed timestamp if it had one
    "recv_ts_utc",  # when the collector received or wrote it
    "source",  # polymarket | spotfeed | collector
    "event_type",
    "market_id",
    "market_slug",
    "interval",
    "run_id",
    "seq",
    "payload",
)

EVENT_TYPES: tuple[str, ...] = (
    "market_open_detected",
    "market_snapshot",
    "orderbook_l1",
    "orderbook_l2",
    "btc_spot",
    "heartbeat",
    "errors",
)

# One tick row per TICK_INTERVAL_SEC.  Missing values are written as empty cells, never as 0.
TICK_COLUMNS: tuple[str, ...] = (
    "ts_utc",
    "market_id",
    "t_since_open_sec",
    "t_left_sec",
    "btc_open_price",
    "btc_spot_price",
    "delta_spot_from_open",
    "yes_bid",
    "yes_ask",
    "yes_mid",
    "spread_yes",
    "yes_book_age_sec",
    "no_bid",
    "no_ask",
    "no_mid",
    "spread_no",
    "no_book_age_sec",
    "book_imbalance_yes",
    "impulse_per_min",
    "dir",
    "zscore_10m",
)
