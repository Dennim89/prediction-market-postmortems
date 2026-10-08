# Kalshi and Polymarket arbitrage on BTC 15-minute markets: what we measured and why it stopped

From February to June 2026 we built a bot for the Bitcoin 15-minute "up or down" markets on
Kalshi and Polymarket. The plan was to trade price gaps between the two venues. Backtests
looked good several times. In the cases we checked, the edge shrank or disappeared once
positions were scored on each venue's own settlement, or once fills were modelled on what
really filled. We stopped in June 2026.

**Status: archived.** The trading code is not published. This folder holds the write-up and a
read-only Polymarket data collector with offline tests: [collector/](collector/).

Built with AI coding agents (Claude, Codex).

## The question

Both venues list a market for every 15-minute window: will BTC end the window above where it
started? A YES share pays $1 if it does and a NO share pays $1 if it does not. On paper, YES on
one venue plus NO on the other pays exactly $1 whatever BTC does. If the pair costs less than $1
after fees, the gap looks like a locked-in profit.

Can a small bot collect that gap? And when it could not, was there any other price relation
between the two venues that could be traded?

## Setup

- Period: February to June 2026.
- Markets: the BTC 15-minute Up/Down markets on Kalshi and on Polymarket.
- Settlement, as we understood the rules at the time: Kalshi settles on a 60-second average of
  a BTC index, Polymarket on a Chainlink BTC/USD price. Each venue fixes its own start price for
  the window, so the two start prices can differ.
- Data: our own collectors recorded both venues' order books and the BTC reference prices.
- Code: a Go bot with order and WebSocket clients for both venues, Python collectors, about 20
  backtest and grid scripts, a walk-forward harness, paper traders and live dry runs. Several of
  the checks below were run as reviews by groups of AI agents.

What we tried:

1. A two-leg spread. Buy YES on one venue and NO on the other when the pair costs less than $1
   after fees. Build the position in the first minutes of the window, exit through the spread,
   and rebalance when only one leg fills. Entries were filtered by G, the gap between the two
   venues' start prices.
2. Oracle lag. When BTC moves, the two settlement prices catch up at different speeds. Bet one
   side on the slower venue.
3. Passive entries: rest limit orders instead of paying the spread.
4. A side experiment outside BTC: a sports and esports monitor that ordered on Kalshi first
   (immediate-or-cancel) and then on Polymarket (fill-or-kill), with a paper trader.

## What we measured

All dates are 2026. The numbers come from our notes and logs written at the time.

| Date | Check | Result |
|---|---|---|
| Mar 25 | First live session, audited against the venue's fill history | 19 fills we did not intend, next to 42 we did. A pre-signing step left resting orders on the book, and market makers filled them. |
| Apr 12-13 | First live run of the sports monitor, Kalshi side | 1 win in 7 trades, against 62% in its backtest. We traced the gap to bugs in the cooldown and in match-clock parsing. |
| May 26 | Do the two venues settle the same window the same way? | Not in 11.3% of episodes. |
| May 26 | One backtest, scored two ways | On a proxy label (BTC close above open, from our own price data) it showed 7 to 8 times the gain it showed on the venues' real resolutions. |
| May 28 | Bid-ask spread on both outcomes of both venues | Median 1 cent on all four, over 1.1M to 1.3M ticks each. |
| May 28 | Funnel on a live day: raw signals, backtest picks, live picks | The backtest re-implemented the bot and skipped about a dozen of its live filters. It described a strategy that never ran. |
| May 29 | Detector latency | Median 0.16 ms, against an effect that lasted 8 to 14 seconds. |
| Jun 1 | Quote freshness | Quotes from the order-book service our paper traders read lagged the exchange, so paper results built on them could not be trusted. A replay on the exchange's own price history looked fine, which moved the question to fills. |
| Jun 3 | Settlement disagreement against the size of the BTC move in the window | 35% of episodes when BTC moved less than $5; 0.5% when it moved $60 or more. |
| Jun 3 | Sweep of 12 angles on the two-venue structure, split across 13 AI agents | No simple edge. |
| Jun 10 | Fill-aware replay of 1,032 oracle-lag signals from April and May | Signals that filled won about 52%. Signals that did not fill would have won about 67%. The haircut, about 6 cents a share, did not shrink when simulated latency went from 0 to 3 seconds. |
| Jun 12 | Passive-order simulation, re-scored on Polymarket's own settlement | Positive before the re-score, negative after it. Its "passive" fills had in fact crossed the spread. |

## Result

No edge survived both tests: settlement on each venue's own terms, and realistic fills. One thin
effect on the NO side survived several checks and then fell below the cost of execution. The
last version of the oracle-lag strategy ran only as a dry run: 259 signals, 0 real orders.

