# Backtest checks for 5-minute up/down markets

A small taker backtest harness for Polymarket-style 5-minute up/down markets, with the checks
our project ran too late or not at all: sanity controls, a lookahead check, a split by day, a
friction model and a paper-log summary. It is plain Python with no dependencies. For people who
backtest short-horizon prediction markets and want a second opinion on a result that looks good.

It comes from the project in the [19x backtest postmortem](../README.md).

**Status: experimental.** The tests run offline on synthetic data. The original harness ran on
our own tick database, which is not included, and this version has not been run on real data.

Built with AI coding agents (Claude, Codex).

## Quickstart

```bash
cd polymarket-btc-5m-backtest/harness
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
python -m backtest_checks demo
```

On Windows, activate with `.venv\Scripts\activate`. The demo makes no network calls.

## Sample output

From `python -m backtest_checks demo`, shortened. The data is synthetic: on day 1 the market's
quotes lag the reference price by 3 seconds, so a rule that sees the current price has a real
edge; on day 2 there is no lag and the true volatility is twice what the rule assumes. The
numbers show what the checks report on that data, not what any real market did.

```text
1. Controls: all days, no friction, mean of 16 resamples of the markets
   (won = share of shares that won; break-even = average price paid; losing = resamples with a loss)
                        trades    won  break-even  pnl/share  losing
  do nothing                 0      -           -          -       -
  naive rule                92  77.0%       66.1%     +10.9c    0/16
  random side              288  53.8%       55.0%      -1.2c   14/16
  cheaper side             288   5.7%        7.9%      -2.2c   16/16
  naive rule, inverted      92  23.0%       36.9%     -13.8c   16/16

2. Split by day, no friction
  day         markets                          trades    won  break-even  pnl/share
  2026-01-01      144  naive rule                  48  68.8%       52.0%     +16.7c
                       best tick in hindsight      48  85.4%       64.3%     +21.1c
  2026-01-02      144  naive rule                  41  82.9%       80.9%      +2.0c
                       best tick in hindsight      41  87.8%       80.1%      +7.7c

4. Lookahead: each market re-run on copies cut at checkpoints
  naive rule                        OK (288 markets, 8,743 checkpoints)
  best tick in hindsight  LEAKS: decisions changed in 61 of 288 markets
```

The full report also has a data section (how many markets have the venue's outcome, and how
often a label from the last price disagrees with it) and a friction table by day.

## What each check does

| Check | Command or function | What it catches |
|---|---|---|
| Controls | `controls.do_nothing`, `random_side`, `cheaper_side`, `inverted` | An evaluation that pays rules with no information. Do nothing must give exactly zero; on fair prices, random and cheaper-side rules lose about the spread; the inverted copy of a rule with an edge must lose. Passing says the evaluation is consistent, not that an edge will last. |
| Lookahead | `controls.future_leak(strategy, markets)` | A decision that uses data from after its own time. Each market is re-run on copies cut at checkpoints, with the outcome hidden; trades up to the checkpoint must not change. The project's later versions picked the tick with the largest edge in the window, and this check flags that. |
| Split by day | `harness.by_day`, section 2 of the report | A result that comes from one day. |
| Friction | `friction.Friction`, `friction.SCENARIOS` | A result that only exists without costs: a fee that peaks at a price of 0.50, slippage, a cap on the share of the shown ask size you can take, a fill some ticks late, noise on the settlement price and the tie rule. |
| Labels | `Market.outcome`, the data section | Scoring on your own price feed. The harness uses the venue's outcome when the data has it and counts the markets scored on a proxy instead. |
| Paper log | `python -m backtest_checks paper --log FILE` | A win rate read without the price. It prints the win rate, the average price, the break-even win rate with fees, and the gap to the backtest. |
| Resampling | `harness.bootstrap` | Noise inside the sample. It resamples the same markets, so it says nothing about other days. |

## Use it on your own data

