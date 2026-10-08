# Prediction-market postmortems

Write-ups of prediction-market trading experiments that did not work: what was tested, how it
was measured, and why it stopped. Each case is a folder with the write-up and the part of its
code that is worth reusing. For developers who build on prediction-market APIs, and for anyone
who wants to see how a backtest that looked good failed against live data.

**Status: archived research.** The repository holds one case. Its reusable code, a read-only
data collector, has offline tests. The live venue APIs were not checked again for this release.

Built with AI coding agents (Claude, Codex).

## Cases

| Case | Question | Result | Reusable code |
|---|---|---|---|
| [Kalshi and Polymarket arbitrage on BTC 15-minute markets: what we measured and why it stopped](kalshi-polymarket-btc-15m/) (Feb to Jun 2026) | Does YES on one venue plus NO on the other lock in a profit on BTC 15-minute markets? | No. The venues settle on different prices, so both legs can lose. Fills were adversely selected, and passive orders had no room. | [Polymarket BTC 15-minute market collector](kalshi-polymarket-btc-15m/collector/) (Python, offline tests) |

## What the first case measured

| Check (2026) | Result |
|---|---|
| Do the two venues settle the same 15-minute window the same way? (May 26) | Not in 11.3% of episodes |
| Settlement disagreement by the size of the BTC move in the window (Jun 3) | 35% for moves under $5; 0.5% for moves of $60 or more |
| The same backtest on a proxy label and on the venues' real resolutions (May 26) | The proxy showed 7 to 8 times the gain |
| Fill-aware replay of 1,032 signals (Jun 10) | Signals that filled won about 52%; those that did not would have won about 67% |
| Median bid-ask spread on all four outcomes (May 28) | 1 cent |

## Quickstart

The code runs offline. From the repository root:

```bash
cd kalshi-polymarket-btc-15m/collector
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
python -m collector run --mock --duration-sec 15
```

The last command writes synthetic raw events and tick rows under `./data`. The
[collector README](kalshi-polymarket-btc-15m/collector/README.md) covers live use and
configuration.

## Lessons that repeat

1. Score on the venue's own resolution. A position settles on that venue's rule and price
   source: not on your own price feed, not on another venue's result, and not on "close above
   open" in your own data. In the first case a proxy label showed 7 to 8 times the gain of the
   same backtest scored on real resolutions.
2. Put fees in the harness before the first result. Fees on these markets can depend on the
   price, differ by venue and market type, and change over time. A number computed without them
   is not a result.
3. Split by day first. Markets on the same day share the same price regime and news, so they
   are not independent samples. Hold out whole days, in time order, before any other analysis.
4. A bootstrap over markets is not out-of-sample. Resampling single markets puts the same days
   on both sides of the test, so it measures noise inside the period you fitted, not how a rule
   does on days it has not seen.
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
