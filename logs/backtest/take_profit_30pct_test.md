# +30% take-profit vs the old +60% — June & July SPY 7DTE

**Result: directionally supportive on June (the only sample where the mechanism
actually occurred), a null result on July, and one clearer finding neither
month's target level explains — overnight gap risk.**

Prompted by 2026-07-29 live trading: SPY 740P went from +40.6% unrealized
(12:15 ET) to a −28.96% stop-out (14:45 ET) on an FOMC-driven reversal,
never approaching the old +60% target. `take_profit_pct` was lowered to 30
that day (`consider_exit_pct: 10` added as a diagnostic alongside it — see
`config/strategy.yaml`, `docs/STRATEGY.md`). This tests that change against
real data, both months replaying the identical price path once under each
rule so old-vs-new is a controlled comparison, not two different samples.

## Method

**July**: SPY-only entries extracted from `2026-07-13_to_2026-07-24.md`'s
already-detailed 0DTE backtest (07-13→07-24, corrected per that doc's
"Correction 1" — 07-21's slot went to IWM, not SPY), re-priced at 7DTE
(nearest expiry ≥7 calendar days, `state=expired` contracts via
`get_option_chains`/`get_option_instruments`, real `get_option_historicals`
bars). 07-24's per-trade detail no longer exists anywhere in the repo (only
the aggregate `+$623, 4 trades` survives) — excluded rather than fabricated.
**8 trades** across 7 days.

**June**: the "19 June SPY entries" behind `dte_comparison.md` were never
preserved at trade level, only as aggregate stats — not reconstructable.
Entries were regenerated from scratch: real SPY bars → `strategy_calc.py
score` at the 5 standard checkpoints (9:45/10:00/10:30/11:00/11:30) across
all 21 June trading days, first `|score|≥40` checkpoint while flat → entry,
re-entries same day allowed per `max_trades_per_day`. **14 trades** across
12 of 21 days (8 days had no qualifying checkpoint).

Both runs sized at `floor($1000/(fill×100))`, min 1 contract, and applied
the same exit ladder: −30% stop (72% trigger), **new** +30% target
(diagnostic +10% consider-exit logged, never acted on), 3-trading-day time
stop, 3-DTE floor — replayed against the identical price path a second time
under the **old** +60% target for direct comparison.

**Data-fidelity, disclosed by both runs, not glossed over:**
- Neither run could get historical greeks/IV for expired contracts (no such
  endpoint exists) — delta was proxied as nearest-$1 ATM strike ≈ 0.50,
  inside the nominal 0.45–0.55 band but not measured.
- July used real 10-minute option bars (finest available for that period).
  June's `10minute` bars returned only synthetic `interpolated:true`
  placeholders this far back — real data only came back at `30minute`,
  which is what was used. June's equity bars were similarly only real at
  `5minute`, not the script's nominal 1-minute schema. **The two months are
  not apples-to-apples with each other in bar granularity**, though each is
  internally consistent and used the finest *real* data available to it.
- No commissions, fees, or slippage modeled beyond the stop-trigger margin.
- No same-bar stop-vs-target ambiguity arose in either sample (unlike the
  tighter 3DTE geometry in `dte_comparison.md`) — noted explicitly since
  the task required a tie-break convention that, in the end, was never
  invoked.

## July — null result (8 trades, 07-14 → 07-24)