Ticks go in a CSV file, one row per tick. `python -m backtest_checks synth --out ticks.csv`
writes the synthetic data in this format.

| Column | Meaning |
|---|---|
| `market_id` | window id, the same on every row of a window |
| `window_start`, `window_end`, `t` | Unix seconds, or ISO 8601 (no offset means UTC) |
| `start_price` | the price the window is measured against |
| `outcome` | `YES` or `NO` (`UP`, `DOWN` also work) as the venue resolved it; empty if unknown |
| `spot` | the reference price the strategy sees |
| `sigma` | volatility of log returns per second known at the tick; empty if unknown |
| `yes_bid`, `yes_ask`, `no_bid`, `no_ask` | best prices; empty if missing |
| `yes_ask_size`, `no_ask_size` | shares shown at the best asks; empty if unknown |

Then `python -m backtest_checks run --ticks ticks.csv` prints the same report for the naive
rule. `--window-sec`, `--margin` and `--size` set its parameters (defaults 10, 0.03 and 10: the
starting values of the project's first version, not tuned settings).

To check your own rule, write a function and pass it to the harness:

```python
from backtest_checks import controls, csvio, harness
from backtest_checks.friction import SCENARIOS
from backtest_checks.model import Trade

def my_rule(market, params):
    # Read market.ticks, market.start_price and market.end; never market.outcome.
    # Return a list of Trade(t=..., side="YES" or "NO", price=..., size=...).
    return []

markets = csvio.read_ticks_csv("ticks.csv")
print(controls.future_leak(my_rule, markets).ok)
for day, group in harness.by_day(markets).items():
    print(day, harness.run(my_rule, group, friction=SCENARIOS["realistic"]).pnl_per_share)
```

A paper log is a CSV with `ts, market_id, side, price, size, outcome` (outcome empty while the
market is open): `python -m backtest_checks paper --log paper.csv --fee-peak 0.018
--backtest-win-rate 0.85`.

No configuration file and no keys are needed.

## Limits

- Taker only. A trade fills at the best ask of its side on the fill tick. There is no queue and
  no market impact, and the depth cap is the only limit on size.
- The fee is `4 * peak * p * (1 - p)` per share, with `peak` the fee in dollars per share at a
  price of 0.50. The scenarios use the peak the project's log recorded for 5-minute crypto
  markets in April 2026 (0.018). The log called it "about 1.8% at 0.50"; whether that means
  1.8 cents per share or 1.8% of the price paid was not checked. Look up the current fee
  schedule before you rely on any of it.
- The scenarios are the project's guesses, not measurements. Fit friction to your own paper
  or live fills.
- The fair value is a zero-drift log-normal model with the sigma written on each tick. It is a
  baseline, not a pricing model.
- The lookahead check only sees the ticks. A leak through another input, such as a sigma
  computed over the whole day and written on every tick, passes it.
- When the venue's outcome is missing, a market is scored on the last tick's price against the
  start price. The venue may settle on another price source.

## Tests

`pytest -q` runs 47 tests in about a second, offline. They passed on Python 3.11 and 3.13.
The paper log in `tests/fixtures/` is synthetic and written by hand.

## Changes from the archived code

- Reads ticks from CSV or builds synthetic ones. The archived code read a SQLite database
  through an absolute local path.
- Scores on the venue's outcome when the data has it. The archived code always scored on the
  last exchange price against the start price.
- A trade fills on the last tick at or before its time. The archived code took the nearest
  tick, which could be a later one.
- The depth cap is optional. Before, every run with friction applied it, so a tick without a
  shown size could not fill.
- The inverted control works for any strategy, and the random control depends only on the seed
  and the market.
- New: the lookahead check, the per-day report, the paper-log summary, the share-weighted win
  rate and break-even columns, and `best_tick_in_hindsight` as a test case.
- Not included: strategy versions v1 to v6 and their settings, and the project's own data and
  logs.
