# Strategy Specification — 0DTE Index Options Momentum

## Objective

Capture intraday directional moves in the major index ETFs using same-day-expiration
options **expiring ~7 days out**, with bounded downside (30% premium stop) and a
bounded holding period (3 trading days / 3 DTE floor). Positions are held across
sessions; there is no intraday flatten.

## Why these rules

- **7DTE, not 0DTE.** A controlled replay of 19 identical June SPY signals across
  0/3/7 DTE (`logs/backtest/dte_comparison.md`) showed the −30% stop sits *inside*
  the 0DTE noise band: it fired on 14 of 19 trades regardless of direction. At 7DTE
  median adverse excursion is −17.4%, comfortably inside the stop, and stop-outs fell
  to 6 of 19. The cost is convexity — 7DTE moves far less in percentage terms.
- **No intraday hard close.** The old 13:00–13:30 flatten existed because an unclosed
  0DTE expires or auto-exercises that day. A 7DTE contract has no such deadline, so
  the position is instead bounded by a stop, a target, and a time stop.
- **No entries in the first 15 minutes**: the 9:30–9:45 range is dominated by opening
  auctions and stop-hunting; signals fire on the *resolution* of that range.
- **30% stop-loss**: a fixed fraction-of-premium stop is the only stop type that works
  on 0DTE (underlying-based stops are too twitchy given gamma). It bounds a single
  trade's loss near `0.30 × max_premium_per_trade` ≈ $300 at default sizing — "near",
  not "at", because the stop is a market order once triggered.
- **Sentiment before signals**: minute-level pre-market tape from 9:00 onward gives
  gap context and directional drift before the open, so the open-drive signal starts
  with a prior instead of reacting cold.

## Composite sentiment score

Computed by `scripts/strategy_calc.py score` from minute bars (fetched via
`get_equity_historicals`, `bounds=extended`, `interval=minute`). Range −100…+100 per
symbol. Components (weights in parentheses):

| Component | Definition | Full-scale at |
|---|---|---|
| Overnight gap (25) | pre-market price at ~9:28 vs prior official close | ±0.50% |
| Pre-market momentum (25) | net drift of minute closes 9:00 → 9:28 | ±0.30% |
| Opening drive (35) | price now vs 9:30 open (computed 9:37 and 9:44) | ±0.30% |
| Range position (15) | where price sits in the day's high-low range, rescaled to ±1 | — |

Each component is `clamp(x / full_scale, −1, +1) × weight`; the symbol score is the
sum. The **market score** (mean across the universe) is journaled for context, but
entries are decided per symbol: each universe symbol whose |score| clears the
threshold qualifies independently, in its own direction. Divergent books (e.g. SPY
call + IWM put on a large-cap/small-cap split day) are allowed.

**Volatility is recorded but does NOT gate entries (yet).** The strategy is long
premium, so buying when implied vol sits far above what the underlying is actually
realising is a structural headwind — the same mispricing that premium *sellers* try
to harvest. Historical IV is not available through the Robinhood tools, so this
cannot be backtested; instead every signal's IV, greeks and IV/RV ratio are journaled
during dry-run, so the hypothesis can be tested on genuine forward data before any
rule is added. See `logs/backtest/trend_filter_test.md` for why an externally-sourced
filter should be measured before being adopted.

Qualitative overlay: the session also pulls headline news (`co-invest get_news`) at
9:00. News does not move the numeric score; it can only *veto* a trade (e.g., FOMC
decision day at 14:00, CPI print at 8:30 that whipsawed futures) — the veto and
reason must be journaled.

**Score velocity (diagnostic — does NOT gate entries).** `entry_threshold` only
looks at the absolute level, |score| >= 40. On 2026-07-27 the score never crossed
that level all session, but it moved -21.8 -> -30.6 in 12 minutes (9:44-9:56 ET) —
a real, fast directional move the level-only gate never saw. Every minute during
the flat re-check loop, `strategy_calc.py velocity` computes points/minute between
consecutive readings and flags anything at or above `velocity_watch_pts_per_min`
(config, default 1.0 — an unvalidated starting guess). Journaled in a dedicated
table, never acted on, same pattern as the shadow-leg and signal-decay diagnostics:
build forward evidence before considering a rule change. **Known limitation**: once
drive/range_pos clamp (see the 9:59 ET structural-floor finding), the score's
derivative saturates to ~0 for the same reason the level does — so this is
informative mainly in the pre-clamp window, not a fix for a clamped/floored score.

