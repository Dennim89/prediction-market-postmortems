# A 19x backtest meets a day-by-day split and 12 hours of paper trading

In April 2026 an AI coding agent spent two sessions on one idea for Polymarket's 5-minute
Bitcoin up/down markets: in the last seconds of a window, compare each side's ask with a fair
value computed from the BTC price, and buy the side that looks cheap. In the first session the
backtest score grew 19 times. In the second, a split by day showed that most of the gain came
from the first day, and simple execution costs and a fee the backtest had left out cut the
second day further. A re-tuned version won the numbers back on the same data. Then a paper bot
ran for about 12 hours. It won 67% of its trades at an average price of 0.70, not enough to
cover the price paid, while the backtests had shown 80% to 90%. We dropped the idea.

**Status: archived.** The strategy versions are not published. This folder holds the
write-up and a small backtest harness with a friction model, sanity controls, a lookahead
check and a per-day split, tested offline on synthetic ticks: [harness/](harness/).

Built with AI coding agents (Claude, Codex).

## The question

A 5-minute up/down market pays $1 per Up share if BTC ends the window at or above its start
price, and $1 per Down share otherwise. Near the end of the window the outcome depends on two
things: how far BTC is from the start price, and how much it can still move. A simple model
turns that into a probability:

P(Up) = Φ( ln(S / S0) / (σ √t) )

where S is the BTC price now, S0 the start price, σ the volatility per second and t the
seconds left. If one side's ask is well below the model's probability for that side, buy it.
Does that make money?

## Setup

- Period: 20 to 22 April 2026.
- Markets: Polymarket's 5-minute BTC up/down markets.
- Data: one-second ticks from our own collector on one server: the Binance BTC price, the best
  bid and ask with sizes on both outcomes, and order-flow features. Session 1 used 23 hours (275
  markets, about 80,000 ticks). Session 2 used 25 hours (307 markets): the same data plus 2.6
  hours.
- Backtest: taker only. A trade filled at the ask of the tick that triggered it and was held to
  expiry. The outcome came from the last Binance price against the start price. Results were
  averaged over 32 to 64 resamples of the markets.
- Controls: do nothing, buy a random side, buy the cheaper side, and the strategy inverted.
- Process: an AI coding agent ran both sessions from a short brief. In the first it tested 22
  hypotheses and stacked the ones that raised the score into versions v1 to v5.
- Paper run: a bot traded on paper on live data from 21 April 18:18 to 22 April 06:23 UTC.

## What we measured

All dates are 2026. The numbers come from the project's logs, and the paper-run figures were
counted again from the paper log for this write-up.

| Date | Check | Result |
|---|---|---|
| Apr 21 | Controls on the starting rule (v0) | Passed. The inverted copy lost, the cheaper side lost and the random side ended near zero. The inverted copy won 79% of its trades and still lost money: it bought the expensive side. |
| Apr 21 | Session 1: v0 to v5, filters and a position size that grew with the model's edge, all chosen on the same 23 hours | Backtest score up 19 times. The largest single step was the sizing. |
| Apr 21 | Session 2: the same versions, split by day | v5 scored 3.5 times lower on day 2 than on day 1. The sizing step (v2) kept about 1% of its day-1 result, and v0 lost money on day 2. Both days were inside the session-1 data, except the last 2.6 hours. |
| Apr 21 | v5 with 1 cent of slippage, at most 30% of the shown ask size, and a fill one tick late | The day-2 mean fell to about a tenth of day 1. Some resamples lost money. |
| Apr 21 | Fee and settlement rules, from a web search by a second agent | The backtest had no fee. The log recorded a taker fee on 5-minute crypto markets since February 2026, highest at a price of 0.50 (about 1.8% in the log's words) and near zero at the extremes. It also recorded that Polymarket settles these markets on Chainlink Data Streams, not on Binance, and that ties resolve Up. About 7% of the markets ended within $5 of the start price, where the two sources can disagree. |
| Apr 21 | v6: a wider entry window and new thresholds, searched on the same 25 hours with the friction model | The numbers recovered. They were in-sample again. |
| Apr 21-22 | Paper run, about 12 hours | 113 resolved trades. Won 67.3% at an average price of 0.70; a share bought at 0.70 needs a 70% win rate to break even before fees. The run lost money before fees. The backtests had shown 80% to 90%. The log does not record which version ran. |

Found while preparing this write-up: from v5 on, the strategy scanned every tick in its entry
window and traded at the one with the largest edge. A live bot cannot do that: at any tick it
does not know whether a later tick will offer more. The paper bot took 90 of its 114 entries
within the first 10 seconds of its window, which is what a bot that takes the first tick that
qualifies does. How much this choice inflated the backtests is unknown: the tick database is
not included. The [harness](harness/) has a check that flags it.

## Result

The edge did not hold. The 19 times came from choices fitted to the same hours, most of it from
one day. Costs the backtest had left out took much of what remained. On new hours of live data
the paper bot lost money before fees.

## Why it stopped

The paper run missed the backtest's win rate by 14 to 23 points and lost money before fees.
In May 2026, after this and other tests, we classed Polymarket's 5- and 15-minute crypto
markets as efficient for a trader without HFT-grade speed and stopped working on them. The
log's own caveats (one to two days of data, guessed friction, Binance prices instead of the
settlement source) were reasons to doubt the backtest from the start.

