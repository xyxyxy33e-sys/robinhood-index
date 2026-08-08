# Entry persistence / confirmation gate — three-leg test (2026-08-07)

Prompted by the 2026-08-07 stop-out: the day's entry (+49.2 at 11:22 ET, 8
min before the window close, after a whipsaw morning) was the forward
period's only losing call, while both 8/4 winners entered at nearly the
same clock time on signals that had held ≥40 for hours. Question: does
requiring the signal to PERSIST before entry improve outcomes? Owner
approved the test ("intuitively makes sense"), then chose the parameter
before full results landed: **P=3 minutes, adopted 2026-08-07** ("Make P=3
for now, the longer it waits, is avoiding the upward trend"). This doc
records all three legs and the honest status of the evidence for and
against that choice.

## Rule definition (as adopted)

`entry_persistence_min: 3` (config), enforced via `strategy_calc.py
persistence`: an entry additionally requires |score| ≥ `entry_threshold`
for P consecutive minutes with the same sign, measured on **backfilled
1-minute bars** — not on polling checks, so the gate is cadence-independent
(a session polling every ~7 minutes backfills bars and evaluates the
trailing minute series). Entry at/after the P-th qualifying minute; entry
must be at or before `entry_latest` (11:30:00 ET inclusive, later
exclusive). Persistence runs count only regular-session minutes (≥ 9:31
ET); pre-open scores never seed a run. Blocked signals are journaled with
hypothetical outcomes and do not consume trade slots.

## Leg 1 — forward period, exact minute-level replay (7/28 → 8/7)

Score series recomputed at every regular-session minute from the repo's own
stored 1-minute bars (`data/*.json`), then re-priced by a backtest agent
with real Robinhood option data (5-minute bars — the finest REAL
granularity; minute bars for these contracts are interpolated placeholders).
Entries: nearest-$1 ATM at signal time, exits −28% stop / +30% TP / time
stop / DTE floor. Note the sim is NOT a like-for-like re-run of the live
sessions (minute cadence vs sparse polling; ATM vs delta-band strikes).

| Variant | Trades (closed) | W/L | Closed P&L | Open marks | Total |
|---|---|---|---|---|---|
| Actual recorded ledger | 8 | 5W/3L | +$408.50 | — | +$408.50 |
| P=1 (minute cadence, no gate) | 12 | 7W/5L | +$762.46 | −$42 | +$720.46 |
| P=5 | 7 | 5W/2L | +$583.14 | −$38 | +$545.14 |
| P=10 | 7 | 5W/2L | +$675.48 | — | +$675.48 |
| P=15 | 6 | 5W/1L | +$936.16 | — | +$936.16 |

Key structural facts (robust):
- Every winning day's signal (7/30, 8/3, 8/4) held ≥40 continuously — all
  persistence levels keep the winners, delaying entries 2–16 min.
- The 1–2-minute spikes were all bad: 8/5 9:57 (−$193 when priced), 8/6
  10:18 (−$150), 8/7 10:25 (underwater). Minute-cadence P=1 would have
  taken ~−$343 of phantom losses the real sessions dodged only by sparse
  polling luck.
- 7/29 is a regime lesson: at minute cadence every variant TP'd the put
  early (+$200-206) where the real session's later sparse entry rode into
  the FOMC reversal for −$232 — and then the sim's re-entries gave it back.
- The variant RANKING is not significant: the re-pricing agent documented
  ~8 separate cents-level boundary flips (e.g. 8/7 P=1 survived its stop by
  4.9 cents; 7/30 P=15 missed stopping out by 4 cents before its TP) any
  one of which reorders the table. P=15's edge is mostly omission of the
  four losing days — regime-dependent, 9 days, one strong uptrend.
- P=3 (adopted; not in the priced grid — chosen by the owner mid-test):
  entries interpolate between P=1 and P=5 — 9:47/9:49/9:47-9:49 on the
  winner days (2–4 min delay, mostly the same 5-min fill buckets as P=5),
  skips ONLY the 8/6 spike, takes 8/5 at 9:59 (≈ P=1's −$193 outcome) and
  8/7 at 11:10 (≈ P=10's −$268 outcome or the open underwater mark).
  Estimated forward total ≈ +$350–400 — roughly the actual ledger,
  slightly below P=5/P=10/P=15 on THIS sample because it admits 8/5 and
  8/7. Its value proposition is the spike filter at minimal chase cost,
  not sample-P&L maximization.

## Leg 2 — June 2026, checkpoint-quantized confirmation (strict version)

Two consecutive |score|≥40 checkpoints (9:45/10:00/10:30/11:00/11:30 —
i.e. a 15–30 min persistence requirement, the STRICT end of the family).
Regenerated from real 5-min equity / 30-min option bars.

- Recorded baseline +$124 (14 trades, 7W) → confirmed +$628 (6 trades,
  4W). Skipped 5 losers, forfeited 2–3 winners.
- **The margin is noise**: +$702 of it is one trade surviving its stop by
  $0.02 on a 30-minute bar; −$554 is another missing its target by $0.10.
  Remove the single lucky flip and the confirmed variant UNDERPERFORMS
  (≈ −$113). Baseline itself reconciled only partially (score regeneration
  reproducible to ±1–6 pts; four June signals sat within that noise of the
  threshold — itself a finding about how knife-edge the 40 gate is).

## Leg 3 — July 13–24 2026, same strict checkpoint rule

- Known baseline −$2,059 (0/8) → confirmed −$651 (0/3). Entire benefit =
  trading 3 times instead of 8–10 in a week with zero winners.
- **Direct counter-example**: the regenerated SPY-only series' one correct
  entry (7/23 10:30 put, +$198 to target) is exactly the trade the
  confirmation rule DELAYED into a −$190 loser. Strict confirmation cost
  ~$388 on the only day the signal was right.
- Also independently re-confirmed two prior findings: 9:45 single-checkpoint
  morning extremes are unreliable, and the 7/22→23 overnight gap (three
  −56–58% stop fills) dominates the week regardless of entry rule.

## Synthesis and decision

1. **Strict confirmation (15–30 min, P≈15) is REJECTED** despite the best
   raw forward number (+$936): both historical legs show its gains are
   quantization noise (June) or trading-less-in-a-losing-week (July), it
   delayed July's only correct entry into a loser, and its forward edge is
   omission of losing days in a 9-day sample.
2. **Some persistence beats none**: the 1–2-minute spike entries were
   losers in every observed instance (8/5, 8/6, 8/7 first-touches), and
   minute-cadence polling with NO gate would have taken all of them. A
   small P is cheap insurance: winners' signals all survived it with 2–4
   minute delay.
3. **P=3 adopted (owner decision, chase-priority explicit).** The analyst
   recommendation was P=5 (filters everything P=3 filters, plus 8/5's
   3-minute 9:59 spike, at +2 min extra delay); the owner weighted
   trend-chasing cost higher and chose 3. At P=3 vs P=5 the observable
   difference on the whole forward sample is ONE trade (8/5, ≈ −$190
   hypothetical — which the OI filter would likely have blocked anyway at
   the old 500 threshold, and might not block at the new 250). Reasonable
   people land either way at this sample size; the choice is journaled as
   deliberate.
4. **Forward evidence collection is built in**: every persistence-blocked
   signal gets journaled with its hypothetical outcome (PLAYBOOK Phase 3
   step 1), so P can be re-tuned on real forward counterfactuals instead
   of another backtest round-trip.

## Caveats (the usual, plus this test's own)

All three legs share: no spread/slippage/fees, no historical greeks
(ATM≈0.50 proxy), bar-quantized exits (5-min forward, 10-min July, 30-min
June — NOT mutually comparable), and knife-edge sensitivity documented in
each leg (multiple trades within cents of flipping). The forward leg is 9
days of one regime; June is one mean-reverting month; July is one chop-
into-selloff fortnight. P=3 specifically has NO priced backtest of its own
— it is an interpolation choice inside a family whose strict end failed
validation and whose loose end (P=1) underperforms it on spike days.
Treat `entry_persistence_min: 3` exactly like every other recently-adopted
parameter: provisionally correct, journaled, and owed a verdict from the
forward blocked-signal record it now generates.

Working artifacts: `/tmp/.../scratchpad/confirm_local/` (minute score
series, replay.py), `.../june_confirm/`, `.../july_confirm/` (agent
inputs/outputs; ephemeral, summarized fully above).