| # | Entry | Dir | Contract | Fill | Exit | Reason | Exit px | P&L | Old-rule (+60%) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 07-14 11:30 | Call | 753C exp 07-21 | 4.61 | 07-15 ~12:10 | stop | 3.32 | −$258 (−28.0%) | identical |
| 2 | 07-16 09:45 | Put | 751P exp 07-23 | 4.47 | 07-16 ~10:10 | stop | 3.22 | −$250 (−28.0%) | identical |
| 3 | 07-17 09:45 | Put | 741P exp 07-24 | 5.73 | 07-17 ~10:00 | stop | 4.13 | −$160 (−27.9%) | identical |
| 4 | 07-20 09:45 | Call | 749C exp 07-27 | 4.90 | 07-20 ~10:10 | stop | 3.53 | −$274 (−28.0%) | identical |
| 5 | 07-21 10:30 | Call | 747C exp 07-28 | 5.28 | **07-23 open** | **gap-through stop** | 2.28 | −$300 (−56.8%) | identical |
| 6 | 07-22 10:00 | Call | 749C exp 07-29 | 5.32 | **07-23 open** | **gap-through stop** | 2.34 | −$298 (−56.0%) | identical |
| 7 | 07-22 11:30 | Call | 749C exp 07-29 (same contract as #6 — see caveat) | 5.63 | **07-23 open** | **gap-through stop** | 2.34 | −$329 (−58.4%) | identical |
| 8 | 07-23 11:00 | Put | 738P exp 07-30 | 6.79 | 07-24 ~10:50 | stop | 4.89 | −$190 (−28.0%) | identical |

**0/8 wins. Total P&L identical under both rules: −$2,059.** Peak unrealized
gain across all 8 trades topped out at +23.3% (trade 8) — nothing ever got
near +30%, let alone +60%, so the target level never entered the picture.
The 30-vs-60 comparison genuinely has no signal in this window; it isn't
evidence the change is neutral, it's evidence this week never produced the
pattern the change targets.

Trade #7 note: entered the same contract as #6 at 11:30 the same day — under
the *current* `max_concurrent_positions: 1` this second entry likely
couldn't happen live while #6 was still open. Replayed anyway to match
`dte_comparison.md`'s prior methodology (which also didn't enforce the
concurrency cap); treat #7 as a parallel-signal test, not a literal scenario.

## June — the mechanism shows up directly (14 trades, 12 of 21 days)

| # | Entry | Score | Dir | Strike/Exp | Fill | Qty | New (+30%) exit | Reason | New P&L | Old (+60%), same path | Old reason | Old P&L |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 06-02 11:00 | +41.0 | Call | 760/06-09 | 4.86 | 2 | 06-03 open (gap) | **gap stop** | −$486 (−50.0%) | identical | gap stop | −$486 (−50.0%) |
| 2 | 06-03 09:45 | −46.2 | Put | 756/06-10 | 4.73 | 2 | 06-04 ~10:00 | target | **+$284 (+30.0%)** | 06-04 ~13:00 | stop | −$264 (−27.9%) |
| 3 | 06-05 09:45 | −72.3 | Put | 750/06-12 | 5.94 | 1 | 06-05 ~12:00 | target | +$178 (+30.0%) | 06-05 ~12:30 | target | +$356 (+59.9%) |
| 4 | 06-08 11:00 | +62.4 | Call | 745/06-15 | 6.37 | 1 | 06-08 ~13:00 | stop | −$178 (−27.9%) | identical | stop | −$178 (−27.9%) |
| 5 | 06-09 09:45 | +77.9 | Call | 746/06-16 | 5.40 | 1 | 06-09 ~10:00 | stop | −$151 (−28.0%) | identical | stop | −$151 (−28.0%) |
| 6 | 06-10 11:00 | −42.7 | Put | 733/06-17 | 8.18 | 1 | 06-10 ~11:30 | target | **+$245 (+30.0%)** | 06-11 ~14:00 | stop | −$229 (−28.0%) |
| 7 | 06-12 11:00 | +81.5 | Call | 742/06-22 | 8.24 | 1 | 06-12 ~12:00 | stop | −$231 (−28.0%) | identical | stop | −$231 (−28.0%) |
| 8 | 06-15 09:45 | +52.8 | Call | 753/06-22 | 4.85 | 2 | 06-15 ~12:00 | target | **+$292 (+30.1%)** | 06-16 ~13:30 | stop | −$272 (−28.0%) |
| 8b | 06-16 11:30 | −40.5 | Put | 753/06-23 | 5.81 | 1 | 06-17 open (gap) | gap target | +$221 (+38.0%) | *capital still locked in #8* | — | n/a |
| 9 | 06-22 10:00 | +60.1 | Call | 750/06-29 | 5.40 | 1 | 06-22 ~10:30 | stop | −$151 (−28.0%) | identical | stop | −$151 (−28.0%) |
| 10 | 06-24 11:00 | +59.4 | Call | 740/07-01 | 6.68 | 1 | 06-24 ~13:00 | stop | −$187 (−28.0%) | identical | stop | −$187 (−28.0%) |
| 11 | 06-29 09:45 | +69.3 | Call | 739/07-06 | 5.34 | 1 | 06-29 ~10:15 | stop | −$150 (−28.1%) | identical | stop | −$150 (−28.1%) |
| 12 | 06-29 11:00 | +41.4 | Call | 738/07-06 | 6.28 | 1 | 06-30 open (gap) | gap target | +$273 (+43.5%) | 06-30 ~12:00 | target | +$377 (+60.0%) |
| 13 | 06-30 10:00 | +52.6 | Call | 744/07-07 | 5.50 | 1 | 06-30 ~14:45 | target | **+$165 (+30.0%)** | *capital still locked in #12* | — | n/a |

