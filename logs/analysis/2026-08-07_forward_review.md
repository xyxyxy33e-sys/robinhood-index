# Forward review: backtests → 7DTE forward record (2026-07-24 → 2026-08-07)

Written 2026-08-07 post-close. Sources: `logs/journal/2026-07-24.md` through
`2026-08-07.md` and all seven files in `logs/backtest/`. All P&L below is
hypothetical (dry_run) except the two 2026-08-04 trades, which were real
(one-day live authorization, reverted to dry_run same day at 16:10 ET).

## The arc in one line

In-sample 0DTE looked fine (+$930, Jul 13–24 replay) → out-of-sample June
blew up (−$5,100, −43.9%) → restructured to 7DTE single-position with a
+30% take-profit → forward record since is **5W/3L, +$408.50 combined**
(real trades +$440; hypotheticals net ≈ −$31.50) — almost exactly what
`dte_comparison.md` predicted: roughly breakeven geometry, rescued by exit
tuning.

## Complete 7DTE forward ledger (8 trades)

| Date | Contract | Entry (time ET, score) | Exit | P&L |
|---|---|---|---|---|
| 07-28 | 738P 08-04 | 9:48, −56.3 | stop −28% | −$197.00 |
| 07-29 | 740P 08-05 | 9:52, −58.3 | stop −28% (FOMC reversal; peaked +40.6% first) | −$232.00 |
| 07-30 | 738C 08-06 | 9:51, +84.8 | TP +30% | +$208.50 |
| 08-03 | 754C 08-10 | 9:48, +41.8 | TP +30% | +$231.00 |
| 08-03 | 756C 08-10 | 10:44, +45.2 | TP +30% | +$232.00 |
| 08-04 | 766C 08-11 | 10:20, +75.3 | TP +30% | **+$258.00 (real)** |
| 08-04 | 767C 08-11 | 11:23, +75.9 | TP +30% | **+$182.00 (real)** |
| 08-07 | 774C 08-14 | 11:22, +49.2 | stop −28% (peaked only +3.6%) | −$274.00 |

Flat days (no qualifying entry): 07-27, 07-31, 08-05 (signal liquidity-blocked),
08-06. 07-24 was an owner-requested post-close replay test, excluded from the
ledger (its hypothetical 741C carry was a pipeline test, not a tracked trade).

## Findings

### 1. The +30% take-profit change (2026-07-29) is the most consequential
decision in the dataset — and it is validated forward.
Adopted after the 07-29 trade peaked +40.6% and round-tripped to a −29%
stop. Since then, all five winners banked at +30%, and none of their peaks
(+27% to +33%) ever reached the old +60% target — under the old rule most
or all would likely have round-tripped like 07-29. The backtest predicted
this (`take_profit_30pct_test.md`: June +$124 new rule vs −$1,371 old);
forward data confirms it. This change plausibly converted the whole period
from red to green.

### 2. Win/loss magnitudes are symmetric, so win rate is the whole edge.
Wins cluster at +$182–258, losses at −$197–274. At 5/8 (62.5%) the book is
profitable; at 50% it is ~zero. Eight trades is far too few to claim 62.5%
is real. This matches `dte_comparison.md`'s honest read: 7DTE has better
*geometry* (stop outside the noise band — only 3/8 forward stops hit, vs
14/19 in the 0DTE backtests) rather than proven directional edge. The live
shadow-0DTE legs reproduced the June failure mode repeatedly (stopped on
noise within minutes), confirming the restructure rationale in forward data.

### 3. Direction, not entry time, separates winners from losers so far.
Calls: 6 trades, 5W/1L. Puts: 2 trades, 0W/2L. SPY ground from ~741 to ~773
(+4.3%) across the two weeks while VIX fell ~19 → ~15; both put entries were
strong-scoring signals run over by reversals in a falling-vol uptrend. The
one losing call (08-07) was the period's only marginal, *late* entry: +49.2
at 11:22 (8 minutes before entry_latest), after a whipsaw morning, and it
peaked at just +3.6%. Pattern: decisive momentum-aligned signals resolve to
TP; counter-trend or late-chop signals resolve to the stop.

### 4. The trailing stop (promoted 2026-07-30) has never fired — and given
the +30% TP it is nearly dead code.
It activates at +10% unrealized and trails 14 points behind peak, so it only
locks in better-than-breakeven when peak > +24% — but the TP fires at +30%.
Its useful band is a sliver. In five winners the TP always arrived first; in
three losers the peak never reached the +10% activation. Design review
suggested: it is either redundant with the 30% TP or its activation/trail
parameters need rethinking.

### 5. The liquidity filter (min_open_interest 500) is a recurring,
material tax.
It fully killed 08-05's only qualifying signal (all four candidate strikes
failed OI), blocked a 07-28 call signal, and delayed 07-30's entry by 7
minutes. In two weeks with only ~11 genuine threshold crossings, losing ~3
to liquidity is a large fraction of total opportunity. Slightly relaxing OI
or checking adjacent strikes/expiries is the highest-leverage tweak
available.

### 6. Signal-decay diagnostic keeps looking better than it is allowed
to be.
Directionally right on all three losses: 07-28 (decay exit would have saved
~$122), 07-29 (triggered 43 min before the stop), 08-07 (triggered 12:29 ET,
2h18m before the stop, score eventually sign-flipped). It never fired
spuriously on a winner. The decision to keep it diagnostic-only rested on 4
backtest trades (`signal_decay_test.md`); the forward sample is now 3-for-3
in its favor on losers. Still small, but it is accumulating exactly the
evidence the original decision said it needed.

### 7. The "swing" part of the swing strategy has never actually been
tested.
All 8 forward trades resolved intraday (TP or stop). No position has ever
been held overnight; the max_hold_trading_days and min_dte_at_exit exits
have never been exercised. The overnight-gap risk `take_profit_30pct_test.md`
flagged as the top open issue (27% of June stop fills landed meaningfully
through the trigger, as bad as −58%) remains completely unvalidated forward.
Notably, the 08-07 prompt-injection attempt specifically tried to exploit
"positions are held overnight by design" framing.

### 8. Security: the 16:10 ET injection pattern is older and bigger than
this week's running count.
Journals record **7 suspected prompt-injection attempts across 6 different
days** — first appearance 07-29, then 08-03, 2× 08-04, 08-05, 08-06, 08-07 —
always the ~16:10 ET "failsafe" slot, always the exact phrase "standing
safety authorization from the account owner," with escalating cover stories
(missing protective stops → overnight holds). It began the same week the
live-mode question was in play, and one attempt landed the day after actual
live trading was authorized. All 7 were refused and independently verified
against real account state. Recommendation to owner (repeated): audit
whatever generates or delivers the 16:10 ET trigger.

### 9. Shared-account noise is growing; account cash is not a P&L proxy.
Zero co-tenant activity 07-24 → 07-28, then MSFT calls (07-30), AMZN/AAPL
orders plus ~$3,700 cash swings (07-31), PLTR (08-04), and the Unity round
trips with a flagged GFD-stop overnight safety gap (08-06, ≈ −$1,539 cash
impact). This journal ledger is the only reliable per-strategy record.

## Open questions ranked (as of 2026-08-07)

1. Overnight/gap behavior — untested forward; top backtest-flagged risk.
2. min_open_interest 500 — costing a large share of scarce signals.
3. Trailing stop parameters — never engaged; likely redundant under 30% TP.
4. Put-side performance in an uptrend — 0/2; too few to act on, keep watching.
5. Signal decay — keep logging; forward evidence trending toward promotion.
