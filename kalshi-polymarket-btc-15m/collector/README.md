# Polymarket BTC 15-minute market collector

Records Polymarket's 15-minute "Bitcoin Up or Down" markets for later analysis. It finds the
current window, polls the order books of its Up and Down outcomes, follows the Chainlink
BTC/USD price that Polymarket streams over its real-time data socket (RTDS), and writes:

- every raw event as one line of JSON: `data/raw/<UTC date>/<market id>.jsonl`;
- one tick row every 5 seconds as CSV: `data/ticks/<UTC date>/<market id>.csv`.

It is read-only: public endpoints, no keys, no orders. It comes from the project described in
the [Kalshi and Polymarket postmortem](../README.md). For people who want their own record of
these markets instead of trusting someone else's numbers.

**Status: experimental.** The tests run offline on synthetic data. The live endpoints were
last used in 2026 and were not checked again for this release. Polymarket planned to move its
order book API to a new version (CLOB V2) on 2026-04-28. Read each venue's API terms before
you run it against the live service.

## Quickstart

```bash
cd kalshi-polymarket-btc-15m/collector
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
python -m collector run --mock --duration-sec 15
```

The last command uses synthetic data and makes no network calls. Without `--mock` the collector
reads the live endpoints until Ctrl+C. On Windows, activate with `.venv\Scripts\activate`.

## Sample output

Tick rows from the `--mock` run above. The data is synthetic and some columns are left out:

```text
ts_utc,btc_open_price,btc_spot_price,yes_bid,yes_ask,yes_mid,yes_book_age_sec,no_bid,no_ask,no_book_age_sec,dir
2026-10-08T13:10:43.139142+00:00,99998.24,99996.26,0.48,0.5,0.49,0.995,0.5,0.52,0.995,-1
2026-10-08T13:10:48.140956+00:00,99998.24,99992.34,0.48,0.5,0.49,0.989,0.5,0.52,0.989,-1
```

Check a raw file with `python -m collector validate data/raw/<date>/<market id>.jsonl`. For the
run above it printed `OK: 71 events`.

## Configuration

Every setting has a default, so no configuration is needed. To change something, copy
`.env.example` to `.env` or `config.yaml.example` to `config.yaml` and edit it. Environment
variables win over `config.yaml`. Nothing here is secret.

| Environment variable | config.yaml key | Default | Meaning |
|---|---|---|---|
| `MARKET_PROVIDER` | `providers.market` | `polymarket` | `polymarket`, or `mock` for synthetic data |
| `SPOT_PROVIDER` | `providers.spot` | `rtds` | `rtds`, or `mock` for synthetic data |
| `POLYMARKET_GAMMA_URL` | `polymarket.gamma_url` | `https://gamma-api.polymarket.com` | market discovery |
| `POLYMARKET_CLOB_URL` | `polymarket.clob_url` | `https://clob.polymarket.com` | order books |
| `POLYMARKET_RTDS_URL` | `polymarket.rtds_url` | `wss://ws-live-data.polymarket.com` | reference price stream |
| `POLYMARKET_BITCOIN_TAG_ID` | `polymarket.bitcoin_tag_id` | `235` | Gamma tag used to list Bitcoin events |
| `OUTPUT_DIR` | `output.dir` | `./data` | output folder |
| `TICK_INTERVAL_SEC` | `intervals.tick_interval_sec` | `5` | seconds between tick rows |
| `ORDERBOOK_POLL_SEC` | `intervals.orderbook_poll_sec` | `1` | seconds between book polls |
| `SPOT_POLL_SEC` | `intervals.spot_poll_sec` | `2` | seconds between `btc_spot` events |
| `MARKET_DISCOVERY_SEC` | `intervals.market_discovery_sec` | `10` | seconds between window lookups |
| `OPEN_PRICE_MAX_LAG_SEC` | `intervals.open_price_max_lag_sec` | `5` | see "Limits" |
| `L2_DEPTH` | `orderbook.l2_depth` | `10` | book levels kept per side |
| `LOG_LEVEL` | `logging.level` | `INFO` | |

## Output

### Raw events (JSONL)

Every event has `ts_utc` (when it happened: the exchange or feed timestamp if the message had
one), `recv_ts_utc` (when the collector received it), `source`, `event_type`, `market_id`,
`market_slug`, `interval`, `run_id`, `seq` and `payload`.

| `event_type` | Written when | `payload` |
|---|---|---|
| `market_open_detected` | a new window is found | start and end time, Up and Down token ids |
| `market_snapshot` | the open price is captured, or found missing | `btc_open_price`, `btc_open_ts`, `open_lag_sec`, or a reason |
| `orderbook_l1` | each book poll | side, best bid and best ask with sizes |
| `orderbook_l2` | each book poll | side, top `L2_DEPTH` levels, best price first |
| `btc_spot` | a new reference price, checked every `SPOT_POLL_SEC` | price, source |
| `heartbeat` | every 10 seconds | age of the latest reference price |
| `errors` | a network or API call fails, or no current window is found | phase, error |

