# PLAYBOOK — Daily SPY 7DTE Session Runbook

Audience: the Claude session fired by the `0dte-morning-session` routine at 9:00 ET.
Execute top to bottom. All times US/Eastern; MCP timestamps are UTC.
Load parameters from `config/strategy.yaml` — never hardcode them.

## Prime directives

1. **`mode: dry_run` → never call `place_option_order` / `cancel_option_order`.**
   Journal the exact order you *would* have placed (contract, qty, price).
2. **Never exceed a `risk:` limit.** When any check is ambiguous, don't trade.
3. **Every open position carries a WORKING GTC stop-market at all times.** With no
   intraday hard close this is its only protection. A `gfd` stop expires at 16:00
   and leaves it naked overnight — if GTC cannot be placed, CLOSE instead.
4. **Always run Phase 5 (EOD) and Phase 6 (journal + push)**, whatever else happened.
5. **Poll every 5 min and REPLAY the interval — never trust the endpoint score.**
   Resolution comes from the replay, not the poll rate. One wake per turn; never
   stack backup wakes. Schedule with `send_later`, never Bash sleep.

---

## The check-in (used by Phases 3 and 4 — the core loop)

Every wake runs these six steps. `scripts/checkin.py` does the mechanical parts.

1. **Clock + lag.** Record wall clock and lag vs. the scheduled time. Log it in the
   journal's Wake delivery log. If lag > 30 min, step the cadence down to 20 min and
   journal it (see Changelog: 2026-08-14).
2. **Backfill.** `get_equity_historicals` (SPY, `interval=minute`) from the last
   check. Merge:
   `python3 scripts/checkin.py merge --date YYYY-MM-DD --symbol SPY` (stdin:
   `HH:MM open high low close volume` per line, UTC). Idempotent — safe to overlap.
3. **Replay the interval.**
   `python3 scripts/checkin.py scan --date YYYY-MM-DD --symbol SPY --since HH:MM`
   Prints every minute at/over `entry_threshold` and exits 2 if any. A crossing plus
   a complete persistence run can begin and end inside one 5-min interval, so this is
   the check that makes a slower poll safe. **Before `entry_latest` a crossing is
   actionable** → run `strategy_calc.py persistence`, verify the entry time is at or
   before `entry_latest`, then go to Phase 3 step 2. **After `entry_latest` it is
   informational only** — no entry is possible for the rest of the day.
4. **Position (if any).** `get_option_quotes` on the held contract, plus
   `get_option_historicals` for its own minute bars across the interval — the option's
   own high/low is what determines whether an exit triggered, not the endpoint quote.
   `python3 scripts/checkin.py exits --fill F --low L --high H --mid M` → stop / TP /
   carry-floor verdict, exits 2 on a stop or TP touch. Also confirm the GTC stop is
   still working (`get_option_orders`) and track peak mid since entry.
5. **Diagnostics.** While a position is open, log a signal-decay row EVERY wake:
   `strategy_calc.py decay --entry-score <at entry> --current-score <now>`. Record it
   even when it does not trigger — the post-trigger path is the dataset.
6. **Journal, commit, push, schedule ONE next wake.** Decay rows every wake; a general
   status line only when something changed or every ~10th wake.
   **Pre-emptive cadence tightening (added 2026-08-22, see
   `logs/analysis/2026-08-22_weekly_review.md`):** during Phase 3, if `|score|` is within
   15 points of `entry_threshold` (i.e. `|score| >= entry_threshold - 15`) on the latest
   bar, schedule the next wake at 3 min regardless of whether anything has crossed yet.
   A complete P=3 run takes only 3 minutes to open and close — tightening only *after* a
   crossing is observed is structurally too late, since the run can finish before that
   tightened wake ever fires. This was the difference between 8/21 (tightened
   pre-emptively at +30.6, no miss) and four prior misses (8/14, 8/18, 8/19, 8/20) where
   a full qualifying run opened and closed inside a single wake gap that started from a
   score not yet flagged as "close." Revert to normal cadence once the score pulls back
   outside the 15-point band with no live run.

**Wake prompt template** — keep it short; the journal is the source of truth, the
prompt is a pointer. Prompts go stale within minutes and have twice carried claims
already retracted in the journal.