**Score acceleration (diagnostic — does NOT gate entries).** Second derivative:
change in points/minute per minute, via `strategy_calc.py velocity --velocity-prev`.
Flags a move speeding up or reversing, not just moving — e.g. 2026-07-27's
9:44-9:50 bounce (+3.2 pts/min) was violently reversed by 9:50-9:56 (-4.6 pts/min),
an acceleration of -1.3 pts/min^2, well past the placeholder
`acceleration_watch_pts_per_min2` (0.5). Same caveats as velocity: an unvalidated
starting threshold, saturates once components clamp, and the two-interval
timestamp is an approximation (uses the current step's dt, not the gap between
the two velocity readings' midpoints) given irregular live sampling.

**0DTE call/put price velocity + acceleration (diagnostic — never trades, does
NOT gate anything).** The same `velocity` math applied to real option premiums
instead of the abstract score, via `--watch-threshold`/`--accel-watch-threshold`
overrides (option premiums are dollar-scale, not -100..100). Two FIXED legs —
nearest-the-money 0DTE call and put, picked once per session at Phase 3 step 0
— are re-quoted every flat re-check regardless of which way, if any, the
sentiment score points; this extends the existing shadow-0DTE-leg snapshot
(previously captured only at signal time) into a continuous forward series.
Purpose: test whether 0DTE gamma-driven premium velocity carries information
the sentiment-score velocity or the eventual 7DTE trade doesn't — e.g. a 0DTE
leg could show sharp price acceleration on noise that never shows up in the
underlying's score at all. Unvalidated thresholds, journal-only, same
discipline as every other diagnostic here: build forward evidence before
proposing a rule.

## Regime filters (no-trade days)

Skip the entire day, journaling the reason, when any of:
- |overnight gap| on SPY > `gap_limit_pct` (1.5%) — gap days mean-revert unpredictably
- VIX > `vix_max` (35) — stops get run by noise
- A major scheduled macro event lands inside the trade window (FOMC statement,
  CPI/PCE/NFP released after 9:00 ET)

**VIX day-over-day change + acceleration (diagnostic only, added 2026-08-04)** —
`vix_change_watch_pts_per_day` and `vix_acceleration_watch_pts_per_day2` in config, both
computed via `strategy_calc.py velocity` at Phase 1 (velocity, then acceleration via
`--velocity-prev`, same 2nd-derivative mechanism as the sentiment-score diagnostics above).
`vix_max` is a level gate; it was never actually validated against real historical VIX (the
June out-of-sample backtest had no VIX data to test it on — see
`logs/backtest/2026-06_out_of_sample.md`). A fast VIX *jump*, and especially a jump that is
itself accelerating day over day, can signal the same mean-reversion/whipsaw regime shift
that made June lose money, even before the level crosses `vix_max`. Logged, not gating —
same discipline as the velocity/acceleration diagnostics above: build forward evidence
before proposing a rule.

## Entry rules

1. Time gate: `entry_earliest` (09:45) ≤ now ≤ 11:30 ET. 9:35, 9:45, 9:50 and 10:00
   were all backtested over Jul-13→24; the P&L spread between them was inside noise,
   so this is a judgment call, not an optimum. **9:35 is the one setting ruled out on
   mechanism**: with a single 5-min bar, `drive` and `range_position` measure noise and
   flip sign within 15 minutes.
2. Signal gate, per symbol: |symbol score| ≥ `entry_threshold` (40). Every qualifying
   symbol is a candidate — calls and puts may be held simultaneously.
3. Direction per symbol: score > 0 → **call**, score < 0 → **put**. At most one open
   position per symbol at a time; open candidates in order of |score| until
   `max_concurrent_positions` or `max_total_premium_usd` is reached.
4. Contract: today's expiration, delta in [0.35, 0.45] (slightly OTM), premium ≥
   `min_premium` ($0.15/share — cheaper contracts are spread-dominated; skip the
   entry rather than stepping strikes), bid/ask spread ≤ 10% of mid, open interest
   ≥ 500, volume ≥ 100.
5. Size per position: `floor(max_premium_per_trade / (ask × 100))` contracts, minimum
   1 — skip the symbol if even 1 contract exceeds the per-position budget ($1,000), the
   combined-premium cap, or remaining settled cash.
6. Order: limit buy at the mid, rounded up one tick; if unfilled after 2 minutes,
   re-peg to the ask once; if still unfilled after 2 more minutes, cancel and
   re-evaluate the signal from scratch.

**Entry & blocked-signal extremity diagnostic (record, never gate — added
2026-07-31, extended 2026-08-01).** For every qualifying signal — entered OR
blocked by the time gate (`entry_earliest`) or a liquidity/contract filter — log
the `drive` component/`drive_pct`, whether `drive` is clamped (`abs(drive_pct) >=
0.30`, i.e. pinned at its ±35 max), and `range_pos` (raw 0–1, plus
near-low/near-high/mid-range). Motivation: the first week of live trading
(2026-07-27→31, 3 entries) showed a `range_pos` pattern worth watching — both
losing PUT entries fired with `range_pos` essentially AT the day's exact low
(0.009 and 0.032), while the one winning CALL entry fired closer to, but short of,
the exact high (0.943) — but checking `drive`-clamp state on the same three trades
does NOT support a clean story: the winning entry's `drive` was actually *more*
clamped in percentage terms (92.9% of max) than one of the losing entries (90.9%),
so "drive clamped" alone does not distinguish these three outcomes.

A follow-up check across the same week's other days surfaced a different, more
mechanical pattern: on both 07-28 and 07-30, an earlier signal crossed
`entry_threshold` but was blocked (07-28: before `entry_earliest`; 07-30: no
contract cleared the liquidity filters) — and in both cases, the actual entry that
followed minutes later was MORE extreme (`range_pos` closer to 0/1, `drive` closer
to its clamp) than the blocked reading. That suggests the extremity pattern may be
partly, or wholly, an artifact of the entry pipeline's own delay — waiting for
`entry_earliest` or a liquid contract gives price more time to run further in the
same direction — rather than something inherent to the signal that predicts
outcome. Logging blocked signals alongside entered ones (not just entered ones) is
what lets this be tested with real numbers instead of anecdote.

This is recorded as a hypothesis, not a finding: n is still tiny, directions are
confounded, and the cleanest-looking part of the original hunch (drive-clamp)
already failed to hold up. It does not gate entries. Revisit only once there's
enough signals — entered and blocked — to test it without curve-fitting to a
handful of days — see `logs/journal/` "Entry & blocked-signal extremity tracking"
table.

## Exit rules (first hit wins)

Exits are evaluated per position, on a **1-minute monitoring cadence** — both while
positions are open and while flat (signal re-checks), per `monitoring:`.

| Exit | Mechanism |
|---|---|
| −28% initial stop | Resting **stop-market, GTC** sell placed immediately after entry fill: trigger at 72% of fill (−28%, slippage margin). **This is the only protection an open position has until the trailing stop below activates** — it must be `gtc`, never `gfd`, or it expires at the close and leaves the position naked overnight. No limit floor: a stop-limit can gap through its floor and never fill. |
| Trailing stop (post +10%) | **Added 2026-07-30 (owner decision) — REAL, gating rule.** Promoted from the diagnostic-only "consider-exit checkpoint" row this table used to carry (2026-07-29 → 2026-07-30). Once unrealized gain first crosses `consider_exit_pct` (+10% of fill), the resting stop tightens off the −28% floor to trail the peak: `effective_stop = fill × (1 + (peak_gain_pct − trail_stop_distance_pct) / 100)`, clamped to never go below the original −28% stop. `trail_stop_distance_pct` (default 14, half the original stop width) sets how far behind the running peak it trails — the stop only ever moves up, re-placed at the new `effective_stop` any time it increases. Compute with `strategy_calc.py stops --fill F --peak P` (`trailing_stop`/`effective_stop`/`trailing_stop_active`). **Zero backtest evidence** — added directly from live/dry-run observation: the 2026-07-30 SPY 738C crossed +10% at 13:01 ET and did not exit until +32% five hours later purely because consider_exit was diagnostic-only that day; the +10% activation and 14pp trail width are both unvalidated starting guesses, not tuned thresholds — re-tune (or revert to diagnostic-only) if forward data shows it triggers prematurely on ordinary chop. If the trailing stop fills, re-entry is permitted under the normal re-entry rules below if the signal still qualifies. |
| +30% take-profit | Checked every minute during market hours. If mid ≥ 130% of fill: cancel the stop, sell at bid-pegged limit, then confirm flat. (Not resting — Robinhood allows only one working sell against a position.) Lowered from +60% on 2026-07-29 after a SPY 740P round-tripped from +40.6% unrealized (12:15 ET) to a −28.96% stop-out (14:45 ET) on an FOMC-driven reversal — see `logs/journal/2026-07-29.md`. The +60% level came from the July 0DTE backtest (median MFE only +13.4% at 7DTE, target reached 2/19 times — see `logs/backtest/dte_comparison.md`). Retested June+July 2026 on regenerated real-data SPY 7DTE trades: directionally supportive on June (+$124 vs a −$1,371 counterfactual under the old +60%, the round-trip-prevention mechanism visible in 4 of 14 trades), a null result on July (every trade stopped out before either target bound) — see `logs/backtest/take_profit_30pct_test.md`. Thin sample (22 trades total, only 6 where the two rules diverge); not treated as settled. |
| Time stop | Exit by 13:30 ET on the 3rd trading day after entry (`max_hold_trading_days`). |
| DTE floor | Exit immediately if the contract reaches `min_dte_at_exit` (3 DTE), whichever comes first — this keeps the position out of the theta cliff and out of 0DTE entirely. |
| *(diagnostic)* Shadow 0DTE leg | **Not a position.** Every signal also resolves the equivalent 0DTE contract (same direction, same strike where it exists), and its price, greeks and stop/target outcomes are journaled to a 13:30 terminal value. Purpose: the June DTE comparison favoured 7DTE, but June was mean-reverting while July's gains came from 0DTE convexity — the ranking is likely regime-dependent, so this builds a forward out-of-sample answer at zero risk. Never traded. |
| *(diagnostic)* Signal decay | **Not an exit.** While a position is open, the session logs when the entry thesis dies (\|score\| < 20 or sign flip) and what an exit there would have realised, then keeps logging until the real exit. A June test on 4 affected trades improved the month from +$261 to +$598 — promising, but 4 trades, with 80% of the gain resting on one within-bar timing call, and 30-min checkpoints cannot model the live 1-minute cadence. Journaled to build forward evidence; see `logs/backtest/signal_decay_test.md`. |
| Daily loss halt | Realized loss on a calendar day ≥ `daily_loss_halt_usd` → no further entries that day, and close any position still open. **Ordering rule (previously ambiguous):** the resting stop is a live server-side order — if it fills, that fill is the exit. The halt only force-closes positions still open at the moment it triggers. |

Re-entries (up to `max_trades_per_day` total entries) are allowed after an exit if
the time gate still holds, the symbol re-qualifies, concurrency/premium caps permit,
and the trade is funded from still-settled cash (never same-day sale proceeds —
good-faith-violation rule).

## Sizing & account constraints

- Account: Robinhood cash account (no margin, no PDT restrictions, but T+1 settlement
  on option sale proceeds — hence the proceeds-reuse rule).
- **Overnight gap risk is new and unavoidable.** A GTC stop-market triggers on the
  open if a gap carries price through it, filling at whatever the market offers —
  potentially far worse than −30%. This risk did not exist under the 0DTE design.
- Default budget: $1,000 premium per position, ONE position at a time (single-symbol
  universe), 6 sequential entries/day. A full 30% stop is now ≈ −$300, so
  the `daily_loss_halt` of $1,000 binds first — the day ends after roughly 3 full
  stops, not 6. Max premium at risk at any instant is $3,000 (~26% of the account's
  $11.6k); max realized loss per day is the $1,000 halt (~8.6%).
- Agentic API is single-leg only: long calls and long puts. No spreads, no shorts.

## Known failure modes (accepted)

- A fast gap through the stop fills at an unbounded price — with stop-market the exit
  is guaranteed but the loss can exceed −30% (accepted trade for never holding an
  unprotected position). Overnight gaps make this materially more likely than under
  the intraday-only design. The monitor loop still market-closes any position sitting
  below its trigger with no working stop order.
- **The exit geometry is untested for multi-day holds.** The ±30/60 bands were
  measured on *intraday* 7DTE holds, where median MFE was only +13.4% and the target
  was reached 2 of 19 times. Over a 3-day hold the distribution widens and both
  barriers become more reachable, but no backtest covers this combination — see the
  warning at the top of `logs/backtest/dte_comparison.md`.
- Signals near threshold on chop days will produce stop-outs; the daily halt bounds it.
- If every session-scheduling mechanism fails, the position still carries a working
  GTC stop server-side, which is why that invariant is absolute. The 15:45 EOD check
  and 16:10 failsafe exist to verify that stop is present, not to flatten positions.