## What we would do differently

- Split by day before anything else, and keep whole days out of every search. Here the 19
  times came mostly from day 1, and most of "day 2" had been searched too.
- Run the controls first, and read them for what they are. They show that the evaluation is
  consistent, not that an edge will last. Here they passed.
- Do not read resamples of the same hours as a forecast. They say nothing about the next day.
- Put the venue's fee and settlement rule into the first backtest, and score on the venue's
  own outcome.
- Fit friction to observed fills, not guesses, and start paper trading early. Twelve hours of
  paper trading said more than two days of backtests.
- Compare the win rate with the break-even rate (the average price paid plus fees), not with
  50%.
- Check that every decision uses only data up to its own time.
- Size by edge only after the edge holds on days the search has not seen. Sizing multiplies
  whatever is in the sample, noise included.

## Map of the code

The original project had 27 Python files (about 2,400 lines), three Markdown logs and two CSV
logs.

| Part | What it did | In this repository |
|---|---|---|
| `lib.py` | SQLite tick loader and the log-normal fair value | The fair value: yes, in [harness/](harness/). The loader is replaced by a CSV reader and a synthetic tick generator; the database is not included. |
| `eval.py` | Taker backtest and resampling of markets | Yes, rewritten. It scores on the venue's outcome when the data has it, and counts the markets it scores on a proxy. |
| `friction.py` | Fee curve, slippage, depth cap, latency, settlement noise, tie rule | Yes, with the log's scenarios as presets. |
| `sanity_checks.py` | Do nothing, random side, cheaper side, inverted | Yes, generalised so the inversion works for any strategy. New: the lookahead check. |
| `temporal_cv.py` | Backtest per day | Yes, as the per-day report. |
| `strategy_v0_naive.py` | The untuned starting rule | Yes, with its starting values. |
| `debug_live_vs_bt.py` | Paper log against the backtest | The summary part (win rate, average price, break-even, gap) as `paper.py`. |
| `strategy_v1.py` to `strategy_v6.py`, `strategies_v1_stack.py`, seven `strategy_H*` files, scratch, sweep and analysis scripts | Tuned versions and hypothesis tests | No. They hold tuned settings. The best-tick choice of v5 and v6 appears without their settings, as a test case for the lookahead check. |
| `paper_live.csv`, `shadow_v4_today.csv` | Our paper and shadow trading logs | No. The tests use a synthetic sample. |
| `LEARNINGS.md`, `SESSION_SUMMARY.md`, `SESSION2_SUMMARY.md` | The research log | No. The numbers above come from them. |

## Limits of this write-up

- The numbers come from logs written in April 2026 and from the paper log. The tick database
  is not included, so the backtests could not be run again.
- The fee and settlement facts are as the log recorded them in April 2026. We did not check them
  again.
- Two days of data and one 12-hour paper run are small samples. They show that this backtest
  was wrong, not that every strategy on these markets fails.
