# Up/down market audits and evaluation harness

Checks a dataset of Polymarket-style up/down markets before you trust a backtest on it, and
evaluates a trading rule with fees, a time split and a check for sizing fitted in-sample. Each
check matches an error that inflated our numbers in the project described in the
[64-day postmortem](../README.md). For people who backtest short-horizon prediction markets.

**Status: experimental.** The tests run offline on synthetic data. The original audits ran on
64 days of archived order books that are not included, and this rewrite has not been run on
that data.

Built with AI coding agents (Claude, Codex).

## Quickstart

```bash
cd polymarket-btc-updown-audits/harness
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
python -m updown_audit demo
```

On Windows, activate with `.venv\Scripts\activate`. The demo builds 72 hours of synthetic
markets in memory and makes no network calls.

## Sample output

From `python -m updown_audit demo`, shortened. The synthetic quotes are fair by construction,
so there is no edge to find, and 3 quote rows are crossed on purpose. The numbers show what the
checks report on that data, not what the real markets did.

```text
  Labels from 1-minute candles against the venue's outcome, 15m
    alignment  start_candle_opens  end_candle_opens  markets  agree
    A                     end-16m            end-1m      288  97.9%
    B                     end-15m            end+0m      288  89.9%
    C                     end-15m            end-1m      288  90.3%
    D                     end-16m            end+0m      288  94.8%

  5- and 15-minute windows that end together
    pairs  agree
    288    69.8%

2. Lookahead check: when each input of the pin rule (threshold 0.9) became known
    input                known_from  trades  known_after_entry  unknown_time  share_late
    m5_close            m5_close_ts     742                  0             0        0.0%
    spread_at_entry  entry_quote_ts     742                  0             0        0.0%
    lifetime_spread           end15     742                742             0      100.0%
    m5_vote              m5_vote_ts     742                494             0       66.6%

3. What late inputs do to the hit rate (on fair prices the hit rate should match the price)
    rule                                        trades    hit  avg_price  hit_minus_price
    pin rule                                       742  71.8%      72.5%         -0.7 pts
    pin rule, lifetime spread in lowest 10%         75  81.3%      76.2%         +5.1 pts
    pin rule, spread at entry in lowest 10%        121  81.8%      81.4%         +0.5 pts
    vote of all three 5-minute markets, slot 1     288  85.8%      59.9%        +25.9 pts

5. Sizing fitted in-sample: one rule fitted on all data and on the train part only
    variant                      train_net_per_share  test_net_per_share
    flat, one share                           -3.58c              -0.10c
    sized, fitted on all data                 -0.09c              +6.96c
    sized, fitted on train only               +3.19c              -0.10c
```

The full report also covers coverage, window lengths, the share of Up outcomes, crossed books,
disagreement by the size of the move, calibration, quotes per day, and fees before and after a
time split.

## What each check catches

| Check | Function | The error it caught in the project |
|---|---|---|
| Window lengths | `audits.window_lengths` | The start time in the market data was the time a market was created, about a day before its window. |
| Candle labels | `audits.label_agreement`, `disagreement_by_move` | Which candle alignment matches the venue's outcomes, and where a candle label goes wrong: on small moves. |
| Same-end agreement | `audits.same_end_agreement` | A 5-minute market and a 15-minute market that end together are different bets. The project scored one on the other's outcome. |
| Books, calibration, coverage, quotes per day | `audits.book_sanity`, `calibration`, `coverage`, `daily_density`, `winner_balance` | Crossed books, prices that do not match outcomes, missing markets and thin days. |
| Lookahead | `checks.lookahead` | Inputs known after the entry: votes that used later closes, and a filter on a spread averaged over the market's whole life. |
| Duplicate keys | `checks.duplicate_keys` | A LEFT JOIN that duplicated rows and made an extra leg look profitable. |
| Wrong market | `checks.wrong_market` | A position bought in one market and scored on another market's outcome. |
| Fees and split | `evaluate.evaluate` | Results before fees, and periods of different length compared by their totals. |
| In-sample sizing | `evaluate.sizing_check` | Size multipliers fitted on the same data they were scored on. |
| Reproducible resampling | `evaluate.subsample` | Seeds that drew different trades on every run. |

