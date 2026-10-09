# 64 days of Polymarket BTC up/down order books: the audits that caught our inflated numbers

In April 2026 we used 64 days of archived Polymarket order books to test one idea on the
Bitcoin up/down markets: when a 5-minute market closes pinned near 0 or 1, does the 15-minute
market around it follow? AI agents turned the idea into 18 strategy versions, and most new
versions looked better than the one before. Audits then showed that much of the gain came from
errors: lookahead, a filter that picked winners after the fact, a position scored on the wrong
market, duplicated rows, fees left out, and position sizes fitted to the windows they were
scored on. The plain rule did not cover the fee. We stopped working on these markets in May
2026.

**Status: archived.** The strategy versions and the data are not published. This folder holds
the write-up and the audits and evaluation harness, rewritten and tested offline on synthetic
data: [harness/](harness/).

Built with AI coding agents (Claude, Codex).

## The question

Polymarket lists Bitcoin up/down markets for 5-minute, 15-minute and 1-hour windows. Each
market pays $1 per share on the side that wins: Up if BTC ends the window above its start
price, Down otherwise. A 15-minute window contains three 5-minute windows. When the first
5-minute market of a 15-minute window closes pinned near 1 (or near 0), the 15-minute market
still has 10 minutes to run.

Does the pinned price tell you something the 15-minute price has not taken in yet? Can a taker
buy the 15-minute market on the same side, hold it to expiry and make money after fees?

## Setup

- Period: 21 February to 25 April 2026, 64 days.
- Data: order-book snapshots of Polymarket's BTC markets from a public third-party archive,
  reduced to one row per market and second with the best bid and ask of both outcomes. 33,060
  markets (5-minute, 15-minute and 1-hour, the 1-hour ones including multi-strike markets) and
  about 26 million rows. Outcomes from Polymarket's market data. Binance BTC/USDT 1-minute
  candles for the label checks. The data, about 280 MB, is not included, and we did not check
  the archive's terms.
- The rule: 5 seconds before a 5-minute market closes, if its mid price is pinned near 1 (or
  near 0), buy Up (or Down) at the ask on the 15-minute market that contains it, and hold to
  expiry.
- Process: 8 explore agents, 5 refine agents, review agents and later autonomous agent sessions
  produced versions v1 to v18. They added filters, a stop-loss, extra legs, and sizing by the
  BTC move, volatility and hour.
- Evaluation: resampling with seeds, a time split at 14 April, and 8 walk-forward windows of 14
  days. Fees came in on 27 April.

## What the audits found

The numbers come from the project's research log and review reports, written in April 2026.

| Error | How it looked | What the audit found |
|---|---|---|
| Lookahead | "Vote" and "all three agree" variants hit close to 100%, on the held-out part too. | They used the closes of the later 5-minute markets in the window, which come after the entry. Without them, a first 5-minute market pinned near 1 was followed by an Up 15-minute window 75% of the time. |
| Selection bias | A filter on the 15-minute market's average spread raised the hit rate to 97.9%. | The spread was averaged over the market's whole life, the minutes after the entry included. Markets that settled early near 0 or 1 had tiny spreads, so the filter kept markets that were already decided. Without the filter the same rule lost money; with the spread known at the entry it hit about 75%. |
| Wrong outcome column | A "cheaper venue" trick added to the result: when a 5-minute and a 15-minute market end together, buy whichever is cheaper. | It bought the 5-minute market but scored it on the 15-minute outcome. Windows that end together had the same outcome only 65.9% of the time. The trick inflated the result by about 4%. |
| Duplicated rows | An extra leg on the 1-hour market looked like a small gain. | A LEFT JOIN had duplicated rows. On clean rows the extra leg lost money. |
| Fees found late | Every result until 27 April was before fees. | The order book's fee fields, read as 0.10 × p × (1 − p) per share per side, took 50.6% of the gross walk-forward result of the best version at the time. A stop-loss exit pays the fee twice, so after fees, holding to expiry beat the stop-loss for the sized versions. |
| Sizing fitted in-sample | The sized versions were "positive in all 8 walk-forward windows". | Size multipliers of up to about 24 times were fitted on those same windows. A sizing rule fitted on the data before 5 April and applied to the rest kept about half of its result per day, while flat one-share trades held roughly level. |
| Reviews by reading | Review agents ranked the strategies. | The sandbox stopped them from running code, so they audited by reading code and result files. One round's first pick still relied on the biased spread filter. |

Checks that passed:

- Polymarket's 15-minute outcomes agreed with Binance 1-minute candles, close against close,
  97.79% of the time, so the outcome column could be trusted.
