# JUNE 2026 — OUT-OF-SAMPLE BACKTEST OF THE PRODUCTION CONFIG

**Result: −$5,100 over 21 trading days. −43.9% of the account. Max drawdown −$5,855.**

This is the first test of the strategy on data that was never used to choose any
parameter. Every earlier result (+$930 / +$690 / +$548 / +$239 across four variants)
came from Jul 13–24, the same ten days the entry time, premium floor and other
settings were selected on. June is clean.

Config tested (current production): entries 9:45–11:30, |score| ≥ 40 per symbol,
$1,000/position, ≤3 concurrent, $3,000 combined, 6 entries/day, $0.15 premium floor,
stop −30%, TP +60%, $1,000 daily halt, flat 13:30.

## Daily results

| Day | P&L | Day | P&L | Day | P&L |
|---|---|---|---|---|---|
| 06-01 | −$1,165 ⛔ | 06-11 | −$1,044 ⛔ | 06-23 | $0 |
| 06-02 | −$562 | 06-12 | −$471 | 06-24 | −$827 |
| 06-03 | **+$1,190** | 06-15 | **+$1,187** | 06-25 | −$587 |
| 06-04 | +$540 | 06-16 | **+$1,393** | 06-26 | +$803 |
| 06-05 | −$1,545 ⛔ | 06-17 | +$523 | 06-29 | −$21 |
| 06-08 | −$851 | 06-18 | −$810 | 06-30 | −$30 ⛔ |
| 06-09 | −$1,171 ⛔ | 06-22 | −$1,728 ⛔ | | |
| 06-10 | +$76 | | | **TOTAL** | **−$5,100** |

⛔ = daily loss halt tripped (6 of 21 days)

7 winning days (avg +$816) · 13 losing (avg −$832) · 1 flat.
Best +$1,393 · worst −$1,728. No recovery: the equity curve ends at its low.

## The dominant failure mode: the three symbols are one bet

SPY, QQQ and IWM are driven by the same market factor, so their scores cross the
threshold *together*. The "3 concurrent positions, mixed directions allowed" design
was meant to diversify; in practice it concentrates. On 06-08, 06-18, 06-22 and
06-24 the model fired all three symbols long at the same checkpoint — at the local
high — and every position stopped in the same reversal:

- 06-08: 3 calls at 11:00, all stopped → −$851
- 06-18: 3 calls at 11:00, all stopped → −$810
- 06-22: 3 calls at 10:00 at the day's high, then two shorts into the bounce → −$1,728
- 06-09: 3 calls at 9:45, all stopped in the *same* 14:00Z bar → −$1,171

At $1,000/position this is ~$900 of loss per synchronized reversal. The concurrency
limit is not a risk control here — it is a leverage multiplier on a single view.

## Why June differs from July

July 13–24 contained two strong sustained trend days (07-23, 07-24) that produced
most of the profit. June was dominated by intraday mean reversion: momentum crossed
the threshold at local extremes and reverted before the +60% target. The strategy is
a momentum-continuation bet; June did not continue. Ten days of July was not enough
to reveal that — which is exactly what out-of-sample testing is for.

## Sizing amplified, it did not cause

Re-running June at the old $500/position (halving every P&L) gives ≈ −$2,550. The
doubled size doubled the loss; it did not create it. The signal itself was negative
in June under any sizing.

## Rules gaps found (real, unresolved)

1. **Halt vs. resting stop ordering.** When the daily halt trips while a position is
   still open, the spec does not say whether the resting stop or the halt liquidation
   wins. Flagged independently on 06-05 ($464 swing), 06-22, and 06-30 ($125 swing).
   Must be pinned down before live trading.
2. **Regime filter is SPY-only.** On 06-18 QQQ gapped +2.03% and IWM +1.62% — both
   beyond the 1.5% limit — but the day traded because SPY gapped +0.92%. All three
   then faded their gaps and all three stopped. A per-symbol gap check would have
   blocked those entries.
3. **Per-symbol lock costs the best signals.** Repeatedly (06-01 IWM at −98, 06-10,
   06-17 IWM at 48–59) the strongest score of the day was blocked because that
   symbol's prior position was still open. The 30-minute checkpoint grid overstates
   this vs the live 1-minute cadence, but the effect is real.

## Data fidelity caveats

- Option history for June resolves only to **30-minute** bars; 10- and 5-minute bars
  return `interpolated: true` (synthetic). Exit timing is therefore coarser than the
  July run's 10-minute replay. Where a 30-minute bar contained both the stop and the
  TP, ordering was resolved from the underlying's 5-minute path (mandatory step);
  agents reported this was needed on only a handful of trades and was unambiguous
  each time.
- Entries at 9:45 fall mid-bar and were priced as mean(open, close) of the 13:30Z
  bar, which was frequently a single flat print — the softest fills in the run.
- Entries were evaluated at 5 checkpoints (9:45/10:00/10:30/11:00/11:30) rather than
  the live 1-minute cadence.
- **The VIX arm of the regime filter could not be evaluated** — no historical VIX is
  available through the Robinhood tools. Days were scored as if VIX passed. June 5
  and June 9–10 were violent enough that a VIX > 35 reading is plausible; those three
  days alone account for −$3,761. If the VIX filter would have blocked them, June
  improves to ≈ −$1,339 — still negative.
- No commissions, fees or slippage modeled (~$0.08/contract round trip would add a
  few hundred dollars of additional loss across ~80 trades).

## Conclusion

Two months of real data now disagree: July +$930, June −$5,100, net ≈ −$4,170 over
31 trading days. The June sample is twice the size and was not used for tuning, so it
is the more trustworthy of the two. The strategy as specified does not demonstrate an
edge, and the current sizing turns an unproven signal into account-threatening
exposure (−43.9% in one month; the $1,000 halt fired on 6 of 21 days and did not
prevent it, because a halt caps one day, not a losing streak).

**Recommendation: return `mode` to `dry_run` before Monday.** Options if you want to
continue: (a) paper-trade live for a few weeks and compare to these replays;
(b) fix the identified rules gaps (halt ordering, per-symbol gap filter) and the
concentration problem (e.g. one position at a time, or require symbols to disagree)
and re-test on fresh out-of-sample data; (c) drop position size back to $250–500
while the signal is unproven. This is the account owner's decision — the config was
left exactly as set.
