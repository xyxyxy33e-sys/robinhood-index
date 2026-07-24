# robinhood-index — SPY 7DTE Index Options Strategy

An agent-operated strategy that trades **SPY options expiring ~7 days out** through
the Robinhood agentic account. Entries are signalled intraday; positions are held
across sessions and exited by stop, target, or time stop.

> **History:** this began as a 0DTE intraday strategy on SPY/QQQ/IWM. Out-of-sample
> testing (`logs/backtest/`) showed (a) the three ETFs' signals fire together, making
> a "diversified" book one leveraged bet, and (b) the −30% stop sits inside the 0DTE
> noise band, firing on 14 of 19 trades regardless of direction. Hence: one symbol,
> longer expiry. **The strategy has not demonstrated a profitable edge — read the
> backtest logs before funding it.**

## Daily lifecycle (all times US/Eastern)

| Time | Action |
|---|---|
| 9:00 | Scheduled session starts; begins tracking market sentiment minute-by-minute (pre-market bars, overnight gap, news) |
| 9:30 | Market opens; session watches the opening drive (no entries yet — first 15 min is noise) |
| 9:45–11:30 | Entry window: if SPY's sentiment score clears the threshold, buy a ~7DTE call (bullish) or put (bearish). One position at a time, ≤ $1,000 premium |
| immediately after fill | Resting stop-market **GTC** order at −28% of fill — with no hard close this is the position's only protection, so it must survive overnight |
| every minute (market hours) | Monitor: take-profit check, stop verification, time-stop / DTE-floor check |
| 15:45 | **EOD verification**: confirm every open position still has a working GTC stop; close anything that cannot be protected |
| 16:10 | Independent failsafe re-verifies stops on all carried positions |
| exit | −30% stop · +60% target · 3 trading days held · or 3 DTE remaining — whichever first |

## Repository layout

- `docs/STRATEGY.md` — full strategy specification: signal construction, entry/exit rules, risk limits, rationale
- `docs/PLAYBOOK.md` — the step-by-step runbook the scheduled agent session executes each morning (tool-by-tool)
- `config/strategy.yaml` — all tunable parameters (mode, sizing, thresholds, times)
- `scripts/strategy_calc.py` — deterministic math: sentiment scoring, position sizing, stop/target prices
- `logs/journal/` — one committed journal file per trading day (signals, decisions, orders, P&L)
- `data/` — intraday scratch data (gitignored)

## Safety model

1. **`mode` in `config/strategy.yaml` governs everything. It is currently `dry_run`.**
   The session does everything — sentiment, signals, contract selection, sizing — and
   journals the trades it *would* have placed, but never places, cancels or modifies
   an order. Set it to `live` to trade real money; read `logs/backtest/` first.
2. Setting `mode: live` is your standing authorization for scheduled sessions to place
   orders **within the limits in `config/strategy.yaml`** without per-order
   confirmation. Review the `risk:` block before flipping it.
3. Hard limits enforced by the playbook: max premium per trade, one position at a
   time, max trades per day, daily loss halt, no entries after 11:30 ET, and a
   working GTC stop on every open position at all times.
5. **Overnight gap risk exists now.** Removing the intraday close means a gap can
   carry price through the stop, filling far below −30%. This did not exist under
   the 0DTE design.
4. Cash account discipline: trades are funded only from start-of-day settled cash and
   same-day sale proceeds are never re-used (avoids good-faith violations).

## Scheduling

Two Claude Code routines drive the strategy (created via the Claude Code Remote
trigger system; cron is evaluated in **UTC**):

| Routine | ID | Cron (UTC) | ET (EDT) | Purpose |
|---|---|---|---|---|
| `0dte-morning-session` | `trig_0113xQ7waSQKDmJU9QyHqoUC` | `0 13 * * 1-5` | 9:00 weekdays | Runs `docs/PLAYBOOK.md` end-to-end |
| `0dte-failsafe-closeout` | `trig_01RoDZSx6HvoxA7RdpRCsjiG` | `10 20 * * 1-5` | 16:10 weekdays | Verifies every carried position has a working GTC stop |

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

Long options are among the highest-risk instruments retail traders can buy: theta
decay is relentless, and a 100% loss of premium on any given trade is a normal outcome.
The 30% stop-loss bounds per-trade damage but, being a market order once triggered,
gaps/slippage can exceed it. At current settings up to $3,000 of premium can be at
risk simultaneously and the day halts at $1,000 of realized losses. Only fund this
strategy with money you can afford to lose entirely.
