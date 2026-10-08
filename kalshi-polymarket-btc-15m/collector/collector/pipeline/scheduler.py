"""The collector run.

Concurrent loops share one CollectorState:

- market discovery: find the current 15-minute window (every MARKET_DISCOVERY_SEC);
- order book: poll the YES and NO books of that window (every ORDERBOOK_POLL_SEC);
- RTDS: stream the BTC/USD reference price over a WebSocket (live mode only);
- spot: record each new price, and a heartbeat every 10 s (checks every SPOT_POLL_SEC);
- open price: take the first price stamped at or after the window start;
- ticks: write one CSV row (every TICK_INTERVAL_SEC).

Network errors are logged, written as `errors` events and retried.  So is "no current
window found", at most once a minute.  Any other failure that ends a loop stops the
whole run with CollectorFailed, so a supervisor sees it, instead of the run carrying on
with a missing piece.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from collector.config import CollectorConfig, load_config
from collector.pipeline.aggregator import build_tick
from collector.pipeline.state import CollectorState
from collector.providers.mock import MockPolymarketProvider, MockSpotFeedProvider
from collector.providers.polymarket import PolymarketProvider
from collector.providers.spotfeed import SpotFeedProvider
from collector.storage.csv_writer import CSVWriter
from collector.storage.jsonl_writer import JSONLWriter
from collector.utils.logsetup import setup_logging

logger = logging.getLogger("collector")

HEARTBEAT_SEC = 10.0
NOT_FOUND_REPORT_SEC = 60.0
OPEN_PRICE_CHECK_SEC = 0.5
RTDS_RECV_TIMEOUT_SEC = 60.0
RTDS_MAX_BACKOFF_SEC = 60.0


class CollectorFailed(RuntimeError):
    """A collector loop stopped unexpectedly."""


def build_providers(cfg: CollectorConfig) -> tuple[Any, Any]:
    """Market provider and spot provider for this configuration."""
    if cfg.market_provider == "mock":
        market: Any = MockPolymarketProvider()
    else:
        market = PolymarketProvider(
            gamma_url=cfg.polymarket.gamma_url,
            clob_url=cfg.polymarket.clob_url,
            bitcoin_tag_id=cfg.polymarket.bitcoin_tag_id,
        )
    if cfg.spot_provider == "mock":
        spot: Any = MockSpotFeedProvider()
    else:
        spot = SpotFeedProvider(rtds_url=cfg.polymarket.rtds_url)
    return market, spot


def _install_signal_handlers(shutdown: asyncio.Event) -> list[signal.Signals]:
    loop = asyncio.get_running_loop()
    installed = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown.set)
        except (NotImplementedError, RuntimeError, ValueError):
            continue  # on Windows Ctrl+C arrives as KeyboardInterrupt instead
        installed.append(sig)
    return installed


async def run_collector(
    config_path: str | None = None,
    *,
    cfg: CollectorConfig | None = None,
    duration_sec: float | None = None,
    handle_signals: bool = True,
    providers: tuple[Any, Any] | None = None,
) -> str:
    """Run until stopped (signal or `duration_sec`).  Returns the run id.

    `providers` replaces the configured (market, spot) providers; tests use it.
    Raises CollectorFailed if a loop dies.
    """
    if cfg is None:
        cfg = load_config(config_path)
    setup_logging(cfg.log_level)

    run_id = str(uuid.uuid4())
    state = CollectorState()
    pm, spot_provider = providers or build_providers(cfg)
    jsonl = JSONLWriter(base_dir=cfg.output.dir, run_id=run_id, raw_subdir=cfg.output.raw_subdir)
    csv_w = CSVWriter(base_dir=cfg.output.dir, ticks_subdir=cfg.output.ticks_subdir)
    iv = cfg.intervals
    shutdown = asyncio.Event()

    def market_fields() -> tuple[str, str]:
        m = state.market
        return (m.market_id, m.slug) if m else ("", "")

    def record_error(phase: str, exc: Exception, **extra: Any) -> None:
        logger.warning("%s failed: %r", phase, exc)
        jsonl.write(
            event_type="errors",
            market_id=market_fields()[0],
            market_slug=market_fields()[1],
            payload={"phase": phase, "error": repr(exc), **extra},
            source="collector",
        )

    async def market_discovery_loop() -> None:
        last_not_found: float | None = None
        while not shutdown.is_set():
            try:
                market = await pm.find_current_15m_market()
            except Exception as exc:  # network or API error: record and retry
                record_error("market_discovery", exc)
                market = None
            else:
                # Finding nothing is not an exception, but it must not pass silently:
                # a changed slug format or tag would leave the collector idle forever.
                if market is None and (
                    last_not_found is None or time.monotonic() - last_not_found >= NOT_FOUND_REPORT_SEC
                ):
                    last_not_found = time.monotonic()
                    record_error("market_discovery", LookupError("no current 15-minute BTC window found"))
            if market is not None and (state.market is None or state.market.slug != market.slug):
                state.set_market(market)
                jsonl.write(
                    event_type="market_open_detected",
                    market_id=market.market_id,
                    market_slug=market.slug,
                    payload={
                        "start_time": market.start_time.isoformat(),
                        "end_time": market.end_time.isoformat(),
                        "yes_up_id": market.yes_up_id,
                        "no_down_id": market.no_down_id,
                    },
                    source="polymarket",
                )
                logger.info("market %s", market.slug)
            await asyncio.sleep(iv.market_discovery_sec)

    async def orderbook_loop() -> None:
        depth = cfg.orderbook.l2_depth
        while not shutdown.is_set():
            market = state.market
            if market is not None:
                for token_id, side in ((market.yes_up_id, "yes"), (market.no_down_id, "no")):
                    try:
                        data = await pm.fetch_orderbook(token_id, depth=depth)
                    except Exception as exc:  # network or API error: record and retry
                        record_error("orderbook", exc, side=side)
                        continue
                    if not data or state.market is not market:  # empty, or the window changed
                        continue
                    recv_ts = datetime.now(timezone.utc)
                    l1 = pm.parse_orderbook_l1(data, token_id, side, recv_ts)
                    l2 = pm.parse_orderbook_l2(data, token_id, side, depth, recv_ts)
                    if side == "yes":
                        state.yes_l1, state.yes_l2 = l1, l2
                    else:
                        state.no_l1, state.no_l2 = l1, l2
                    if l1 is not None:
                        jsonl.write(
                            event_type="orderbook_l1",
                            market_id=market.market_id,
                            market_slug=market.slug,
                            payload={
                                "side": side,
                                "bid_price": l1.bid_price,
                                "bid_size": l1.bid_size,
                                "ask_price": l1.ask_price,
                                "ask_size": l1.ask_size,
                            },
                            ts_utc=l1.ts,
                            recv_ts_utc=recv_ts,
                        )
                    jsonl.write(
                        event_type="orderbook_l2",
                        market_id=market.market_id,
                        market_slug=market.slug,
                        payload={
                            "side": side,
                            "bids": [[lv.price, lv.size] for lv in l2.bids],
                            "asks": [[lv.price, lv.size] for lv in l2.asks],
                        },
                        ts_utc=l2.ts,
                        recv_ts_utc=recv_ts,
                    )
            await asyncio.sleep(iv.orderbook_poll_sec)

    async def rtds_loop() -> None:
        import websockets

        backoff = 2.0
        while not shutdown.is_set():
            try:
                async with websockets.connect(spot_provider.rtds_url) as ws:
                    await ws.send(json.dumps(spot_provider.subscribe_message()))
                    logger.info("RTDS subscribed to %s", spot_provider.symbol)
                    backoff = 2.0
                    while not shutdown.is_set():
                        msg = await asyncio.wait_for(ws.recv(), timeout=RTDS_RECV_TIMEOUT_SEC)
                        if isinstance(msg, str) and msg.strip().upper() == "PONG":
                            continue
                        sp = spot_provider.update_from_message(msg)
                        if sp is not None:
                            state.spot = sp
                            state.add_spot_to_history(sp.ts, sp.price)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # disconnects and timeouts: reconnect with backoff
                logger.warning("RTDS connection lost (%r); reconnecting in %.0f s", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RTDS_MAX_BACKOFF_SEC)

    async def spot_loop() -> None:
        last_written: datetime | None = None
        last_heartbeat = time.monotonic()
        while not shutdown.is_set():
            sp = spot_provider.get_last()
            if sp is not None and (last_written is None or sp.ts > last_written):
                last_written = sp.ts
                if state.spot is None or sp.ts >= state.spot.ts:
                    state.spot = sp
                state.add_spot_to_history(sp.ts, sp.price)
                market_id, slug = market_fields()
                jsonl.write(
                    event_type="btc_spot",
                    market_id=market_id,
                    market_slug=slug,
                    payload={"price": sp.price, "source": sp.source},
                    source="spotfeed",
                    ts_utc=sp.ts,
                )
            if time.monotonic() - last_heartbeat >= HEARTBEAT_SEC:
                last_heartbeat = time.monotonic()
                age = None
                if state.spot is not None:
                    age = round((datetime.now(timezone.utc) - state.spot.ts).total_seconds(), 3)
                market_id, slug = market_fields()
                jsonl.write(
                    event_type="heartbeat",
                    market_id=market_id,
                    market_slug=slug,
                    payload={"spot_age_sec": age},
                    source="collector",
                )
            await asyncio.sleep(iv.spot_poll_sec)

    async def open_price_loop() -> None:
        while not shutdown.is_set():
            market = state.market
            if market is not None and not state.open_price_decided:
                first = state.first_spot_at_or_after(market.start_time)
                if first is not None:
                    ts, price = first
                    lag = (ts - market.start_time).total_seconds()
                    state.open_price_decided = True
                    if lag <= iv.open_price_max_lag_sec:
                        state.btc_open_price, state.btc_open_ts = price, ts
                        payload: dict[str, Any] = {
                            "btc_open_price": price,
                            "btc_open_ts": ts.isoformat(),
                            "open_lag_sec": round(lag, 3),
                        }
                        logger.info("open price %.2f for %s", price, market.slug)
                    else:
                        payload = {
                            "btc_open_price": None,
                            "open_lag_sec": round(lag, 3),
                            "reason": "first price after the window start came too late",
                        }
                        logger.info("no open price for %s: first price came %.1f s late", market.slug, lag)
                    jsonl.write(
                        event_type="market_snapshot",
                        market_id=market.market_id,
                        market_slug=market.slug,
                        payload=payload,
                        source="collector",
                    )
            await asyncio.sleep(OPEN_PRICE_CHECK_SEC)

    async def tick_loop() -> None:
        while not shutdown.is_set():
            await asyncio.sleep(iv.tick_interval_sec)
            market = state.market
            if market is not None and (state.spot or state.yes_l1 or state.no_l1):
                csv_w.write_tick(build_tick(state), market.market_id)

    async def stop_after(seconds: float) -> None:
        await asyncio.sleep(seconds)
        logger.info("duration reached (%.1f s), stopping", seconds)
        shutdown.set()

    loops = {
        "market_discovery": market_discovery_loop(),
        "orderbook": orderbook_loop(),
        "spot": spot_loop(),
        "open_price": open_price_loop(),
        "ticks": tick_loop(),
    }
    if isinstance(spot_provider, SpotFeedProvider):
        loops["rtds"] = rtds_loop()

    tasks = [asyncio.create_task(coro, name=name) for name, coro in loops.items()]
    stop_waiter = asyncio.create_task(shutdown.wait(), name="shutdown")
    extra = [asyncio.create_task(stop_after(duration_sec), name="duration")] if duration_sec else []
    signals = _install_signal_handlers(shutdown) if handle_signals else []
    logger.info(
        "collector started run_id=%s market=%s spot=%s output=%s",
        run_id,
        type(pm).__name__,
        type(spot_provider).__name__,
        cfg.output.dir,
    )

    failure: str | None = None
    try:
        done, _ = await asyncio.wait([*tasks, stop_waiter], return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task is stop_waiter or task.cancelled():
                continue
            exc = task.exception()
            if exc is not None:
                failure = f"loop '{task.get_name()}' crashed: {exc!r}"
                logger.error("%s", failure, exc_info=exc)
            elif not shutdown.is_set():
                failure = f"loop '{task.get_name()}' returned unexpectedly"
                logger.error("%s", failure)
    finally:
        shutdown.set()
        pending = [*tasks, stop_waiter, *extra]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        running_loop = asyncio.get_running_loop()
        for sig in signals:
            running_loop.remove_signal_handler(sig)
        jsonl.close()
        csv_w.close()
        await pm.aclose()
        logger.info("collector stopped run_id=%s", run_id)

    if failure:
        raise CollectorFailed(failure)
    return run_id