- The start time in the market data was the time a market was created, about a day before its
  window. Window starts were taken from the end time instead.
- The outcomes were split close to 50/50, crossed books were rare, and the data had no gaps from
  21 February to 25 April (some days were sparse).

Found while preparing this write-up:

- The BTC move and volatility inputs behind the sizing and the later filters were read from
  the 1-minute candle that closes when the 5-minute market ends: 5 seconds after the entry.
- The evaluation's resampling used Python's built-in `hash()`, which changes from one process to
  the next, so the seeds drew different trades on every run. Full-sample results were not
  affected.
- The 15-minute prices were taken from a row stamped exactly 5 seconds before the 5-minute
  close. The 1-second table had rows only for seconds with book events, so windows without an
  update in that second were left out. The effect is unknown.

## Result

Nothing we would trade. The plain rule on the first 5-minute market of each window, with no
filters and one share a trade, won 74.4% of 2,592 trades at an average price of 0.74: about 0.6
cents a share before fees. At that price the fee, as the project read it, was about 1.9 cents a
share. The later versions got their numbers from filters and sizing chosen on the same data,
and the strongest of them from the errors above.

## Why it stopped

There is no stop note in the project. Our notes from May and June 2026 give the reasons:

- A paper bot on a server ran logic like v12 in April. Our notes do not show a later version on
  it, and whether this signal was ever tested with real fills is unknown.
- By May, after this and other tests, we classed Polymarket's 5- and 15-minute crypto markets as
  efficient for a taker without HFT-grade speed.
- Other backtests from the same months turned out wrong too: labels from the wrong price
  source, and a backtest that skipped the live bot's filters. See the
  [Kalshi and Polymarket case](../kalshi-polymarket-btc-15m/).
- In June, a fill-aware replay of related signals showed adverse selection: the signals that
  filled were more often the losing ones.

The project's own checklist still listed latency simulation and a size cap by book depth as
open.

## What we would do differently

- Score every position on the outcome of the market it was bought in, as the venue resolved it.
- Put fees in the harness before the first result.
- Give every input the time it became known, and reject any input known after the entry. That
  one rule catches the vote variants, the lifetime spread filter and the 5-second candle.
- Check row counts and unique keys after every join.
- Fix the time split before looking at results, fit sizing on the earlier part only, and compare
  periods per day, not by their totals.
- Use one evaluation function for the backtest and the live bot, model fills from real books
  (adverse selection included), and cap sizes by depth.
- Let reviewers run code.

## Map of the code

The original project had 92 Python files, about 14,800 lines. 20 of them sit in `agents/`, a
folder of 90 files of agent output.

| Part | What it did | In this repository |
|---|---|---|
| `audit_resolutions.py`, `data_audit.py` | Outcomes against Binance candles under four candle alignments; winner split; agreement of windows that end together; crossed books; calibration; coverage | Yes, rewritten as functions over three documented tables, with tests: [harness/](harness/). |
| `audit_random_sample.py`, `audit_polymarket_live.py` | Spot checks of 30 markets against Binance and Coinbase candles and Polymarket's API | No. They call third-party APIs through a helper that bypasses local DNS. The label check accepts any candle table, so a second source can be checked the same way. |
| `eval_v2.py` | Fee model, hold or stop-loss exit, time split, resampling | Yes, rewritten. The fee rate and the split are arguments, resampling is reproducible, and results are per share and per day. The v12 and v13 sizing functions are not included. |
| `strategies/common.py`, `strategies/baseline_crosstf.py` | Signal table for the 5- and 15-minute pairs | Rewritten as one example rule, with the pin threshold as an argument and the time each input became known. |
| `strategies/best_v*` (16 files), 38 experiment scripts, `runner.py`, `eval.py` and other scripts | Versions v1 to v18, sweeps and sizing | No. They hold tuned settings and sizing rules. |
| `agents/` | Scripts, results and reports of the explore, refine and review agents | No. Their findings are summarised above. |
| `scripts/` | Market metadata from Polymarket's API, download and filtering of the archive's files, the 1-second join, Binance candles | No. They download from the third-party archive, and one helper bypasses local DNS. The [harness README](harness/README.md) describes the tables to build instead. |
| `eda/`, `REPORT.md`, `LEARNINGS.md`, `backtests/` | Coverage, calibration tables, research log, baseline results | No. The numbers above come from them. |

## Limits of this write-up

- The numbers come from logs and review reports written in April 2026. The data is not
  included and we did not run the analyses again.
- The fee and settlement facts are as the project read them at the time.
- One venue, one asset and 64 days. This shows how one piece of research went wrong, not that
  every strategy on these markets fails.