```
[wake — Phase N, <cadence>, position OPEN|FLAT]
THE JOURNAL IS AUTHORITATIVE (logs/journal/YYYY-MM-DD.md). Scheduled for HH:MMZ.
Position: <contract, id, fill, stop, TP, carry floor, peak> | or: FLAT
Run the standard check-in (PLAYBOOK "The check-in"). Then schedule ONE 5-min wake.
<one line of anything genuinely new since last wake>
mode: dry_run|live
```

---

## Phase 0 — Bootstrap (9:00)

1. `git fetch` + checkout `claude/robinhood-day-options-strategy-y8eskp` (the default
   branch may be empty — this branch is the source of truth).
2. Read `config/strategy.yaml`. Confirm it's a weekday and markets are open; journal
   and stop on a holiday.
3. `get_accounts` → confirm the configured account is `agentic_allowed=true`,
   `option_level_2`+. If not: journal, notify, stop.
4. `get_portfolio` → record start-of-day settled cash (the sizing base).
5. `get_option_positions` (nonzero) → **carried-over positions are expected.** For each:
   confirm a WORKING GTC stop (`get_option_orders`, state queued/confirmed); re-place if
   missing. Record entry date + expiration so Phase 4 can apply the time stop / DTE floor.
   **Carry-cushion reconciliation (added 2026-08-22):** if yesterday's Phase 5 journaled a
   carry-cushion dollar figure (previous step's diagnostic), compare it to today's actual
   overnight move: `gap_dollars = (today's first regular-session mid) − (yesterday's Phase
   5 mid)`, signed against the stop direction (a move toward the stop is negative). If
   `|gap_dollars| > cushion`, journal it explicitly as a **cushion breach** (whether or not
   the stop itself was touched — a breach that didn't reach the stop is still evidence the
   gate underpriced the move). If `|gap_dollars| ≤ cushion`, journal that the cushion held.
   This is what turns "did the gate work" from a hand-reconstruction across two journal
   files into a single line read off Phase 0 every morning a position was carried.
6. Create `logs/journal/YYYY-MM-DD.md` from the template below.

## Phase 1 — Pre-open (9:00 → 9:29)

1. `get_news` → scan for a regime veto (FOMC, CPI, NFP, major geopolitical shock).
   `get_indexes` / `get_index_quotes` → VIX level.
1b. **VIX day-over-day (diagnostic).** Last two daily closes via `get_index_historicals`
   (interval=day, ~7 days back). Then:
   `strategy_calc.py velocity --score-now <today VIX> --score-prev <T-1> --minutes-elapsed 1
   --velocity-prev <T-1 minus T-2> --watch-threshold 5.0 --accel-watch-threshold 3.0
   --pct-watch-threshold 15.0`
   `--minutes-elapsed 1` means "one day-step", NOT one minute — passing 1440 dilutes the
   rate so nothing ever flags. Journal level, change, accel, pct. Rationale lives in
   config next to `vix_change_watch_pts_per_day`.
2. Poll SPY/QQQ/IWM minute bars (`bounds=extended`, from 09:00 ET). Each poll returns
   the full tape since 9:00, so polling every ~7 min gives complete coverage.
2b. **Volatility baseline (every day, traded or not).** 21 daily SPY closes →
   `strategy_calc.py rvol --closes "<oldest,...,newest>"`. Record rv5/rv10/rv20 next to
   VIX — this is the denominator of the IV/RV ratio.
3. ~9:28: write bars + prior closes + VIX to `data/YYYY-MM-DD-bars.json`, run
   `strategy_calc.py score`. Journal the pre-open score and any veto.
4. Regime filter tripped → journal `NO-TRADE DAY: <reason>` and skip to Phase 5 timing.

## Phase 2 — Opening drive (9:30 → 9:44)

Wake ~9:37 and ~9:44. Refresh bars, re-run the score, journal the evolution. **No orders.**
If `|score| >= entry_threshold` fires before `entry_earliest`, it is still a real signal —
log an extremity row with status `blocked - time gate` (columns per Phase 3 step 2d).

## Phase 3 — Entry (entry_earliest 9:45 → entry_latest 11:30)

Run **the check-in** every 5 min. On a crossing:

1. **Persistence gate (REAL, gating).** `strategy_calc.py persistence --input <bars>
   --symbol SPY` — entry may proceed only if `entry_gate_met` is true (|score| ≥
   threshold, same sign, for `entry_persistence_min` consecutive minutes, measured on
   backfilled minute bars, not polls). Entry must be at or before `entry_latest`
   (11:30:00 inclusive). If the gate blocks an otherwise-qualifying signal, log an
   extremity row `blocked - persistence gate` and track it like a shadow trade — that
   record is the forward evidence for re-tuning P. **A blocked signal does not consume a
   `max_trades_per_day` slot.**
2. **Contract selection.**
   a. `get_option_chains` → chain id.
   b. Expiration: nearest listed **≥ `dte_target` (7) calendar days** out; if +7 is a
      weekend/holiday take the next, never below +6. `get_option_instruments`.
   c. `get_option_quotes` → pick the contract clearing **`target_delta_min`/`max`
      (0.45–0.55, use the REAL delta from the quote, not a strike offset), `min_premium`,
      `max_spread_pct_of_mid`, `min_open_interest`, `min_volume`**. If nothing
      clears, log `blocked - liquidity/contract filter` and resume re-checks — this also
      does not consume a trade slot.
   d. **Record two diagnostics for every qualifying signal, entered or not:**
      - *Volatility snapshot* — IV, delta, gamma, theta, vega, and IV/rv10. We are long
        premium, so paying above realised IV is a structural headwind; historical IV is
        not retrievable, so this forward record is the only way to test it.
      - *Extremity* — status, `drive` value and `drive_pct`, whether drive is clamped
        (`|drive_pct| >= 0.30`), and `range_pos` (near-low <0.15, near-high >0.85). Tests
        whether entries systematically land at range extremes. n is tiny; diagnostic only.
   e. **Size against PAPER equity (owner, 2026-08-17 — this is a test run).**
      `strategy_calc.py paper` → take `sizing_budget_usd`
      (`min(max_premium_per_trade_usd, paper_equity_usd)`), then
      `strategy_calc.py size --price <ask> --budget <sizing_budget_usd>`.
      Paper equity **compounds**: `data/paper_ledger.json` = $11,858.54 starting
      snapshot + one row per realized paper trade. At current equity the $1,000 cap
      binds, so sizing is unaffected by the other strategies' cash reservations.
      **Do not block an entry on low real `buying_power`** — nothing is being funded.
      A `HALT` field in the `paper` output means equity is exhausted; stop entering.
      **If mode is ever live**, this step inverts: `get_portfolio` in the same wake,
      budget = `min(max_premium_per_trade_usd, live buying_power)`, and `size` returning
      0 → log `blocked - insufficient buying power` (no trade slot consumed). Never bend
      sizing, the stop, or any `risk:` limit to fit a shrunken budget, and never free up
      cash by touching another strategy's orders.
   f. **Shadow 0DTE leg (record, never trade).** Same underlying/direction/strike at
      today's expiry (nearest strike if absent). Record ask, mid, IV, greeks, and the
      contracts a full budget would buy. This is the forward answer to 7DTE-vs-0DTE.
3. **Place (live only).** `review_option_order` (limit buy at mid rounded up one tick,
   gfd) → any blocking alert aborts the trade. Then `place_option_order` with a fresh
   `ref_id`.
4. **Fill management.** Poll `get_option_orders` after ~2 min. Unfilled → cancel, re-place
   at ask once. Still unfilled → cancel, journal, resume re-checks. Partial fills count as
   filled (stop qty = filled qty).
5. **Immediately after fill (live only): place the resting stop.**
   `strategy_calc.py stops --fill <avg_fill>` → **`stop_market`, sell-to-close,
   `stop_price = stop_trigger`, NO `price` param, `time_in_force: gtc`,
   `market_hours: regular_hours`**, fresh `ref_id`. Verify it is working.
   ⚠️ **`gtc` is mandatory** (directive 3). If the broker rejects GTC on a stop_market, do
   NOT fall back to `gfd` — close the position and journal the rejection.
   **A position must never sit without a working stop for more than one wake.**
6. Journal: contract, qty, fill, stop order id, score at entry, extremity row.

## Phase 4 — Monitoring (market hours, every 5 min)

Run **the check-in**. Exits, in priority order:

1. **Stop filled** (`stop_trigger_frac`, static −28%) → journal exit P&L. If still before `entry_latest` and
   under `max_trades_per_day`, a Phase 3 re-check is permitted (settled cash only).
2. **Time stop / DTE floor** — held `max_hold_trading_days` (3) trading days, or contract
   at `min_dte_at_exit` (3 DTE) → close now: cancel stop, sell bid-pegged limit, re-peg
   every 2 min until flat.
3. **Mid ≥ take-profit** (`take_profit_pct`, +30%) → cancel that position's stop, sell
   bid-pegged limit, confirm fill, journal.
4. **Safety net** — position open with no working stop and mid ≤ `stop_trigger` → sell
   immediately at marketable limit; otherwise re-place the stop at `stop_trigger`.
5. **Daily halt** — realized P&L ≤ −`daily_loss_halt_usd` → no further entries and close
   anything still open. A resting stop that already filled IS the exit; the halt only
   closes what is still open when it trips.
6. **The resting stop is NEVER moved.** It stays at the static −28% `stop_trigger` for the
   life of the position. Track peak (`stops --peak`) as a diagnostic only.
7. **Shadow-leg tracking (record, never act).** Quote the position's shadow 0DTE contract
   each wake; log its mid and whether it would have hit −30% / +60% **against its own
   fill**. Pass `stops --fill <shadow_fill> --take-profit-pct 60` explicitly — the shadow
   keeps the original ±30/60 geometry so the comparison stays apples-to-apples. Mark it
   closed at 13:30 ET (it would expire) and stop tracking it that day.
8. **Signal-decay (record, never act).** Per the check-in, every wake. It must not change
   any exit decision — the real exits are the five above plus the Phase 5 carry gate.

## Phase 5 — EOD verification (15:45 ET)

Positions are **not** flattened wholesale. This makes them safe to carry — or closes the
ones too weak to.

1. `get_option_positions` (nonzero). For EVERY open position:
   a. `get_option_orders` → confirm a stop-market sell, working (queued/confirmed),
      `time_in_force: gtc`, correct quantity, priced at the static `stop_trigger` (any
      other price is stale — re-place it).
   b. Missing / cancelled / rejected / `gfd` → re-place as GTC now. If it cannot be placed
      as GTC, CLOSE before 16:00 rather than carry unprotected.
   c. **EOD carry gate (REAL, gating).** `strategy_calc.py stops --fill <avg_fill>` →
      compare mid to `eod_carry_floor` (`eod_carry_min_unrealized_pct`, −14%, half the stop
      width). **Mid ≤ floor → CLOSE now** (cancel stop, bid-pegged limit, re-peg every
      2 min, flat before 16:00): too little cushion against an overnight gap through the
      trigger. Above → carry with the GTC stop. Journal the decision either way, every day
      a position is open at 15:45. In dry_run, journal the hypothetical close.
      **Carry-cushion diagnostic (added 2026-08-22, see
      `logs/analysis/2026-08-22_weekly_review.md`):** when carrying, journal the cushion
      in dollars (`mid − eod_carry_floor`) explicitly next to the decision. This is what
      Phase 0 the next morning reconciles against — see Phase 0 step 5.
2. Time stop / DTE floor: anything breaching before the next session closes now, not
   next morning.
3. Journal: open positions, stop order ids, DTE remaining, days held.

## Phase 6 — Journal & push

1. Complete the journal: fills, realized P&L per trade and total, signal history,
   deviations.
2. `git add logs/ && git commit && git push -u origin claude/robinhood-day-options-strategy-y8eskp`
   (retry ×4, backoff 2/4/8/16s).
3. End the session. **Do not leave wakes scheduled past `failsafe_check` (16:10).**

---

## Journal template

```markdown
# SPY 7DTE Journal — YYYY-MM-DD
mode: <dry_run|live> | settled cash at open: $X | VIX: X (prior close X, Δ X pts/day / X%, accel X pts/day²)
## Phase 0 — Bootstrap (HH:MM ET)
## Regime
gap SPY: X% · news veto: none|<reason> · VIX X < 35 · tradeable: yes|no
## Volatility baseline
VIX: X · rv5: X% · rv10: X% · rv20: X%
## Signal history
| time | SPY | QQQ | IWM | market | note |
## Wake delivery log
| wake | scheduled | delivered | lag | cadence |
## Volatility snapshot per signal (diagnostic)
| time | contract | taken? | IV | rv10 | IV/RV | delta | theta | vega | outcome |
## Entry & blocked-signal extremity tracking (diagnostic)
| time | contract/direction | status | score | drive | drive_pct | clamped? | range_pos | extremity |
## Persistence gate log (REAL gate)
| time | score | trailing run (min) | gate met? | action |
## Shadow 0DTE leg (diagnostic — never traded)
| time | 7DTE contract | 0DTE contract | 7DTE mid | 0DTE mid | 0DTE qty @ budget | stop/TP hit? | terminal (13:30) |
## Signal-decay tracking (diagnostic — every wake while open)
| time | contract | entry score | score now | retained % | triggered | option mid | hypothetical P&L if exited here |
## Phase 4 — monitoring
| time | note |
## Trades
| # | contract | qty | fill | stop id | exit | exit px | P&L | reason |
## Phase 5 — EOD verification (HH:MM ET)
## End of day
flat by: · realized P&L: $X · trades: N/6 · deviations:
```

---

## Changelog — rules removed or changed (do not re-add without evidence)

Full rationale is in git history and `logs/analysis/`; kept short here so the runbook
stays readable.

- **2026-08-22 — carry-cushion diagnostic added** (Phase 5 step 1c + Phase 0 step 5,
  owner-approved): journal the carry cushion in dollars when carrying, reconcile it
  against the actual overnight move the next Phase 0. Motivated by 8/19's journal
  claiming the carry gate had "failed 2 of 2" when re-reading the underlying events
  (`logs/analysis/2026-08-22_weekly_review.md`) found only one clean miss (8/19) and one
  case where the cushion was eaten but the stop was never threatened (8/17) — the
  comparison had to be hand-reconstructed across two files, which is how the
  overstatement happened. `eod_carry_min_unrealized_pct` (-14%) unchanged — n=2 is still
  too thin to tune against.
- **2026-08-22 — pre-emptive cadence tightening added** (check-in step 6): tighten to
  3 min once `|score|` is within 15 pts of `entry_threshold`, not only after a crossing.
  A weekly review (`logs/analysis/2026-08-22_weekly_review.md`) found 4 wake-latency
  misses in the forward record (8/14, 8/18, 8/19, 8/20) where a full P=3 run opened and
  closed inside one wake gap that started from a score not yet flagged as "close" —
  reactive tightening was structurally too late in all four.
- **2026-08-14 — monitoring cadence 1 min → 5 min; fallback-wake pattern removed.**
  Measured wake delivery: at 1-min cadence the tail reached 181 min; at 5-min it is ~13
  min. Scheduling more triggers did not buy more wakes, and stacked backup wakes were
  themselves delayed. Resolution now comes from replaying the interval, not the poll rate.
  Step-down trigger: any wake >30 min late → 20-min cadence.
  → `logs/analysis/2026-08-14_wake_delivery_audit.md`
- **2026-08-14 — Phase 3 step 0 (two fixed ATM 0DTE reference legs) removed**, along with
  the *Score velocity* and *0DTE option price velocity* tables it fed. Both logged zero
  rows for five consecutive sessions (last data 8/07). The position-linked shadow 0DTE leg
  is retained — it is the one that produced usable evidence (see 8/13).
- **2026-08-07 — trailing stop removed** (`consider_exit_pct` / `trail_stop_distance_pct`).
  Never fired across 8 forward trades; near-dead code under a +30% take-profit.
  → `logs/analysis/2026-08-07_forward_review.md` finding 4.
- **2026-08-07 — EOD carry gate added** (Phase 5 step 1c) and **`min_open_interest`
  500 → 250**; **persistence gate P=3 added** (Phase 3 step 1).
- **2026-07-29 — take-profit 60% → 30%.** The shadow 0DTE leg deliberately keeps +60%.
- **Hard close removed** (owner decision): positions are held across sessions. Directive 3
  exists because that removal made the resting GTC stop the only overnight protection.