Trades #3, #12 win under both rules (old captures more, since neither
reversed before +60%). Trades #2, #6, #8, and the counterfactual on #13
(reached +51.8% unrealized before round-tripping to a stop — near-identical
shape to the live 2026-07-29 trade that prompted this test) are the direct
hits: unrealized gain nears or reaches +60%, then fully reverses to a stop
under the old rule, while the new rule locks it at +30%.

| | New (+30%) | Old (+60%), same 14 paths (counterfactual) |
|---|---|---|
| Win rate | 7/14 (50.0%) | 3/14 (21.4%) |
| Total P&L | **+$124** | **−$1,371** |
| Target bound | 7/14 (all winners) | 3/14 |
| Time-stop / DTE-floor bound | 0/14 | 0/14 |

Old-rule total drops to **−$1,566** if you additionally respect that its
capital would still be locked in #8 and #12 when #8b and #13 fire — those
two extra trades the new rule was free to take were both profitable
(+$221, +$165), a secondary argument for the lower target (faster capital
recycling) independent of the stop/target mechanics.

## Combined

| | New (+30%) | Old (+60%) |
|---|---|---|
| July P&L | −$2,059 | −$2,059 (identical) |
| June P&L | +$124 | −$1,371 to −$1,566 |
| **Combined** | **≈ −$1,935** | **≈ −$3,430 to −$3,625** |

The ~$1,500–1,700 combined swing is driven almost entirely by June — July
contributes nothing to the comparison either way.

## Gap risk — the better-supported finding, and it isn't about the target level

**6 of 22 backtested trades (27%) had a meaningfully different realized P&L
than their nominal trigger because of an overnight gap-through:**

- July: 3 of 8 gapped through the stop into the 07-22→07-23 selloff, landing
  at **−56% to −58%** instead of the nominal −28%.
- June: 1 gapped against (trade #1, −50% vs −28% nominal) and 2 gapped in
  its favor (#8b +38.0%, #12 +43.5%, both vs a nominal +30%).

This shows up in *both* independently-run months and is unrelated to
whether the target is 30% or 60% — a stop-market fills at whatever price
prints on the open, not at the trigger, and there is currently no mechanism
that bounds how much worse than −30% an overnight gap can make the loss.
`docs/STRATEGY.md`'s "Known failure modes" section already names this
risk in the abstract; this is now the third and fourth *quantified* instance
of it (on top of the two already implied by the July doc's mention of gap
risk as new to the 7DTE design).

## STOP TUNING caveat

22 trades across two months, one of which (July) contributes a null result
and the other (June) a real but thin signal — only 6 of June's 14 trades
actually diverge between old and new rule; the other 8 stop out identically
regardless of target, same as all of July. Both backtest agents that
produced this data independently pushed back against overclaiming. Read
this as: **the lower target is not obviously wrong and has a demonstrated
real mechanism (round-trip prevention, directly visible in June) — not that
30% is proven optimal.** A fair validation needs more months, ideally
including a trending regime where the target binds more often on the
winning side, before treating 30% as settled. `take_profit_pct` is left at
30 (no revert) — there is no evidence-based reason to move it, per the same
standard `2026-07-13_to_2026-07-24.md` applied to its own checkpoint/floor
variants.

## Recommendation / next steps

1. **Keep `take_profit_pct: 30`.** June supports it where the mechanism
   occurred; July is silent, not contradictory.
2. **Gap risk is unaddressed and better-evidenced than the target question.**
   No config change proposed here — this needs its own investigation before
   touching anything (e.g., is a wider stop-trigger margin, a smaller
   position size, or accepting the risk as the cost of holding overnight
   the right response? each has a real tradeoff worth weighing on its own,
   not bundled into this test). Flagging it as the clear next thing to look
   at, not implementing a fix.
3. Re-run this same regeneration methodology on a trending month (e.g.
   revisit July's original 0DTE window's better trend days, or wait for
   August 2026 data) once available, so the target-level question gets a
   sample where +60% would have plausibly bound more often on winners, not
   just losers.
