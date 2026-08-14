# PLAYBOOK — Daily 0DTE Session Runbook

Audience: the Claude agent session fired by the `0dte-morning-session` routine at
9:00 ET. Execute top to bottom. All times US/Eastern; MCP timestamps are UTC.
Load config from `config/strategy.yaml` first — never hardcode parameters.

**Prime directives**
1. If `mode: dry_run` → never call `place_option_order` / `cancel_option_order`.
   Journal the exact order you *would* have placed instead (contract, qty, price).
2. Never exceed a `risk:` limit. When any check is ambiguous, don't trade.
3. Whatever happens, run **Phase 5 (EOD verification)** and **Phase 6 (journal + push)**.
4. Schedule every intra-day pause with `send_later` (claude-code-remote MCP).
   Never use Bash sleep.
5. **Poll every 5 minutes and REPLAY the gap — never trust the endpoint score.**
   (Revised 2026-08-14, owner decision, replacing the 1-min-cadence + fallback-wake
   pattern of 2026-08-12.) Wake delivery is unreliable and does not scale with how
   many triggers you create; minute-resolution comes from replaying backfilled bars
   on each wake, NOT from waking every minute. See Phase 4.

## Phase 0 — Bootstrap (9:00)

1. `git fetch origin claude/robinhood-day-options-strategy-y8eskp` and check it out
   (the default branch may be empty — this branch is the source of truth).
2. Read `config/strategy.yaml`. Confirm today is a weekday and equity markets are
   open (skip + journal on market holidays — check whether SPY's chain lists today
   in `expiration_dates` via `get_option_chains`; no 0DTE today → no-trade day).
3. Verify via `get_accounts` that the configured account is still
   `agentic_allowed=true` with `option_level_2`+. If not: journal, notify, stop.
4. `get_portfolio` → record start-of-day settled cash (sizing base).
5. `get_option_positions` (nonzero) → **positions carried over from previous sessions
   are expected now.** For each: confirm a WORKING GTC stop exists (`get_option_orders`,
   state=queued/confirmed); if not, re-place it immediately. Record entry date and
   expiration so Phase 4 can apply the time stop and DTE floor.
6. Create today's journal file `logs/journal/YYYY-MM-DD.md` from the template at the
   bottom of this file.

## Phase 1 — Sentiment collection (9:00 → 9:29)

1. At 9:00: `co-invest get_news` — scan for regime-filter events (FOMC, CPI, NFP,
   major geopolitical shock). `get_indexes` / `get_index_quotes` for VIX level.
