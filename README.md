# Prediction-market postmortems

Write-ups of prediction-market trading experiments that did not work: what was tested, how it
was measured, and why it stopped. Each case is a folder with the write-up and the part of its
code that is worth reusing. For developers who build on prediction-market APIs, and for anyone
who wants to see how a backtest that looked good failed against live data.

**Status: archived research.** The repository holds three cases. Each comes with reusable code
and offline tests: a read-only data collector, data audits with an evaluation harness, and a
backtest harness with a friction model and sanity controls. The live venue APIs were not checked
again for this release.

Built with AI coding agents (Claude, Codex).

## Cases

| Case | Question | Result | Reusable code |
|---|---|---|---|
| [Kalshi and Polymarket arbitrage on BTC 15-minute markets: what we measured and why it stopped](kalshi-polymarket-btc-15m/) (Feb to Jun 2026) | Does YES on one venue plus NO on the other lock in a profit on BTC 15-minute markets? | No. The venues settle on different prices, so both legs can lose. Fills were adversely selected, and passive orders had no room. | [Polymarket BTC 15-minute market collector](kalshi-polymarket-btc-15m/collector/) (Python, offline tests) |
| [64 days of Polymarket BTC up/down order books: the audits that caught our inflated numbers](polymarket-btc-updown-audits/) (Feb to Apr 2026) | When a 5-minute market closes pinned near 0 or 1, does the 15-minute market around it follow? | Not by enough to pay the fee. Much of the gain across 18 versions came from lookahead, a biased filter, a wrong outcome column, duplicated rows, missing fees and sizing fitted in-sample. | [Data audits and evaluation harness](polymarket-btc-updown-audits/harness/) (Python and DuckDB, offline tests) |
| [A 19x backtest meets a day-by-day split and 12 hours of paper trading](polymarket-btc-5m-backtest/) (Apr 2026) | Can a fair-value model find mispriced asks in the last seconds of a BTC 5-minute market? | No. The gain was fitted to one day, the backtest left out costs, and the paper bot won 67% of its trades at an average price of 0.70. | [Backtest checks: friction model, sanity controls, lookahead check, per-day split](polymarket-btc-5m-backtest/harness/) (Python, no dependencies, offline tests) |

## What the cases measured

Numbers from each case, as evidence of a mistake or of a mechanism. Each case folder has the
full table and its sources.

### Kalshi and Polymarket arbitrage on BTC 15-minute markets

| Check (2026) | Result |
|---|---|
| Do the two venues settle the same 15-minute window the same way? (May 26) | Not in 11.3% of episodes |
| Settlement disagreement by the size of the BTC move in the window (Jun 3) | 35% for moves under $5; 0.5% for moves of $60 or more |
| The same backtest on a proxy label and on the venues' real resolutions (May 26) | The proxy showed 7 to 8 times the gain |
| Fill-aware replay of 1,032 signals (Jun 10) | Signals that filled won about 52%; those that did not would have won about 67% |
| Median bid-ask spread on all four outcomes (May 28) | 1 cent |

### 64 days of Polymarket BTC up/down order books

| Check (2026) | Result |
|---|---|
| Hit rate with a filter on the 15-minute market's spread averaged over its whole life, against the spread known at entry | 97.9%, against about 75% |
| 5- and 15-minute windows that end at the same time: same outcome | 65.9% |
| Fees, read as 0.10 × p × (1 − p) per share per side, as a share of the gross walk-forward result of the best version at the time | 50.6% |
| A sizing rule fitted on the data before 5 April, applied to the rest, per day | Kept about half of its result; flat one-share trades held roughly level |

### A 19x backtest, a day-by-day split and 12 hours of paper trading

| Check (2026) | Result |
|---|---|
| Backtest score from the starting rule to v5, all tuned on the same 23 hours (Apr 21) | 19 times higher |
| v5 split by day (Apr 21) | Day 2 scored 3.5 times lower than day 1 |
| v5 with 1 cent of slippage, a depth cap and one tick of latency (Apr 21) | Day-2 mean about a tenth of day 1; some resamples lost money |
| Paper run of about 12 hours, 113 trades (Apr 21-22) | Won 67.3% at an average price of 0.70; the backtests had shown 80% to 90% |

## Quickstart

The code runs offline. From the repository root, this installs the three code folders, runs
their tests and prints the reports of the two harnesses on synthetic data:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e "kalshi-polymarket-btc-15m/collector[dev]" -e "polymarket-btc-updown-audits/harness[dev]" -e "polymarket-btc-5m-backtest/harness[dev]"
pytest -q kalshi-polymarket-btc-15m/collector polymarket-btc-updown-audits/harness polymarket-btc-5m-backtest/harness
python -m updown_audit demo
python -m backtest_checks demo
```

Each code folder's README covers its own use: the
[collector](kalshi-polymarket-btc-15m/collector/README.md) (an offline run with `--mock`, live
use, configuration), the [audits and evaluation harness](polymarket-btc-updown-audits/harness/README.md)
and the [backtest checks](polymarket-btc-5m-backtest/harness/README.md) (both: how to run them
on your own data).

## Lessons that repeat

1. Score on the venue's own resolution. A position settles on that venue's rule and price
   source: not on your own price feed, not on another venue's result, and not on "close above
   open" in your own data. In the first case a proxy label showed 7 to 8 times the gain of the
   same backtest scored on real resolutions. In the second, a position bought on a 5-minute
   market was scored on the 15-minute outcome, and the two agree only 65.9% of the time when
   they end together.
2. Put fees in the harness before the first result. Fees on these markets can depend on the
   price, differ by venue and market type, and change over time. A number computed without them
   is not a result. In the second case, fees took about half of the best version's gross
   result, and the plain rule's margin before fees was smaller than the fee.
3. Split by day first. Markets on the same day share the same price regime and news, so they
   are not independent samples. Hold out whole days, in time order, before any other analysis.
   In the third case, the best version scored 3.5 times lower on its second day than on its
   first.
4. A bootstrap over markets is not out-of-sample. Resampling single markets puts the same days
   on both sides of the test, so it measures noise inside the period you fitted, not how a rule
   does on days it has not seen. In the third case, v5 came out positive in all 64 resamples of
   the 23 hours it was tuned on; the paper bot lost money on the hours that followed.
5. Read the fill-aware ledger, not the research log. Research notes record what a test
   suggested. A fill-aware ledger records what filled, at what price, and how it settled. When
   they disagree, trust the ledger.
6. Model fills from real books. Assume you get the price that was there when the signal fired
   only after a live dry run shows it. In the first case, signals that filled won about 52% and
   signals that did not would have won about 67%.

## How to read the numbers

Numbers appear only as evidence of a mistake or of a measured mechanism: lookahead, selection
bias, fees, fills, in-sample sizing. There are no profit totals, balances or tuned settings.
Nothing here is a trading recommendation.

## Limits

- The numbers come from notes and logs written during each project. Raw data is not included,
  and the venues' data terms were not checked.
- Venue rules, fees and APIs change. Check them before you reuse any code from here.
- Each case describes one project in one period. It is not proof that a whole class of
  strategies fails.

## License

MIT, see [LICENSE](LICENSE).
