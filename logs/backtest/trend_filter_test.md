# Test: daily 5sma/10sma trend filter — NEGATIVE RESULT

Idea taken from two external 7DTE SPX credit-spread write-ups (alphacrunching blog;
"Al Losada" webinar deck). Both gate entries on SPX's 5-day SMA vs 10-day SMA on the
daily chart. Hypothesis: use it as a direction gate on our long-option strategy —
calls only when 5sma > 10sma, puts only when below.

Filter computed from daily closes COMPLETED before the entry day (through D−1), so
it is causally clean. Applied to every SPY trade we have replayed.

| Sample | Unfiltered | Filtered | Trades kept | Verdict |
|---|---|---|---|---|
| June SPY 0DTE | −$1,009 | −$1,074 | 7 of 19 | slightly worse |
| **June SPY 7DTE** | **+$261** | **−$994** | 7 of 19 | **much worse** |
| July SPY 0DTE | −$422 | +$130 | 2 of 9 | better |
| Combined 0DTE | −$1,431 | −$944 | 9 of 28 | better, still losing |

## Conclusion: do not adopt

On the current production config (7DTE) the filter blocked 12 trades worth
**+$1,255** and converted a breakeven month into a $994 loss.

**Mechanism.** June's winning trades were counter-trend. On 06-05 the daily trend
read UP so the filter blocked puts — but the two largest 7DTE winners of the month
were exactly those 06-05 puts (+$356, +$568). Our signal is an intraday
extension/momentum reading; in a mean-reverting month its profitable trades fade the
daily trend, and a trend gate removes them by construction.

**Why the idea did not port.** In the source strategies, 5sma > 10sma is not a
direction predictor — it is a risk filter on a SHORT put spread ("don't sell puts
into a downtrend"), protecting a position that profits from decay and drift. We
applied it as a direction predictor for a LONG premium bet. Different objective,
different job; it does not transfer.

**Caveat.** 28 trades total. The July 0DTE column improved, so this is not uniform.
But the improvement in the combined 0DTE column comes largely from cutting 19 of 28
trades — trading less reduces variance in a losing system without creating edge, and
the filtered result is still negative.

## What DID come out of those sources

1. **Theta.** The deck's slide 13: decay from 5 days to expiry is 100%. We spent this
   project buying options inside that window. Our 25.6% June win rate against a 33.3%
   breakeven is the signature of paying theta at its steepest — independent support
   for moving off 0DTE.
2. **Long vs short premium.** Both sources SELL premium (high win rate, small wins,
   tail losses). We BUY it (low win rate, needs a large move). This reframes the win
   rate problem as structural rather than a signal defect.
3. **Neither strategy is implementable here.** `place_option_order` is single-leg
   only — multi-leg spreads are explicitly unsupported via this MCP even on Level 3
   accounts, and the agentic account is Level 2. Selling spreads would require manual
   trading in the Robinhood app plus a Level 3 upgrade.
4. **Treat the sources' statistics with suspicion.** The alphacrunching claim (delta-40
   short strike, 5-wide, $1.60 credit, 80% win rate) implies breakeven at 68% and
   ≈ +$60/trade on ~$340 collateral weekly — roughly 900% annualised, which is not
   plausible for a publicly described method. The webinar deck's own worked example
   shows a put spread ROLLED SEVEN TIMES across a 282-point (6.6%) SPX decline before
   finally expiring worthless: a demonstration of deferring a loss, not of edge.
   Neither source discloses max drawdown, trade count, or worst trade.
