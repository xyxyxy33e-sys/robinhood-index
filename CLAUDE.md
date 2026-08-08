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
2. Positions are held across sessions. Exit on: **static −28% stop**
   (`stop_trigger_frac` — the resting stop is NEVER moved), +30% target,
   `max_hold_trading_days` (3), `min_dte_at_exit` (3 DTE), or the **EOD carry
   gate** (below) — whichever hits first. (Take-profit lowered from +60% on
   2026-07-29; **trailing stop REMOVED 2026-08-07, owner decision** — it never
   fired in 8 forward trades and was near-redundant under the +30% TP; see
   `logs/analysis/2026-08-07_forward_review.md`. `consider_exit_pct` /
   `trail_stop_distance_pct` no longer exist in config; `stops --peak` is
   diagnostic-only now.)
   **EOD carry gate (real, gating rule — added 2026-08-07, owner decision):**
   at Phase 5 (15:45 ET), an open position whose mid is at or below
   `eod_carry_floor` (fill × 0.86; config `eod_carry_min_unrealized_pct: -14`,
   from `strategy_calc.py stops --fill F`) is CLOSED before 16:00 instead of
   carried overnight — too little cushion to the −28% stop against a gap
   through the trigger. Positions above the floor carry as designed.
   If a stop fills, re-entry is permitted under the normal re-entry rules if
   the signal still qualifies. Signal decay remains diagnostic-only — log it,
   never act on it (forward evidence is mixed: helped 3 losers, would have
   killed the 2026-07-30 winner).
3. No entries after 11:30 ET (11:30:00 inclusive, later exclusive). Entries also
   require the **persistence gate** (added 2026-08-07, owner decision): |score| ≥
   `entry_threshold` for `entry_persistence_min` (3) consecutive minutes, same
   sign, verified on backfilled 1-minute bars via `strategy_calc.py persistence`
   — never on sparse polling checks alone. Never exceed the `risk:` limits.
4. At most ONE open position at a time (`max_concurrent_positions: 1`), so total
   exposure is capped at `max_premium_per_trade_usd` ($1,000).
