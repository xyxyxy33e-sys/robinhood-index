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
| 9:45–11:30 | Entry window: every index whose sentiment score clears the threshold gets a 0DTE call (bullish) or put (bearish) — up to 3 concurrent positions, mixed directions allowed, ≤ $1,000 premium each |
| immediately after each fill | Resting stop-**market** order placed at −28% of fill (the stop-loss the strategy is built around) |
| every minute (positions open) | Monitor positions: take-profit check, stop verification, re-entry evaluation |
| 13:00–13:30 | **Hard close**: cancel resting orders, close all positions with marketable limits, verify flat |
| 13:31 | Independent failsafe session double-checks the account is flat and force-closes anything left |

## Repository layout

- `docs/STRATEGY.md` — full strategy specification: signal construction, entry/exit rules, risk limits, rationale
- `docs/PLAYBOOK.md` — the step-by-step runbook the scheduled agent session executes each morning (tool-by-tool)
- `config/strategy.yaml` — all tunable parameters (mode, sizing, thresholds, times)
- `scripts/strategy_calc.py` — deterministic math: sentiment scoring, position sizing, stop/target prices
- `logs/journal/` — one committed journal file per trading day (signals, decisions, orders, P&L)
- `data/` — intraday scratch data (gitignored)

## Safety model

1. **`mode` in `config/strategy.yaml` governs everything. It is currently `live`.**
   In `dry_run` the session does everything — sentiment, signals, contract selection,
   sizing — and journals the trades it *would* have placed, but never places an order.
   Set it back to `dry_run` to stop trading real money.
2. Setting `mode: live` is your standing authorization for scheduled sessions to place
   orders **within the limits in `config/strategy.yaml`** without per-order
   confirmation. Review the `risk:` block before flipping it.
3. Hard limits enforced by the playbook: max premium per trade, max trades per day,
   daily loss halt, no entries after 11:30 ET, everything flat by 13:30 ET.
4. Cash account discipline: trades are funded only from start-of-day settled cash and
   same-day sale proceeds are never re-used (avoids good-faith violations).

## Scheduling

Two Claude Code routines drive the strategy (created via the Claude Code Remote
trigger system; cron is evaluated in **UTC**):

| Routine | ID | Cron (UTC) | ET (EDT) | Purpose |
|---|---|---|---|---|
| `0dte-morning-session` | `trig_0113xQ7waSQKDmJU9QyHqoUC` | `0 13 * * 1-5` | 9:00 weekdays | Runs `docs/PLAYBOOK.md` end-to-end |
| `0dte-failsafe-closeout` | `trig_01RoDZSx6HvoxA7RdpRCsjiG` | `31 17 * * 1-5` | 13:31 weekdays | Verifies flat; force-closes stragglers |

Both routines fire into the persistent session that created them
(`session_01LYbUn21tPxhdDr2LoioESx`) because that session holds the Robinhood MCP
connector — fresh-session routines created via the API run without connectors and
cannot trade. If that session is ever deleted or loses its connector, recreate the
routines from the claude.ai routines UI with the Robinhood connector attached.

**Model policy (owner requirement): runs must use Claude Sonnet 5, not Fable 5.**
Routine fires execute on the bound session's model, so the session above must be
set to Sonnet 5 in the claude.ai model picker (API-side routine model updates are
disabled: `model_update_disabled`). If the routines are ever recreated in the
routines UI, select Sonnet 5 there.

⚠️ **DST:** these crons assume Eastern Daylight Time (UTC-4). When clocks fall back
(early November), shift both crons +1 hour (`0 14 …` and `31 18 …`) or the session
will start at 8:00 ET.

## Account

- Trading account: Robinhood "Agentic" cash account ••••1551 (agentic-enabled, Options Level 2)
- Capabilities: long calls and long puts, single-leg only (the agentic API does not support spreads)

## Risk disclaimer

0DTE long options are among the highest-risk instruments retail traders can buy: theta
decay is brutal, and a 100% loss of premium on any given trade is a normal outcome.
The 30% stop-loss bounds per-trade damage but, being a market order once triggered,
gaps/slippage can exceed it. At current settings up to $3,000 of premium can be at
risk simultaneously and the day halts at $1,000 of realized losses. Only fund this
strategy with money you can afford to lose entirely.