## Use it on your own data

The audits read three tables from a DuckDB file (all times UTC, without a time zone):

| Table | Columns |
|---|---|
| `markets` | `market_id`; `tf` (`5m`, `15m` or `1h`); `start_ts` and `end_ts` of the window; `winner` (`Up` or `Down`; `Yes` and `No` also work) as the venue resolved it |
| `quotes` | `market_id`, `ts`, `yes_bid`, `yes_ask`, `no_bid`, `no_ask` (NULL when a side is empty) |
| `candles` | `open_time` (start of the minute) and `close`, for 1-minute candles of a reference price |

Build them from your own collector or another source. This repository does not ship data and
does not download any. `python -m updown_audit synth --out example.duckdb` writes the synthetic
tables, so you can see the layout. Then:

```bash
python -m updown_audit audit --db example.duckdb
```

Without `--db`, the command reads `UPDOWN_DB` from the environment or from a `.env` file in the
current folder (see `.env.example`). Nothing else is configured and no keys are needed.

From Python, with pandas frames or a database file:

```python
from updown_audit import audits, checks, db, evaluate, signals

con = db.connect("example.duckdb", read_only=True)   # or db.load_frames(db.connect(), markets=..., quotes=..., candles=...)
print(audits.label_agreement(con, "15m"))
trades = signals.pin_trades(signals.pin_candidates(con), threshold=0.9)
print(checks.lookahead(trades, {"m5_close": "m5_close_ts", "spread_at_entry": "entry_quote_ts"}))
print(evaluate.evaluate(trades, fee_rate=0.10, split_at="2026-01-06 12:00"))
```

`evaluate` works on any trades table with `entry_ts`, `entry_price` and `won` (and
`min_bid_after` for a stop-loss exit), so you can use it for your own rule.

## Limits

- Up/down markets only. Multi-strike markets need their strike, which the tables do not have.
- The candle label is a check, not the truth. The venue may settle on another price source, so
  agreement a little under 100% is expected.
- The fee is `rate * p * (1 - p)` per share and per side. 0.10 is how the project read
  Polymarket's fee fields for these markets in April 2026. Look up the current schedule and pass
  its rate.
- A stop-loss exit is assumed to sell exactly at the stop price.
- `fit_bucket_sizing` is an example of a rule that overfits, there to show `sizing_check`. It is
  not a way to size trades.
- The lookahead check only knows the times you give it.
- The demo threshold of 0.9 is only an example.
- The SQL was written for tables of tens of millions of quote rows, but this rewrite has only
  been run on synthetic tables of up to about half a million rows.

## Tests

`pytest -q` runs 35 tests in about 5 to 8 seconds, offline. They passed on Python 3.11 with
pandas 2.1 and DuckDB 1.0, and on Python 3.13 with pandas 3.0 and DuckDB 1.5. All test data is
synthetic.

## Changes from the archived code

- One documented set of three tables instead of the archive's own tables, and no absolute local
  paths.
- Entry prices come from the last quote at or before the entry, with its age. The archived code
  took the 15-minute prices from a row stamped exactly 5 seconds before the 5-minute close. Its
  1-second table had rows only for seconds with book events, so windows without an update on
  both outcomes in that second were left out. The effect on its results is unknown.
- Every input of the example rule carries the time it became known.
- The BTC inputs of the archived sizing and filters are not included. They came from the
  1-minute candle that closes when the 5-minute market ends, 5 seconds after the entry.
- Resampling uses a stable hash. The archived harness used Python's built-in `hash()`, which
  changes from one process to the next, so its seeds drew different trades on every run.
- The fee rate and the split date are arguments, and per-day results divide by the length of
  each period.
- Not included: the v12 and v13 sizing functions and filters, the spot checks that call
  Binance, Coinbase and Polymarket over the network, and the download scripts.
