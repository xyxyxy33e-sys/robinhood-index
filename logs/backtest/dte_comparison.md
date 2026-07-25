# DTE comparison — 0 vs 3 vs 7 days to expiry

Controlled experiment: the SAME 19 June SPY entries (same day, same entry minute,
same strike, same direction, same ±30/60 exit rules, same $1,000 budget). Only the
expiration changes. Real Robinhood 30-minute option bars throughout.

| | Return on capital | P&L | Winners | Stop fired | Median MAE | Median MFE | Reached +60% |
|---|---|---|---|---|---|---|---|
| 0DTE | −5.6% | −$1,009 | 5/19 | **14/19** | — | — | 5/19 |
| 3DTE | **−9.0%** | −$1,355 | 7/19 | 10/19 | **−28.3%** | +24.4% | 2/19 |
| 7DTE | **+1.8%** | +$261 | **9/19** | 6/19 | −17.4% | +13.4% | 2/19 |

Return-on-capital is the honest metric: higher premiums at longer DTE mean
`floor($1000/premium)` deploys less capital (0DTE $17,975 → 7DTE $14,868), so raw
dollar P&L flatters the longer-dated variants.

## The mechanism (the durable finding)

The ±30/60 geometry cannot be inherited across DTE, because the option's intraday
return distribution scales with gamma:

- **0DTE** — high gamma. A 1-point SPY move swings a ~$1.50 option ~27%. The +60%
  target is genuinely reachable (5/19 hit it), but the −28% stop sits *inside* the
  noise band, so it fires on 14/19 trades regardless of direction.
- **3DTE** — median MAE lands at −28.3%, i.e. *exactly on the stop trigger*. This is
  the worst possible calibration: the stop fires ≈half the time essentially at
  random. Confirmed by sub-cent margins across the sample (06-05 748P cleared its
  trigger by <$0.01; 06-18 747C by $0.005; 06-08 745C by $0.04). Meanwhile only
  2/19 reached +60%. Keeps 0DTE's stop vulnerability, loses its convexity.
- **7DTE** — low gamma. Median MAE −17.4%, comfortably inside the stop, so noise
  stop-outs mostly stop (14 → 6). But median MFE is only +13.4%: the +60% target is
  unreachable, so 11/19 trades simply ran to the 13:30 hard close.

## Why this ranking is probably regime-dependent — do NOT treat it as settled

7DTE won in **June**, which was choppy and mean-reverting; there, surviving noise
beats amplifying moves. **July** was the opposite: the two best days of that window
(07-23, 07-24, +$1,276 combined) came from exactly the 0DTE convexity that 7DTE
gives up. A strategy that wins by not being stopped out will underperform on trend
days, and vice versa.

Sample: 19 trades, one month, and the third DTE variant fitted to it. 3DTE's −9.0%
in particular carries very wide error bars given how many of its trades sat within a
cent of flipping outcome.

## What this does NOT show

None of these variants demonstrates an edge. 7DTE converts a clear loss into roughly
breakeven (+$261 on ~$15k deployed). It removes a structural handicap — a stop
calibrated inside the instrument's noise band — but the underlying signal is
unchanged and was not predictive in June.

## Structural consequences if 7DTE were adopted

1. Positions no longer self-liquidate at expiry. The 13:30 hard close and 13:31
   failsafe exist because an unclosed 0DTE expires or auto-exercises that day; with
   7DTE an unclosed position simply carries overnight — introducing gap risk the
   strategy has never had, and the failsafe's rationale needs rewriting.
2. Premiums are 3–7× higher, so a $1,000 budget buys 1–2 contracts. Integer
   granularity wastes 10–30% of the budget and makes sizing coarse.
3. The exit geometry would need re-deriving for the compressed return distribution
   (agents independently suggested roughly −15%/+20% bands). **Deriving those from
   these same 19 trades would be curve-fitting** — it needs fresh data.

## Forward test now running (added 2026-07-25)

Because this ranking is likely regime-dependent, the dry-run journal now carries a
**shadow 0DTE leg**: every live signal resolves BOTH the traded 7DTE contract and the
equivalent 0DTE contract (same direction, same strike where available), and both are
tracked — entry price, IV, greeks, per-minute mid, stop/target hits, and a 13:30
terminal value for the 0DTE side (it expires; the 7DTE position carries on). The
shadow leg is never traded.

This produces on live, out-of-sample signals exactly the controlled comparison this
document ran on June — the difference being that June was a single mean-reverting
month I had already examined from many angles, whereas this accumulates forward.
`contract.shadow_dte` in the config turns it off.

## Recommendation

Do not adopt 3DTE; it is dominated on both axes. 7DTE is the most promising change
tested so far *because it has a mechanism*, not because of its P&L. Before any config
change, re-run the 7DTE experiment on July (option history there resolves to
10-minute bars, giving better exit timing than June's 30-minute) to see whether the
advantage survives a trending regime. Config left unchanged at 0DTE.
