# Signal-decay exit — promising, but 4 data points

Idea from an aggregated 0DTE summary: "exit immediately if the trend stalls or
reverses." Every exit we have is price-based on the OPTION (−30% / +60% / time). This
one is thesis-based on the UNDERLYING: leave when the signal that justified the entry
dies. It needs no new data — the score is already recomputed every minute.

**Rule tested (chosen a priori, NOT tuned):** exit at the first post-entry checkpoint
where |score| < 20 (half the entry threshold) or the sign flips vs entry. Exit price =
open of that checkpoint's 30-minute bar. The −30% stop and +60% target still take
precedence if hit strictly earlier.

## Result — June SPY 7DTE, 4 of 19 trades affected

| Day | Entry | Score | → Ckpt | Score | Current | Decay exit | Δ |
|---|---|---|---|---|---|---|---|
| 06-08 | 11:00 | +60.7 | 11:30 | +19.8 | −$191 | −$78 | **+$113** |
| 06-18 | 11:00 | +41.3 | 11:30 | +10.6 | +$7 | −$81 | **−$88** |
| 06-22 | 10:00 | +54.0 | 10:30 | **−28.0** | −$289 | −$250 | **+$39** |
| 06-29 | 09:45 | +67.1 | 10:00 | +18.1 | −$257 | +$16 | **+$273** |

**June SPY 7DTE: +$261 → +$598** (+$337 across 4 changed trades; 3 helped, 1 hurt).

The mechanism behaves as intended. On 06-29 the score collapsed +67 → +18 in fifteen
minutes — thesis dead — while the current rules sat in the position until it bled the
full −30%.

## Why this is NOT being adopted as a rule

1. **Four trades.** Three helped, one hurt. A plausible story attached to an anecdote.
2. **One trade carries ~80% of the gain on a timing technicality.** 06-29's +$273
   depends on the decay exit (that bar's OPEN) preceding the stop (triggered INSIDE
   the same 30-minute bar). Defensible, but it is a within-bar ordering call at coarse
   granularity — the same fragility that made the 3DTE comparison untrustworthy
   (`dte_comparison.md`).
3. **The backtest cannot model the live version.** Production re-checks every minute,
   not every 30. A live decay exit fires far sooner and far more often; that could be
   better (leave faster) or much worse (whipsawed out of positions that recover within
   minutes). This difference is probably larger than the effect measured here.

## What is being done instead
Journaled as a diagnostic during dry-run (`strategy_calc.py decay`, PLAYBOOK Phase 4
step 6): log the first trigger AND the path afterwards until the real exit, so the
premature-exit question can be answered on live per-minute data.

**Distinguish from the FAILED trend idea.** The 5sma/10sma daily filter
(`trend_filter_test.md`) tried to predict DIRECTION and blocked $1,255 of winners.
This one detects thesis DEATH on a position already open. Different mechanisms;
the first failed, this one is untested at scale.