1b. **VIX day-over-day change + acceleration (diagnostic, added 2026-08-04).** Fetch VIX's
   last TWO completed daily closes via `get_index_historicals` (interval=day, ~7 calendar
   days back to be safe over weekends/holidays, take the last two completed bars: T-2 and
   T-1). Compute:
   - **Yesterday's velocity** (needed only as an input to today's acceleration):
     `python3 scripts/strategy_calc.py velocity --score-now <T-1 close> --score-prev <T-2
     close> --minutes-elapsed 1` → read its `delta` (or `points_per_minute`, identical at
     dt=1) as yesterday's day-over-day change.
   - **Today's change + acceleration + percentage**: `python3 scripts/strategy_calc.py
     velocity --score-now <today's VIX from step 1> --score-prev <T-1 close>
     --minutes-elapsed 1 --velocity-prev <yesterday's delta from above> --watch-threshold
     5.0 --accel-watch-threshold 3.0 --pct-watch-threshold 15.0`.
   `--minutes-elapsed 1` in both calls means "1 day-step", NOT one minute — do not pass
   1440; the tool's `notable`/`notable_accel` flags compare against the watch thresholds on
   that same unit, so a real 1440-minute dt would silently dilute a 5+ point jump to ~0.003
   pts/min and neither flag would ever fire. With dt=1, `delta`/`points_per_minute` read
   directly as the day-over-day point change, and `acceleration_pts_per_min2` reads directly
   as points/day². `pct_change` (and `notable_pct`, since `--pct-watch-threshold` is passed)
   reads as the day-over-day percentage move — meaningful for VIX in a way a fixed point
   threshold isn't, since a point move means something very different at a low vs high VIX
   baseline. Journal the change, acceleration, and percentage next to the VIX level.
   *** DIAGNOSTIC ONLY — does not gate entries, see `vix_change_watch_pts_per_day`,
   `vix_acceleration_watch_pts_per_day2`, and `vix_change_watch_pct_per_day` in
   config/strategy.yaml for rationale ***.
2. Poll minute bars with `get_equity_historicals`:
   `symbols=[SPY,QQQ,IWM]`, `interval=minute`, `bounds=extended`,
   `start_time=<09:00 ET today in UTC>`. Each poll returns the full minute-by-minute
   tape since 9:00, so polling every ~7 min (wake via `send_later`, e.g. 9:07, 9:14,
   9:21, 9:28) yields complete per-minute coverage without a wake per minute.
2b. **Volatility baseline (record every day, traded or not).** Fetch 21 daily SPY
   closes (`get_equity_historicals`, interval=day, ~30 calendar days back) and run
   `python3 scripts/strategy_calc.py rvol --closes "<oldest,...,newest>"`. Record
   rv5/rv10/rv20 alongside the VIX level from step 1. This is the denominator of the
   IV/RV ratio.
3. At ~9:28: write the collected bars + prior closes (`get_equity_quotes` →
   `close.price`) + VIX to `data/YYYY-MM-DD-bars.json` (schema: see script header)
   and run `python3 scripts/strategy_calc.py score --input data/YYYY-MM-DD-bars.json`.
   Journal the pre-open score and any regime-filter hit.
4. Regime filter tripped (gap, VIX, macro event) → journal "NO-TRADE DAY: <reason>",
   skip to Phase 5 timing (still schedule a 12:45 wake to double-check flatness).

## Phase 2 — Opening drive (9:30 → 9:44)

1. Wake at 9:37 and 9:44 (`send_later`). Each wake: refresh minute bars (now
   including regular-session bars), re-run the score.
2. Journal score evolution. No orders in this phase — but if `|score| >= entry_threshold`
   fires here (before `entry_earliest`), it is still a real signal that a live entry
   would eventually respond to once 09:45 arrives. Log a row in the "Entry &
   blocked-signal extremity tracking" table with status `blocked - time gate` (see
   Phase 3 step 2f for the column definitions) — this captures the extremity reading
   at the *first* crossing, before waiting for `entry_earliest` pushes it further.

## Phase 3 — Entry decision (entry_earliest 09:45, re-checks until 11:30)

0. **Resolve 0DTE reference legs, once per session (record, never trade).** If
   `shadow_dte` (0) has a listed expiration today (already checked in Phase 0):
   `get_option_chains` (SPY) → `get_option_instruments` (today's expiration) →
   `get_option_quotes` to pick the nearest-the-money CALL and nearest-the-money
   PUT to the current SPY price (independent of the sentiment score's direction —
   track both sides regardless of which way, if any, the score is pointing).
   Record both `option_id`s and their initial mid prices — **fix these two
   contracts for the rest of the session** (do not re-pick a new ATM strike as
   spot moves; that would corrupt the velocity series by switching instruments
   mid-stream). Skip and journal "no 0DTE expiry today" if none exists.
1. Compute final scores. The `signal.entries` list from `strategy_calc.py score`
   holds every symbol whose |score| ≥ `entry_threshold` (strongest first), each with
   its own direction — calls and puts may be opened simultaneously. Apply the news
   veto, **then the persistence gate (REAL, gating — added 2026-08-07, owner
   decision)**: backfill the day's 1-minute bars up to now and run
   `strategy_calc.py persistence --input <bars.json>` — the entry may proceed only
   if `entry_gate_met` is true, i.e. |score| has held ≥ `entry_threshold` with the
   same sign for `entry_persistence_min` (3) consecutive minutes. This is measured
   on the minute-bar series, NOT on polling checks, so backfill before evaluating;
   entry must still be at or before `entry_latest` (11:30:00 ET inclusive, later
   exclusive). When the gate BLOCKS an otherwise-qualifying signal, journal the
   blocked entry (time, score, run length) in the "Entry & blocked-signal extremity
   tracking" table with status `blocked - persistence gate`, and track its
   hypothetical outcome like a shadow trade — that record is the forward evidence
   for re-tuning P (see `logs/backtest/entry_confirmation_test.md`). A
   persistence-blocked signal does not consume a `max_trades_per_day` slot. Then
   open positions in list order until `max_concurrent_positions` (one per
   symbol) or `max_total_premium_usd` is hit.
   - Empty list → schedule re-checks every `interval_flat_minutes` until
     `entry_latest` (11:30); each re-check repeats this phase. After 11:30 →
     Phase 4 (monitor-only).
   - **Score velocity + acceleration (record, never gate).** On each flat re-check,
     run `python3 scripts/strategy_calc.py velocity --score-now <this reading>
     --score-prev <last reading> --minutes-elapsed <gap> --velocity-prev <last
     computed points_per_minute>` (omit `--velocity-prev` on the first two
     re-checks of the day — no prior velocity yet to diff). Journal a row in the
     "Score velocity tracking" table when `notable` or `notable_accel` is true,
     or the direction/accel_direction flips; this is purely diagnostic — it must
     NOT be used to decide whether to enter. See STRATEGY.md.
   - **0DTE call/put price velocity + acceleration (record, never gate/trade).**
     Same re-check, `get_option_quotes` on the two fixed `option_id`s from step 0
     (cheap — no chain/instrument re-resolution needed). For EACH leg independently
     run `python3 scripts/strategy_calc.py velocity --score-now <mid now>
     --score-prev <mid last check> --minutes-elapsed <gap> --velocity-prev <last
     computed pts_per_minute for that leg> --watch-threshold
     <option_velocity_watch_usd_per_min> --accel-watch-threshold
     <option_acceleration_watch_usd_per_min2>`. Journal a row per notable leg in
     the "0DTE option price velocity tracking" table. Purely diagnostic — never
     gates, never triggers a trade in either mode. If a fixed leg expires
     worthless intraday or the quote 404s, journal it and stop tracking that leg
     for the rest of the day (don't re-pick a new strike mid-session).
2. For each entry candidate:
   a. `get_option_chains` (symbol) → chain id; confirm today ∈ expiration_dates.
   b. Pick the expiration: nearest listed date **>= `dte_target` (7) calendar days**
      out; if +7 is a weekend/holiday take the next available, never below +6.
      Then `get_option_instruments` (chain_id, that expiration, type=call|put).
      NOTE: verify today ∈ expiration_dates is NO LONGER the check — 0DTE is not used.
   c. `get_option_quotes` on the candidates → pick the contract meeting
      delta (`target_delta_min`/`max`, 0.45–0.55 at 7DTE) / premium-floor / spread /
      OI / volume rules. Use the REAL delta from the quote payload; the old 0DTE
      strike-offset heuristic does not transfer to 7DTE. If NO candidate clears
      these filters, the signal is blocked — log a row in the "Entry & blocked-signal
      extremity tracking" table (step 2f below) with status `blocked - liquidity/
      contract filter`, then return to signal re-checks (this does not consume a
      `max_trades_per_day` slot).
   d. Size: `python3 scripts/strategy_calc.py size --price <ask> --budget <config>`.
      Confirm premium ≤ remaining settled cash.
   d2. **Shadow leg (record, never trade).** Resolve the equivalent `shadow_dte`
      (0DTE) contract for this same signal: same underlying, same direction, same
      strike as the 7DTE pick where that strike exists at today's expiry — if it does
      not, take the nearest available strike and say so. Record its ask, mid, IV and
      greeks, and the contracts a full `max_premium_per_trade_usd` budget would have
      bought. Skip and journal "no 0DTE expiry today" when today is not an expiration
      date. **Never place an order for it.**
   e. **Record the volatility snapshot** from the chosen contract's `get_option_quotes`
      payload — `implied_volatility`, `delta`, `gamma`, `theta`, `vega`, plus the
      IV/RV ratio (contract IV ÷ rv10 from Phase 1, both as decimals). Do this for
      EVERY qualifying signal, including ones not taken because a cap or the premium
      floor blocked them — the not-taken rows are just as useful for the analysis.
      **Rationale:** we are long premium, so paying above-realised IV is a structural
      headwind. Historical IV is not retrievable through these tools, so this forward
      record is the only way to test whether the ratio predicts outcomes. It is
      DIAGNOSTIC ONLY — it does not gate entries and must not change any decision.
   f. **Record the entry & blocked-signal extremity diagnostic** (added 2026-07-31,
      extended 2026-08-01 to cover blocked signals). From the relevant
      `strategy_calc.py score` output's `detail`/`components`, record: status
      (`ENTERED`, `blocked - time gate`, or `blocked - liquidity/contract filter`),
      `drive` component value and `drive_pct`, whether drive is clamped
      (`abs(drive_pct) >= 0.30`, i.e. the component sits at its ±35 max), and
      `range_pos` (raw 0–1) with a qualitative read (near-low <0.15, near-high >0.85,
      else mid-range). Log a row for EVERY qualifying signal — entered or blocked —
      not just the ones taken. **Rationale:** the first week of live entries (2
      losses, 1 win) showed a suggestive `range_pos` pattern (both losses at the
      exact day-low, 0.009/0.032; the win short of the exact high, 0.943), but the
      `drive`-clamp part of the original hunch did NOT hold up — the winning entry
      was actually more clamped in percentage terms than one of the losses. A
      follow-up check of blocked signals from that same week (07-28's 9:37 ET
      time-gate block, 07-30's 9:44 ET liquidity block) showed the eventual actual
      entry was consistently MORE extreme than the first blocked reading — i.e. the
      entry gates (`entry_earliest`, liquidity filters) systematically delay entry
      until price has moved further, which may explain the extremity pattern better
      than anything about the signal itself. Logging blocked signals alongside
      entered ones is what lets that be tested with real numbers instead of two
      anecdotes. n is still tiny — see STRATEGY.md for the full caveat. DIAGNOSTIC
      ONLY — it does not gate entries and must not change any decision until there
      is enough data to test it properly.
3. Place (live mode): `review_option_order` (limit buy, mid rounded up one tick,
   gfd, with `chain_symbol` + `underlying_type` for fees) → inspect alerts; any
   blocking alert → journal and abort the trade. Then `place_option_order` with a
   fresh UUID `ref_id`.
4. Fill management: poll `get_option_orders` (order_id) after ~2 min. Unfilled →
   cancel, re-place at ask once. Still unfilled → cancel, journal, return to signal
   re-checks. Partial fills count as filled for stop purposes (stop qty = filled qty).
5. **Immediately after fill** (live mode): place the resting stop —
   `stops` from `python3 scripts/strategy_calc.py stops --fill <avg_fill>`:
   **`type: stop_market`**, sell-to-close, `stop_price = stop_trigger`, NO `price`
   parameter (stop_market rejects one), **`time_in_force: gtc`**,
   `market_hours: regular_hours`, fresh `ref_id`. The API requires `stop_price` below
   the current ask — true by construction at 72% of fill. Verify it is working via
   `get_option_orders`.
   ⚠️ **`gtc` is mandatory.** With no hard close this stop is the position's only
   protection; a `gfd` stop expires at 16:00 and leaves it naked overnight. If the
   broker rejects `gtc` on a stop_market, DO NOT fall back to `gfd` — close the
   position instead and journal the rejection.
   **A position must never sit without a working stop for more than one monitoring
   cycle.**
6. Journal: contract, qty, fill, stop order id, score at entry, and the extremity
   diagnostic row (step 2f) in the "Entry & blocked-signal extremity tracking" table.

## Phase 4 — Monitoring loop (during market hours)

Cadence: wake **every 5 minutes** (`interval_open_minutes` / `interval_flat_minutes`,
`send_later` with `delay_minutes: 5`), whether a position is open or flat — schedule
the next wake first thing on each wake so a slow turn never breaks the chain.
**Schedule exactly ONE wake per turn.** Do not stack backup wakes.

**Why 5 minutes and not 1 (revised 2026-08-14, owner decision — supersedes the
2026-08-12 fallback-wake pattern).** The 1-minute cadence was never actually
achieved. The 2026-08-14 audit (`logs/analysis/2026-08-14_wake_delivery_audit.md`)
measured requested vs. actual delivery for every trigger that day and found:
- Real delivery to this session was **one wake per ~30–50 minutes**, no matter how
  many triggers were queued — scheduling more did not buy more wakes.
- **Two triggers were stranded permanently** (never fired, still `enabled: true`
  hours past due), and one of them was the fallback backup wake armed specifically
  to catch this failure mode. The mitigation stranded alongside what it was
  protecting.
- Deliveries arrived **out of order** — a 13:46Z trigger fired at 15:00 while a
  14:13Z trigger created later never fired at all.
- Cost that day: a fully-qualifying SPY put entry met the persistence gate at
  11:21 ET and sat qualifying for 9 minutes inside the entry window, unactioned
  (`logs/journal/2026-08-14.md`).
So: **minute-resolution comes from the replay, not from the poll rate.** Polling
less often but replaying every intervening minute recovers the same signal
detection, just after the fact, and stops the trigger backlog that caused the
stranding. 5 min is a first step down from 1; the 2026-08-12 audit found ~20-min
cadence delivers with sub-1-minute lag, so if 5 min still shows stranding or
>10 min lag, step down further toward 20 and journal the change.

**On EVERY wake, backfill the full interval since the last check and run a
per-minute score replay** (`strategy_calc.py score` against progressively truncated
bars, one call per minute in the gap) — never trust the endpoint score alone. At a
5-minute cadence this is the normal path, not an exception: a threshold crossing and
a completed 3-minute persistence run can both begin and end entirely inside one
interval. Check `strategy_calc.py persistence` whenever any replayed minute crosses
`entry_threshold`, and compare the resulting entry time against `entry_latest`
before treating it as actionable. Worked examples: the 8/10, 8/11, 8/12 journals,
and the 8/14 reconstruction.

**If a wake arrives more than ~15 minutes late, or you notice the chain has gone
dark**, treat it as a possible stranded trigger: replay the whole gap as above, and
say so plainly in the journal (time dark, what the replay found, whether anything
was missed). Do not respond by scheduling extra overlapping wakes — that is what
made 8/14 worse.

On each wake, for every open position:
1. `get_option_positions` (nonzero) + `get_option_quotes` on held contracts;
   `get_option_orders` to confirm each position's stop is still working.
   Track the position's peak price (highest mid/mark seen since entry, initialized
   to the fill on the first wake) — needed for step 1b.
1b. **(REMOVED 2026-08-07 — owner decision.)** The trailing-stop check that lived
   here (activation at +10% unrealized, 14pp trail; real rule 2026-07-30 →
   2026-08-07) is gone: it never fired across the 8 forward trades and is
   near-redundant under the +30% take-profit — see
   `logs/analysis/2026-08-07_forward_review.md` finding 4. Keep tracking the
   peak in step 1 (`stops --peak` still reports `peak_gain_pct`, diagnostic
   only), but the resting stop is NEVER moved: it stays at the static −28%
   `stop_trigger` for the life of the position.
2. Stop filled (static −28% level) → journal exit P&L. If time < `entry_latest`,
   entries used < `max_trades_per_day`, and caps permit: re-run Phase 3 re-check
   (funded from settled cash only).
2b. **Time stop / DTE floor:** if the position has been held `max_hold_trading_days`
   (3) trading days, or the contract has reached `min_dte_at_exit` (3 DTE), close it
   now — cancel the stop, sell at a bid-pegged limit, re-peg every 2 min until flat.
3. Mid ≥ take-profit level → cancel that position's stop (`cancel_option_order`),
   sell at bid-pegged limit, confirm fill, journal.
4. Safety net: position open but **no working stop** (cancelled/rejected/expired) and
   mid ≤ the static −28% `stop_trigger` → sell immediately at marketable limit;
   else re-place the stop at `stop_trigger`.
5. Realized P&L for the calendar day ≤ −`daily_loss_halt_usd` → no further entries
   today, and close any position still open. Ordering: a resting stop that already
   filled IS the exit; the halt only closes what is still open when it trips.
5b. **Shadow-leg tracking (record, never act).** On the SAME minute-cadence wakes,
   also quote the open position's shadow 0DTE contract and log its mid, plus whether
   it would have hit the −30% stop or +60% target by now. Its exits are evaluated
   against ITS OWN fill, not the 7DTE fill. **Its target stays fixed at +60% even
   after the 2026-07-29 change to `take_profit_pct` (now 30%)** — pass
   `stops --fill <shadow_fill> --take-profit-pct 60` explicitly, never the bare
   config default, so the shadow leg remains the same ±30/60 geometry as the
   original `logs/backtest/dte_comparison.md` study (otherwise the live 7DTE-vs-
   shadow-0DTE comparison stops being apples-to-apples). A 0DTE shadow must be
   marked closed at 13:30 ET (it would expire), even though the real 7DTE position
   carries on — record its terminal value there and stop tracking it that day.
6. **Signal-decay diagnostic (record, never act).** While a position is open,
   recompute the held symbol's score each wake and run
   `python3 scripts/strategy_calc.py decay --entry-score <at entry> --current-score <now>`.
   - Log the FIRST wake where it triggers: time, entry score, current score,
     retained %, reason, and the option's mid at that instant (i.e. what an exit
     there would have realised).
   - **Then keep logging it EVERY MINUTE until the position actually closes** (the
     monitoring loop already wakes every minute while a position is open, so this
     adds no extra wakes). The open question is whether exiting on decay is
     premature — whether the score and the position recover after the trigger. Only
     the post-trigger path answers that, at the same 1-minute cadence the rule would
     actually run at, so a single trigger row is not enough.
   - This must NOT change any exit decision. The static −28% stop, +30% target,
     time stop, DTE floor, daily halt, and the Phase-5 EOD carry gate remain the
     only real exits.
   - Rationale and current evidence: `logs/backtest/signal_decay_test.md` plus
     the forward record in `logs/analysis/2026-08-07_forward_review.md` finding
     6 — it flagged all 3 forward losers early but ALSO fired mid-trade on the
     2026-07-30 winner (≈ net wash if promoted). Still diagnostic-only.
6b. **(REMOVED 2026-08-07 — owner decision.)** The consider-exit / trailing-stop
   activation rule that lived here (real 2026-07-30 → 2026-08-07) was removed
   along with step 1b — see step 1b's note and
   `logs/analysis/2026-08-07_forward_review.md` finding 4. `consider_exit_pct`
   and `trail_stop_distance_pct` no longer exist in `config/strategy.yaml`.
7. Journal one *general status* line per wake only when something changed (fill,
   exit, stop re-placed) or every 10th wake otherwise — a full 3-hour minute-cadence
   log of "no change" lines drowns the journal. **This throttle does NOT apply to the
   step-6 signal-decay rows: once a position is open, log one decay row every minute
   without exception.** They are the dataset; gaps make the premature-exit question
   unanswerable. Keep them in their own table so they do not swamp the narrative.

## Phase 5 — End-of-day verification (15:45 ET)

Positions are NOT flattened wholesale. This phase makes them safe to carry
overnight — or closes the ones too weak to carry (step 1c).
1. `get_option_positions` (nonzero). For EVERY open position:
   a. `get_option_orders` → confirm a stop-market sell exists in a working state
      (queued/confirmed) with `time_in_force: gtc` and the correct quantity.
   b. Missing / cancelled / rejected / `gfd` → re-place it as GTC immediately. If it
      cannot be placed as GTC, CLOSE the position before 16:00 rather than carry it
      unprotected.
   c. **EOD carry gate (REAL, gating — added 2026-08-07, owner decision).** Run
      `strategy_calc.py stops --fill <avg_fill>` and compare the current mid to
      `eod_carry_floor` (config `eod_carry_min_unrealized_pct`, −14% = half the
      stop width). Mid ≤ floor → CLOSE the position now (cancel stop, sell at
      bid-pegged limit, re-peg every 2 min, flat before 16:00) instead of
      carrying: that close to the −28% stop there is too little cushion against
      an overnight gap through the trigger (June data showed stop fills as bad
      as −56/−58% — `logs/backtest/take_profit_30pct_test.md`). Mid above the
      floor → carry as designed with the GTC stop. Unvalidated threshold
      (adopted from `logs/analysis/2026-08-07_forward_review.md` finding 7 /
      open question 1); journal the gate decision either way, every day a
      position is open at 15:45. In dry_run, journal the hypothetical close.
      (Also confirm the resting stop still sits at the static −28%
      `stop_trigger` — the trailing stop was removed 2026-08-07, so any stop at
      a different price is stale and must be re-placed at `stop_trigger`.)
2. Check the time stop and DTE floor: anything that will breach
   `min_dte_at_exit` or `max_hold_trading_days` before the next session must be
   closed now, not next morning.
3. Journal: open positions, their stop order ids, DTE remaining, days held.

## Phase 6 — Journal & push (after Phase 5)

1. Complete the journal: fills, P&L (realized, per trade and total), signal history,
   deviations from playbook.
2. `git add logs/ && git commit` (message: `journal: YYYY-MM-DD <summary>`) and
   `git push -u origin claude/robinhood-day-options-strategy-y8eskp`
   (retry ×4, backoff 2/4/8/16s).
3. End the session. Do not leave wakes scheduled past `failsafe_check`.

## Journal template

```markdown
# SPY 7DTE Journal — YYYY-MM-DD
mode: <dry_run|live>  |  settled cash at open: $X  |  VIX: X (prior close X, Δ X pts/day / X%, accel X pts/day², diagnostic only)
## Regime
gap SPY: X% · news veto: none|<reason> · tradeable: yes|no
## Volatility baseline
VIX: X · rv5: X% · rv10: X% · rv20: X%
## Signal history
| time | SPY | QQQ | IWM | market | note |
## Volatility snapshot per signal (diagnostic — does not gate entries)
| time | contract | taken? | IV | rv10 | IV/RV | delta | theta | vega | outcome |
## Shadow 0DTE leg (diagnostic — never traded)
| time | 7DTE contract | 0DTE contract | 7DTE mid | 0DTE mid | 0DTE qty @ budget | 0DTE stop/TP hit? | 0DTE terminal (13:30) |
(same signal, same direction, same strike where available — the forward
out-of-sample answer to whether 7DTE beat 0DTE, or whether June was just choppy)
## Signal-decay tracking (diagnostic — does not gate exits)
| time | contract | entry score | score now | retained % | triggered | option mid | hypothetical P&L if exited here |
(first trigger, then EVERY MINUTE until the position actually closes — the
post-trigger path at live cadence is what tells us whether decay exits are premature)
## Score velocity tracking (diagnostic — does not gate entries)
| time | score now | score prev | Δminutes | points/min | direction | notable? | accel (pts/min²) | accel direction | notable accel? |
(added 2026-07-27; row only when notable or direction flips — level-only entry_threshold
can miss fast moves that never cross +/-40; see STRATEGY.md for the clamp caveat)
## 0DTE option price velocity tracking (diagnostic — never trades, does not gate anything)
| time | leg | mid now | mid prev | Δminutes | $/min | direction | notable? | accel ($/min²) | accel direction | notable accel? |
(added 2026-07-27; two FIXED legs per session — nearest-the-money 0DTE call and put,
picked once at Phase 3 step 0 regardless of the sentiment score's direction; row only
when notable/notable_accel or a direction flip; extends the shadow-0DTE-leg snapshot
into a continuous series to test whether 0DTE premium velocity/acceleration says
anything the 7DTE-traded signal or the sentiment-score velocity doesn't)
## Entry & blocked-signal extremity tracking (diagnostic — does not gate entries)
| time | contract/direction | status | score | drive component | drive_pct | drive clamped? | range_pos (raw 0-1) | extremity |
(added 2026-07-31, extended 2026-08-01 to include blocked signals; one row per
qualifying signal — `ENTERED`, `blocked - time gate`, or `blocked - liquidity/
contract filter` — see PLAYBOOK.md Phase 3 step 2f and STRATEGY.md for rationale.
Tests whether entering into an already-clamped/exhausted drive reading correlates
with worse outcomes than entering into a strong-but-not-yet-clamped one, AND
whether blocked signals are systematically less extreme than the entry that
eventually follows. n is tiny, not enough to act on)
## Trades
| # | contract | qty | fill | stop id | exit | exit px | P&L | reason |
## End of day
flat by: HH:MM · realized P&L: $X · trades: N/2 · deviations: none|<list>
```