## Why it stopped

It was not an arbitrage. YES on one venue plus NO on the other pays $1 only if both venues
settle the window the same way. They settle on different prices: a single Chainlink price on
Polymarket, a 60-second average on Kalshi, each against its own start price. When BTC ends close
to the start, the two can land on opposite sides, and then both legs lose (or both win). That is
where the disagreement sat: 35% of episodes with a move under $5, 0.5% with a move of $60 or
more. It shows up only after settlement.

An example with made-up numbers. Polymarket's window starts at 100,000 and Kalshi's at 99,998.
We hold Polymarket YES and Kalshi NO. Polymarket's closing price is 99,999, below its start, so
YES loses. Kalshi's 60-second average is 100,001, above its start, so NO loses as well. The pair
that "could not lose" pays nothing.

Fills were adversely selected. When a signal was right, the price moved away before our
order filled. When it was wrong, the order filled. In the April-May replay, signals that filled
won about 52% and those that did not would have won about 67%. Being faster did not help: the
haircut stayed near 6 cents a share from 0 to 3 seconds of simulated latency.

Passive orders had no room. With a median spread of 1 cent on every side, a resting order
cannot improve the price by much. The one passive simulation that looked positive had scored
Polymarket positions on a label that did not match Polymarket's settlement, and its "passive"
fills had crossed the spread.

Speed was not the limit. The detector reacted in 0.16 ms at the median, and the effect it
chased lasted 8 to 14 seconds.

By June nothing simple was left. The 12-angle sweep found no simple edge, and the one thin
NO-side effect did not cover execution costs.

## What we would do differently

- Score every position on the venue's own resolution from the first backtest. A proxy label
  inflated one backtest 7 to 8 times, and a label that did not match Polymarket's settlement
  made a losing passive-order test look positive.
- Keep one signal function and import it in both the bot and the backtest. Then compare funnel
  counts on a live day: raw signals, backtest picks, live picks. If two of them differ by more
  than 2x, the backtest is wrong.
- Before any real order, run a live dry run that logs the real ask and depth at signal time,
  and model fills from those logs, not from the last quote.
- Store the exchange's timestamp with every quote and check quote age before trusting a
  collector.
- Give every long-running process a watchdog, and let resolvers discover their input files. A
  detector died silently for three days; a resolver with a hard-coded file list skipped newer
  bots.
- Audit the first live session against the venue's own fill history. That is how the 19 stray
  fills were found.

## Map of the code

The original project had about 52,000 lines of Go and Python. Only the collector is published.

| Part | What it did | In this repository |
|---|---|---|
| Polymarket collector (Python) | Finds the current window, polls both order books, follows the Chainlink BTC/USD stream, writes raw JSONL and tick CSV | Yes: [collector/](collector/), cleaned up and tested offline. Its README lists the changes. |
| Go bot, root package (about 17,000 lines) | Two-leg entries, rebalancing, exits, pre-expiry logic, simulation | No. It does not compile in our archive (three functions live in files that are not there), and it holds tuned settings. |
| Kalshi client (Go) | RSA-PSS request signing, orders, WebSocket | No. It depends on the bot's package-level state. A tested Kalshi signing client may be published separately; this repository will link to it instead of keeping a second copy. |
| Polymarket order clients (Go, Python) | Order placement and wrappers | No. They place real orders with keys, and the older Python wrappers target Polymarket's V1 order API, which Polymarket planned to replace on 2026-04-28. |
| Fee and effective-price math | Cost of each leg after fees | No. The formulas were corrected during the project and were not checked against the venues' current fee schedules. |
| Index approximation (`brti_approx.go`) | Approximates Kalshi's settlement index from public exchange feeds | No. It approximates a licensed index, and it is niche. |
| Analyzer (Python) | Episode builder and walk-forward fit of a two-parameter entry rule | No. Its defaults are tuned settings, and it valued open positions at the last tick's bids instead of at each venue's settlement. |
| Sports monitor (Go) | Cross-venue monitor with a paper trader and alerts | No. It is tied to our alerting setup and saved position state, and it does not build in our archive. |
| Research scripts | About 20 backtest, grid and optimizer scripts, early pattern hunts, scratch files | No. They hold tuned settings and results. |
| Server helpers | Deployment and file transfer | No. Specific to our own servers. |

## Limits of this write-up

- The numbers come from notes and logs written during the project. The raw data and the scripts
  that produced the numbers are not in this repository, and we did not re-run them for this
  write-up.
- Venue rules, fees and APIs change. Nothing here was checked again after June 2026.
- This is one project on two venues over five months. It does not show that every cross-venue
  strategy on prediction markets fails.
