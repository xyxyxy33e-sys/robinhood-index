# PLAYBOOK — Daily 0DTE Session Runbook

Audience: the Claude agent session fired by the `0dte-morning-session` routine at
9:00 ET. Execute top to bottom. All times US/Eastern; MCP timestamps are UTC.
Load config from `config/strategy.yaml` first — never hardcode parameters.

**Prime directives**
1. If `mode: dry_run` → never call `place_option_order` / `cancel_option_order`.
   Journal the exact order you *would* have placed instead (contract, qty, price).
2. Never exceed a `risk:` limit. When any check is ambiguous, don't trade.
3. Whatever happens, run **Phase 5 (hard close)** and **Phase 6 (journal + push)**.
4. Schedule every intra-day pause with `send_later` (claude-code-remote MCP).
   Never use Bash sleep.

## Phase 0 — Bootstrap (9:00)

1. `git fetch origin claude/robinhood-day-options-strategy-y8eskp` and check it out
   (the default branch may be empty — this branch is the source of truth).
2. Read `config/strategy.yaml`. Confirm today is a weekday and equity markets are
   open (skip + journal on market holidays — check whether SPY's chain lists today
   in `expiration_dates` via `get_option_chains`; no 0DTE today → no-trade day).
3. Verify via `get_accounts` that the configured account is still
   `agentic_allowed=true` with `option_level_2`+. If not: journal, notify, stop.
4. `get_portfolio` → record start-of-day settled cash (sizing base).
5. `get_option_positions` (nonzero) → if yesterday left anything expiring today
   (should never happen), treat as inherited risk: apply Phase 4 monitoring to it.
6. Create today's journal file `logs/journal/YYYY-MM-DD.md` from the template at the
   bottom of this file.

## Phase 1 — Sentiment collection (9:00 → 9:29)

1. At 9:00: `co-invest get_news` — scan for regime-filter events (FOMC, CPI, NFP,
   major geopolitical shock). `get_indexes` / `get_index_quotes` for VIX level.
2. Poll minute bars with `get_equity_historicals`:
   `symbols=[SPY,QQQ,IWM]`, `interval=minute`, `bounds=extended`,
   `start_time=<09:00 ET today in UTC>`. Each poll returns the full minute-by-minute
   tape since 9:00, so polling every ~7 min (wake via `send_later`, e.g. 9:07, 9:14,
   9:21, 9:28) yields complete per-minute coverage without a wake per minute.
3. At ~9:28: write the collected bars + prior closes (`get_equity_quotes` →
   `close.price`) + VIX to `data/YYYY-MM-DD-bars.json` (schema: see script header)
   and run `python3 scripts/strategy_calc.py score --input data/YYYY-MM-DD-bars.json`.
   Journal the pre-open score and any regime-filter hit.
4. Regime filter tripped (gap, VIX, macro event) → journal "NO-TRADE DAY: <reason>",
   skip to Phase 5 timing (still schedule a 12:45 wake to double-check flatness).

## Phase 2 — Opening drive (9:30 → 9:44)

1. Wake at 9:37 and 9:44 (`send_later`). Each wake: refresh minute bars (now
   including regular-session bars), re-run the score.
2. Journal score evolution. No orders in this phase.

## Phase 3 — Entry decision (9:45, re-checks until 11:30)

1. Compute final score. Gate: |market score| ≥ `entry_threshold` AND agreement rule
   satisfied AND no news veto.
   - Not met → schedule re-checks every 15 min until `entry_latest` (11:30); each
     re-check repeats this phase. After 11:30 → Phase 4 (monitor-only).
2. Pick instrument + direction per STRATEGY.md. Then:
   a. `get_option_chains` (symbol) → chain id; confirm today ∈ expiration_dates.
   b. `get_option_instruments` (chain_id, expiration_dates=today, type=call|put)
      → strikes bracketing spot.
   c. `get_option_quotes` on the 4–6 candidates nearest the delta band → pick the
      contract meeting delta/spread/OI/volume rules (delta band per config; if the
      quote payload lacks greeks, approximate: for ~0.35–0.45 delta use the strike
      1–2 increments OTM from spot).
   d. Size: `python3 scripts/strategy_calc.py size --price <ask> --budget <config>`.
      Confirm premium ≤ remaining settled cash.
3. Place (live mode): `review_option_order` (limit buy, mid rounded up one tick,
   gfd, with `chain_symbol` + `underlying_type` for fees) → inspect alerts; any
   blocking alert → journal and abort the trade. Then `place_option_order` with a
   fresh UUID `ref_id`.
4. Fill management: poll `get_option_orders` (order_id) after ~2 min. Unfilled →
   cancel, re-place at ask once. Still unfilled → cancel, journal, return to signal
   re-checks. Partial fills count as filled for stop purposes (stop qty = filled qty).
5. **Immediately after fill** (live mode): place the resting stop —
   `stops` from `python3 scripts/strategy_calc.py stops --fill <avg_fill>`:
   stop_limit sell-to-close, `stop_price = trigger`, `price = limit_floor`, gfd,
   fresh `ref_id`. Verify it's working via `get_option_orders`. **A position must
   never sit without a working stop for more than one monitoring cycle.**
6. Journal: contract, qty, fill, stop order id, score at entry.

## Phase 4 — Monitoring loop (entry → 12:45)

Wake every ~10 min via `send_later`. On each wake:
1. `get_option_positions` (nonzero) + `get_option_quotes` on held contracts;
   `get_option_orders` to confirm the stop is still working.
2. Stop filled → journal exit P&L. If time < `entry_latest` and trades used <
   `max_trades_per_day`: re-run Phase 3 re-check (funded from settled cash only).
3. Mid ≥ take-profit level → cancel stop (`cancel_option_order`), sell at bid-pegged
   limit, confirm fill, journal.
4. Safety net: position open but **no working stop** (cancelled/rejected/expired) and
   mid ≤ stop trigger → sell immediately at marketable limit; else re-place the stop.
5. Realized day P&L ≤ −`daily_loss_halt_usd` → close everything now, no re-entry,
   journal "DAILY HALT".
6. Journal a one-line status each wake (time, mids, P&L, open orders).

## Phase 5 — Hard close (12:45 → 13:00)

1. At 12:45: `cancel_option_order` on every working order in the account for today's
   strategy positions; then sell-to-close every open position, limit at bid − 1 tick.
2. Poll fills every 2 min; unfilled → re-peg lower. All positions MUST be flat by
   13:00. If a close order rejects repeatedly, keep retrying with wider limits and
   journal each attempt (the 13:10 failsafe routine is the backstop, not the plan).
3. Verify: `get_option_positions` (nonzero) returns no strategy positions.

## Phase 6 — Journal & push (by ~13:05)

1. Complete the journal: fills, P&L (realized, per trade and total), signal history,
   deviations from playbook.
2. `git add logs/ && git commit` (message: `journal: YYYY-MM-DD <summary>`) and
   `git push -u origin claude/robinhood-day-options-strategy-y8eskp`
   (retry ×4, backoff 2/4/8/16s).
3. End the session. Do not leave wakes scheduled past 13:10.

## Journal template

```markdown
# 0DTE Journal — YYYY-MM-DD
mode: <dry_run|live>  |  settled cash at open: $X  |  VIX: X
## Regime
gap SPY: X% · news veto: none|<reason> · tradeable: yes|no
## Signal history
| time | SPY | QQQ | IWM | market | note |
## Trades
| # | contract | qty | fill | stop id | exit | exit px | P&L | reason |
## End of day
flat by: HH:MM · realized P&L: $X · trades: N/2 · deviations: none|<list>
```
