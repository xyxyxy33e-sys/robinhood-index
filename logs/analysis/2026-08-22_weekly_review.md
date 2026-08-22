# Weekly review — 2026-08-17 to 2026-08-21

Scope: five trading sessions (Mon-Fri), re-read in full from `logs/journal/2026-08-17.md`
through `2026-08-21.md`. Goal: separate what the week's own day-by-day framing already
got right from what it overstated or undercounted, and turn the difference into concrete
process changes — not just repeat "flagged for the owner" a third time.

## The week in one table

| date | entries | outcome | paper P&L |
| --- | --- | --- | --- |
| 8/17 | 0 (position carried from 8/14) | TP hit 13:39 ET | **+$214.00** (+30.06%) |
| 8/18 | 1 (SPY 769P, 10:59 ET) | carried overnight | — |
| 8/19 | 1 (SPY 774C, 10:59 ET) + carried-in close | 769P gap-through stop 09:30 ET; 774C intraday stop 12:52 ET | **-$314.00**, **-$200.00** |
| 8/20 | 0 | entry window closed, no crossing survived to be caught | $0.00 |
| 8/21 | 0 | entry window closed, SPY never crossed +/-40 | $0.00 |

Net: **3 realized trades, -$300.00, paper equity $11,858.54 -> $11,558.54 (-2.53%)**. Two
losers, one winner, both losers landed close to the sample size where "the exit stack
worked as designed but the trade lost anyway" and "something is actually wrong" are hard
to tell apart (n=3). No conclusion drawn from that sample here beyond what's below.

## What actually improved this week (no action needed — already done)

**Fill-modeling now distinguishes overnight-gap exits from intraday-touch exits**, and
the distinction earned its keep immediately: the 8/19 gap-through stop (769P, modeled at
the $3.00 opening print) landed -34.35%, 6.35pp beyond the -28% stop design; the same
day's intraday-touch stop (774C, modeled at the $2.58 trigger) landed -27.93%, almost
exactly on target. That's not a coincidence of one trade each — it's the two conventions
being exercised back-to-back on the same day with visibly different overshoot, which is
about as clean a validation as a forward record gets. Nothing to change here.

## Finding 1 — wake-latency missed entries: undercounted, and the fix already exists

Each day's journal cites the prior misses it happens to remember, and the running tally
drifted: 8/20's write-up called itself "the third wake-latency miss (8/14, 8/19,
now this)". **Re-reading the actual 8/18 journal turns up a fourth, uncounted instance**:
a P=3 put-side run opened 14:13Z and closed 14:15Z (10:13-10:15 ET) inside a ~10-minute
wake gap, with the contract (769P) confirmed clearing every filter. That miss wasn't
folded into any later day's count because "8/14 10:13" and "8/18 10:13" share a
time-of-day and read, on a skim, like the same reference.

**Corrected count: 4 confirmed wake-latency misses in the forward record** — 8/14 10:13
ET, 8/18 10:13 ET, 8/19 14:46-48Z, 8/20 14:15-17Z. All four share the same shape: a
complete P=3 qualifying run opens and closes entirely inside one polling gap, and the
contract that would have been entered independently clears every liquidity/delta filter
(verified, not assumed, in three of the four — 8/14's wasn't independently re-checked).

The good news: **the fix has already been informally invented and used, just not
written down.** On 8/21, cadence was tightened to 3 minutes *before* any crossing, purely
because the score was closing in on the threshold (+30.6, 9.4pt margin) — and it held
through the rest of the window without another miss. That's the right instinct: a miss
happens when a full P=3 run (3 minutes) fits inside a gap that's wider than 3 minutes,
which nominal-5-minute cadence allows by construction whenever delivery lags even
slightly. Tightening only *after* a crossing is detected is structurally too late — the
gate can open and close before the tightened wake ever fires. Tightening *before* the
crossing, while the score is still approaching, is the only version of this that can
actually work.

**Action taken:** codified pre-emptive tightening into `docs/PLAYBOOK.md`'s check-in
section (see diff), formalizing what 8/21 already did once ad hoc: cadence steps down to
3 minutes whenever `|score|` is within 15 points of `entry_threshold` on either side,
not only after a threshold crossing has already been observed. This doesn't eliminate
the failure mode (a wake could still lag past 3 minutes, and a run can still complete in
under 3 minutes from a standing start well clear of threshold), but it converts the
"tighten reactively" pattern that's been reinvented ad hoc into a standing rule, which is
the difference between a miss that gets caught by luck (8/21) and one that doesn't
(8/14, 8/18, 8/19, 8/20).

## Finding 2 — EOD carry gate: real finding, but the week's own framing inflated it

