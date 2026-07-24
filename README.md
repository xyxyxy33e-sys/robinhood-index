# robinhood-index — 0DTE Index Options Day Strategy

An agent-operated intraday strategy that trades same-day-expiration (0DTE) options
on index ETFs — **SPY, QQQ, IWM** — through the Robinhood agentic account.

> **Note on IWB:** IWB (iShares Russell 1000) does not list daily expirations, so it
> cannot be traded 0DTE. IWM (Russell 2000) is used as the small/mid-cap leg instead.
> Edit `config/strategy.yaml` to change the universe.

## Daily lifecycle (all times US/Eastern)

| Time | Action |
|---|---|
| 9:00 | Scheduled session starts; begins tracking market sentiment minute-by-minute (pre-market bars, overnight gap, news) |
| 9:30 | Market opens; session watches the opening drive (no entries yet — first 15 min is noise) |
| 9:45–11:30 | Entry window: if the composite sentiment score crosses the threshold, buy a 0DTE call (bullish) or put (bearish) on the strongest/weakest index |
| immediately after fill | Resting stop-limit order placed at ~30% below entry (the stop-loss the strategy is built around) |
| every ~10 min | Monitor positions: take-profit check, stop verification, re-entry evaluation |
| 12:45–13:00 | **Hard close**: cancel resting orders, close all positions with marketable limits, verify flat |
| 13:10 | Independent failsafe session double-checks the account is flat and force-closes anything left |

## Repository layout

- `docs/STRATEGY.md` — full strategy specification: signal construction, entry/exit rules, risk limits, rationale
- `docs/PLAYBOOK.md` — the step-by-step runbook the scheduled agent session executes each morning (tool-by-tool)
- `config/strategy.yaml` — all tunable parameters (mode, sizing, thresholds, times)
- `scripts/strategy_calc.py` — deterministic math: sentiment scoring, position sizing, stop/target prices
- `logs/journal/` — one committed journal file per trading day (signals, decisions, orders, P&L)
- `data/` — intraday scratch data (gitignored)

## Safety model

1. **`mode: dry_run` is the default.** In dry-run the session does everything —
   sentiment, signals, contract selection, sizing — and journals the trades it *would*
   have placed, but never places an order. Flip to `mode: live` in
   `config/strategy.yaml` to trade real money.
2. Setting `mode: live` is your standing authorization for scheduled sessions to place
   orders **within the limits in `config/strategy.yaml`** without per-order
   confirmation. Review the `risk:` block before flipping it.
3. Hard limits enforced by the playbook: max premium per trade, max trades per day,
   daily loss halt, no entries after 11:30 ET, everything flat by 13:00 ET.
4. Cash account discipline: trades are funded only from start-of-day settled cash and
   same-day sale proceeds are never re-used (avoids good-faith violations).

## Scheduling

Two Claude Code routines drive the strategy (created via the Claude Code Remote
trigger system; cron is evaluated in **UTC**):

| Routine | Cron (UTC) | ET (EDT) | Purpose |
|---|---|---|---|
| `0dte-morning-session` | `0 13 * * 1-5` | 9:00 weekdays | Runs `docs/PLAYBOOK.md` end-to-end |
| `0dte-failsafe-closeout` | `10 17 * * 1-5` | 13:10 weekdays | Verifies flat; force-closes stragglers |

⚠️ **DST:** these crons assume Eastern Daylight Time (UTC-4). When clocks fall back
(early November), shift both crons +1 hour (`0 14 …` and `10 18 …`) or the session
will start at 8:00 ET.

## Account

- Trading account: Robinhood "Agentic" cash account ••••1551 (agentic-enabled, Options Level 2)
- Capabilities: long calls and long puts, single-leg only (the agentic API does not support spreads)

## Risk disclaimer

0DTE long options are among the highest-risk instruments retail traders can buy: theta
decay is brutal, and a 100% loss of premium on any given trade is a normal outcome.
The 30% stop-loss bounds per-trade damage but gaps/slippage can exceed it. Only fund
this strategy with money you can afford to lose entirely.
