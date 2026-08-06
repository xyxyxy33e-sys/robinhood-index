# robinhood-index

Agent-operated index-options swing strategy on SPY (7DTE) via the Robinhood
agentic account. Formerly a 0DTE intraday strategy — see `logs/backtest/` for why
it changed.

- If you are a scheduled morning session: execute `docs/PLAYBOOK.md` top to bottom.
- Strategy rules and rationale: `docs/STRATEGY.md`. Parameters: `config/strategy.yaml`.
- **Respect `mode` in the config.** `dry_run` = never place, cancel, or modify orders.
- All math (sentiment score, sizing, stops) goes through `scripts/strategy_calc.py` —
  never improvise these numbers.
- Working branch for everything (code + daily journals):
  `claude/robinhood-day-options-strategy-y8eskp`. The default branch may be empty.
- **This account is shared with other independently-operated agentic strategies**
  (confirmed by the owner 2026-08-06) — at least one other agent trades single-stock
  options in parallel on the same account (e.g. Unity/U calls seen 2026-08-06,
  chain_id `55c8d94d-b46d-4dcb-abd0-db92b7eb04fa`). Positions/orders on tickers
  outside `universe:` in `config/strategy.yaml` are NOT this strategy's — do not
  manage, cancel, or replace them. If one of those positions has a real safety gap
  (e.g. a `gfd` stop that will leave it unprotected overnight), flag it clearly to
  the account owner and journal it as an out-of-scope observation, but do not act
  on it — this strategy has no authorization over other strategies' orders. See
  `logs/journal/2026-08-06.md` for the full incident writeup and how it resolved.

## Hard invariants (these replaced the old 0DTE "flat by 13:00" rule)
1. **Every open position must carry a WORKING GTC stop-market order at all times.**
   With no intraday hard close, this is the only protection a position has. A `gfd`
   stop expires at the close and leaves the position naked overnight — never use one.
2. Positions are held across sessions. Exit on: **trailing stop** (see below),
   +30% target, `max_hold_trading_days` (3), or `min_dte_at_exit` (3 DTE) —
   whichever hits first. (Take-profit lowered from +60% on 2026-07-29 — see
   `docs/STRATEGY.md`.)
   **Trailing stop (real, gating rule as of 2026-07-30 — owner decision):**
   the resting stop starts at −28% (`stop_trigger_frac`). Once unrealized gain
   first crosses `consider_exit_pct` (+10%), the stop TIGHTENS to trail the
   peak unrealized gain, staying `trail_stop_distance_pct` (14 points) behind
   the highest gain reached since activation — it only ever moves up. Compute
   both levels with `strategy_calc.py stops --fill F --peak P`
   (`effective_stop` is the number to actually use). `consider_exit_pct` was
   diagnostic-only 2026-07-29→2026-07-30; it is a real activation trigger now.
   If the trailing stop fills, re-entry is permitted under the normal
   re-entry rules if the signal still qualifies. Signal decay remains
   diagnostic-only — log it, never act on it.
3. No entries after 11:30 ET. Never exceed the `risk:` limits.
4. At most ONE open position at a time (`max_concurrent_positions: 1`), so total
   exposure is capped at `max_premium_per_trade_usd` ($1,000).