8/19's journal describes the carry gate as having "failed to prevent post-carry damage
in 2 of its last 2 relevant tests." Re-reading both underlying events:

- **8/14 -> 8/17**: gate passed at $3.52 vs a $3.06 floor ($0.46 cushion). Overnight gap
  ate the cushion and then some (open $2.95, low $2.89, -16.6% from the pre-carry mark).
  The stop ($2.56) was never threatened, and 8/17's own end-of-day write-up said this
  explicitly: *"the outcome vindicates carrying... not a case for changing
  `eod_carry_min_unrealized_pct`."*
- **8/18 -> 8/19**: gate passed at $4.535 vs a $3.93 floor ($0.61 cushion). Overnight gap
  blew through the stop entirely, -34.35% vs the -28% design, a real loss directly
  attributable to gap risk the gate didn't see coming.

That's **one clean miss (8/19) and one case where the cushion measurement was wrong but
the outcome wasn't damaged (8/17)** — not two failures. Calling it "2 of 2" by 8/19
overstates the evidence relative to what 8/17's own same-day analysis concluded about
itself. The underlying mechanism critique still holds — a flat-market snapshot distance
to a floor doesn't price the overnight gap distribution, and n=2 carries is too thin to
tune `eod_carry_min_unrealized_pct` (-14%) against regardless of which way you count the
misses. **Recommendation: keep collecting real carry events before touching the number.**
What would materially help is turning "gap size relative to cushion" into an explicit
diagnostic logged at Phase 5 every time a position carries (cushion in dollars, and then
the next morning's actual gap in dollars, side by side) — right now that comparison has
to be reconstructed by hand from two different days' journals, which is exactly how the
"2 of 2" overstatement happened. Not implemented yet — flagged below as an open question
rather than done unilaterally, since it changes what Phase 5 logs.

## Finding 3 — the entry_latest (11:30 ET) cutoff: the flagged concern doesn't hold up

8/17 and 8/18 both raised, in their "Open for the owner" sections, that the tradeable
window and the strongest signal keep missing each other. Checking each cited instance
against slot availability at the time:

- **8/17, 13:12 ET signal** (1h42m after `entry_latest`): the carried-in position was
  still open (didn't close until the 13:39 ET take-profit) — `max_concurrent_positions: 1`
  means this signal could not have been taken **regardless of what entry_latest was set
  to**. Extending the window would not have produced a second trade here.
- **8/18, 10:13 ET miss**: happened *inside* the window (09:45-11:30 ET), with the slot
  free. This is a wake-latency problem (Finding 1), not a window-length problem —
  extending `entry_latest` doesn't address a miss that occurred an hour before the
  window closes.

**Neither cited instance is actually evidence for extending the entry cutoff.** The
pattern that generated the recurring flag — "the tradeable window and the tradeable move
keep not lining up" — is real in the sense that good moves keep happening outside the
window, but the mechanism blocking entry in both cases was something other than the
window's length (slot occupancy, wake latency). Extending `entry_latest` would trade a
longer risk-taking window for a benefit that, on this week's own evidence, wouldn't have
materialized. **Recommendation: leave `entry_latest` at 11:30 ET.** This reverses the
direction the open question had been drifting; flagged to the owner as a question below
since it's a change from what two prior sessions' write-ups implied, not because the
data supports moving the number.

## Finding 4 — signal decay: evidence continues to argue against ever gating on it

8/17 alone gave six decay triggers, all six of which reversed, on a trade that finished
+30%. Combined with the 8/07 review's finding that decay "helped 3 losers" but would
have killed a winner, the forward record now has one more full day of same-direction
evidence (all-reversal) and zero days of decay correctly calling a bad trade early
without also killing at least one good one. No change needed — it's already
diagnostic-only — but this is worth stating plainly as an accumulating result, not just
a repeated caveat: **the case for promoting decay to a gating rule has gotten weaker, not
stronger, since 8/07.**

## Decisions (owner, 2026-08-22)

1. **EOD carry gate diagnostic — approved and added.** `docs/PLAYBOOK.md` Phase 5 step 1c
   now journals the carry cushion in dollars every time a position carries; Phase 0 step 5
   now reconciles it against the actual overnight move the next morning and journals
   either "cushion held" or an explicit **cushion breach** (even if the stop itself wasn't
   touched). No change to `eod_carry_min_unrealized_pct` (-14%) — still too little data
   (n=2) to tune the number itself; this only makes the next several carries
   self-documenting instead of requiring hand-reconstruction across two files.
2. **`entry_latest` stays at 11:30 ET — confirmed.** `config/strategy.yaml` updated with
   the 2026-08-22 reconfirmation and pointer to this doc.