### Tick rows (CSV)

Missing values are empty cells, never 0.

| Column | Meaning |
|---|---|
| `ts_utc` | when the row was built (local clock, UTC) |
| `market_id` | Polymarket condition id of the window |
| `t_since_open_sec`, `t_left_sec` | seconds since the window started and until it ends |
| `btc_open_price` | our reading of the reference price at the window start (see "Limits") |
| `btc_spot_price` | latest reference price |
| `delta_spot_from_open` | `btc_spot_price - btc_open_price` |
| `yes_bid`, `yes_ask` | best prices of the Up outcome |
| `yes_mid`, `spread_yes` | mid and spread, only when both sides have a price |
| `yes_book_age_sec` | age of the Up prices at tick time |
| `no_bid` ... `no_book_age_sec` | the same for the Down outcome |
| `book_imbalance_yes` | (bid size - ask size) / (bid size + ask size) over the top 5 Up levels |
| `impulse_per_min` | absolute delta divided by the minutes left, with a floor of 0.5 minutes |
| `dir` | sign of the delta: 1, 0 or -1 |
| `zscore_10m` | latest price against the mean and standard deviation of the last 10 minutes; empty until there are enough points |

## Limits

- One market type on one venue. Kalshi is not collected here.
- The order book is polled over REST, by default once a second per side, so quotes can lag
  the exchange. Each quote keeps the book's own timestamp when the response has one: compare
  `ts_utc` with `recv_ts_utc` in the raw events, and look at `*_book_age_sec` in the ticks,
  before you trust a quote. Book age assumes the local clock is in sync (use NTP). In the
  project this code comes from, quotes from another order-book collector lagged the exchange,
  and paper results built on them could not be trusted.
- `btc_open_price` is our own reading of the Chainlink stream, not the venue's official start
  price. It is taken only from the first price stamped at or after the window start, and only
  if that price came within `OPEN_PRICE_MAX_LAG_SEC`; otherwise the window has no open price.
  Never score a position on these columns. Score it on the venue's own resolution.
- The raw log samples the reference price every `SPOT_POLL_SEC`. It does not keep every RTDS
  message.
- Market discovery asks Gamma for up to 500 open events with the Bitcoin tag and picks the
  `btc-updown-15m-<start>` event whose window contains the current time. If Polymarket changes
  the slug format or the tag, discovery finds nothing and says so in `errors` once a minute.
- Prices outside 10,000 to 1,000,000 USD are dropped as garbage (`MIN_PRICE` and `MAX_PRICE` in
  `collector/providers/spotfeed.py`).
- The message shapes the parsers expect were not compared with the live API for this release.

## How it works

`collector/pipeline/scheduler.py` runs concurrent loops over one shared state: market discovery,
book polling, the RTDS stream, price recording, open-price capture and tick writing. Network
errors are written to `errors` and retried. If a loop dies for any other reason, the whole run
stops with an error, so a process supervisor notices instead of the collector running on with a
missing piece.

```text
collector/
  main.py              command line: run, validate
  config.py            defaults, config.yaml, environment variables
  schema.py            raw event fields, event types, tick columns
  pipeline/            scheduler, state, tick builder
  providers/           Polymarket (Gamma and CLOB), RTDS spot feed, synthetic mocks
  storage/             JSONL and CSV writers
  utils/               time parsing, logging
tests/                 offline tests; fixtures/ holds hand-written synthetic responses
```

## Tests

`pytest -q` runs 67 tests in about 6 seconds with no network access. They passed on Python 3.10
and 3.13. The files in `tests/fixtures/` are synthetic and written by hand. They follow the
response shapes the code expects; they are not captures of the live API.

## Changes from the archived version

The archived collector had 8 tests and a README in Ukrainian. For this release:

- Book levels are sorted before the best prices and the top levels are taken. Before, the top
  levels were the first ones in the response, which is right only if the API lists the best
  price first.
- Book timestamps sent as Unix seconds or milliseconds are read. Before, only ISO strings were,
  and anything else silently became the local receive time.
- From a batch of RTDS prices the newest one is used (before: the first), and an older price
  never replaces a newer one.
- The open price must be stamped at most `OPEN_PRICE_MAX_LAG_SEC` after the window start.
  Before, any price seen in the first two minutes counted as the open.
- Missing values are empty cells instead of 0. New columns `yes_book_age_sec` and
  `no_book_age_sec`. Columns that were never filled (last trade price and size, notes) are gone.
- Environment variables override `config.yaml`, as the old docstring said. Before, the file won.
- A loop that dies stops the run, and "no current window" is reported. Before, both were silent.
- `--mock` runs fully offline; before, mock mode still called the Polymarket API.
  `--duration-sec` stops a run by itself.
- Removed: a `backfill` command and a Chainlink REST option that were never implemented, an
  unused Parquet writer and retry helper, and the browser-style `Origin` and `User-Agent`
  headers on the WebSocket connection.
