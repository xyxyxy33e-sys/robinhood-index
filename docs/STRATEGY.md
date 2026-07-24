# Strategy Specification — 0DTE Index Options Momentum

## Objective

Capture intraday directional moves in the major index ETFs using same-day-expiration
options, with strictly bounded downside (30% premium stop) and no exposure past
13:30 ET — before the afternoon theta cliff and power-hour reversals.

## Why these rules

- **0DTE long options** give high convexity on a correct directional call, but decay
  fastest in the afternoon. Exiting by 13:00 keeps the trade in the window where
  delta, not theta, dominates P&L. (Close window per config `schedule:`.)
- **No entries in the first 15 minutes**: the 9:30–9:45 range is dominated by opening
  auctions and stop-hunting; signals fire on the *resolution* of that range.
- **30% stop-loss**: a fixed fraction-of-premium stop is the only stop type that works
  on 0DTE (underlying-based stops are too twitchy given gamma). It caps a single
  trade's loss at `0.30 × max_premium_per_trade` ≈ $120 at default sizing.
- **Sentiment before signals**: minute-level pre-market tape from 9:00 onward gives
  gap context and directional drift before the open, so the open-drive signal starts
  with a prior instead of reacting cold.

## Composite sentiment score

Computed by `scripts/strategy_calc.py score` from minute bars (fetched via
`get_equity_historicals`, `bounds=extended`, `interval=minute`). Range −100…+100 per
symbol. Components (weights in parentheses):

| Component | Definition | Full-scale at |
|---|---|---|
| Overnight gap (25) | pre-market price at ~9:28 vs prior official close | ±0.50% |
| Pre-market momentum (25) | net drift of minute closes 9:00 → 9:28 | ±0.30% |
| Opening drive (35) | price now vs 9:30 open (computed 9:37 and 9:44) | ±0.30% |
| Range position (15) | where price sits in the day's high-low range, rescaled to ±1 | — |

Each component is `clamp(x / full_scale, −1, +1) × weight`; the symbol score is the
sum. The **market score** (mean across the universe) is journaled for context, but
entries are decided per symbol: each universe symbol whose |score| clears the
threshold qualifies independently, in its own direction. Divergent books (e.g. SPY
call + IWM put on a large-cap/small-cap split day) are allowed.

Qualitative overlay: the session also pulls headline news (`co-invest get_news`) at
9:00. News does not move the numeric score; it can only *veto* a trade (e.g., FOMC
decision day at 14:00, CPI print at 8:30 that whipsawed futures) — the veto and
reason must be journaled.

## Regime filters (no-trade days)

Skip the entire day, journaling the reason, when any of:
- |overnight gap| on SPY > `gap_limit_pct` (1.5%) — gap days mean-revert unpredictably
- VIX > `vix_max` (30) — stops get run by noise
- A major scheduled macro event lands inside the trade window (FOMC statement,
  CPI/PCE/NFP released after 9:00 ET)

## Entry rules

1. Time gate: `entry_earliest` (09:45) ≤ now ≤ 11:30 ET. 9:35, 9:45, 9:50 and 10:00
   were all backtested over Jul-13→24; the P&L spread between them was inside noise,
   so this is a judgment call, not an optimum. **9:35 is the one setting ruled out on
   mechanism**: with a single 5-min bar, `drive` and `range_position` measure noise and
   flip sign within 15 minutes.
2. Signal gate, per symbol: |symbol score| ≥ `entry_threshold` (40). Every qualifying
   symbol is a candidate — calls and puts may be held simultaneously.
3. Direction per symbol: score > 0 → **call**, score < 0 → **put**. At most one open
   position per symbol at a time; open candidates in order of |score| until
   `max_concurrent_positions` or `max_total_premium_usd` is reached.
4. Contract: today's expiration, delta in [0.35, 0.45] (slightly OTM), premium ≥
   `min_premium` ($0.15/share — cheaper contracts are spread-dominated; skip the
   entry rather than stepping strikes), bid/ask spread ≤ 10% of mid, open interest
   ≥ 500, volume ≥ 100.
5. Size per position: `floor(max_premium_per_trade / (ask × 100))` contracts, minimum
   1 — skip the symbol if even 1 contract exceeds the per-position budget ($500), the
   combined-premium cap, or remaining settled cash.
6. Order: limit buy at the mid, rounded up one tick; if unfilled after 2 minutes,
   re-peg to the ask once; if still unfilled after 2 more minutes, cancel and
   re-evaluate the signal from scratch.

## Exit rules (first hit wins)

Exits are evaluated per position, on a **1-minute monitoring cadence** — both while
positions are open and while flat (signal re-checks), per `monitoring:`.

| Exit | Mechanism |
|---|---|
| −30% stop | Resting stop-limit sell placed immediately after entry fill: trigger at 72% of fill price, limit at 65%. Server-side — survives even if the session dies; the 1-min loop is the backup, not the primary. |
| +60% take-profit | Checked every minute. If mid ≥ 160% of fill: cancel the stop, sell at bid-pegged limit. (Not resting — Robinhood allows only one working sell against a position.) |
| Hard close | From `hard_close_start` (13:00), deadline `hard_close_deadline` (13:30): cancel resting stops, sell everything with marketable limits (bid − 1 tick), confirm fills, retry until flat. |
| Daily loss halt | Realized day loss ≥ `daily_loss_halt_usd` → close everything, no re-entry. |

Re-entries (up to `max_trades_per_day` total entries) are allowed after an exit if
the time gate still holds, the symbol re-qualifies, concurrency/premium caps permit,
and the trade is funded from still-settled cash (never same-day sale proceeds —
good-faith-violation rule).

## Sizing & account constraints

- Account: Robinhood cash account (no margin, no PDT restrictions, but T+1 settlement
  on option sale proceeds — hence the proceeds-reuse rule).
- Default budget: $500 premium per position (user rule: single position < $500), up
  to 3 concurrent positions (one per symbol), $1,500 combined premium, 6 entries/day.
  Worst normal day with 6 full stops ≈ −$900, which is also the `daily_loss_halt`
  cap (~7.8% of the account's $11.6k).
- Agentic API is single-leg only: long calls and long puts. No spreads, no shorts.

## Known failure modes (accepted)

- A fast gap through the stop can fill worse than −35% or (rarely) leave the
  stop-limit unfilled; the monitor loop market-closes any position whose mid is below
  the stop trigger with no working stop order.
- Signals near threshold on chop days will produce stop-outs; the daily halt bounds it.
- If every session-scheduling mechanism fails simultaneously, the 13:31 failsafe
  routine is the last line; worst case an ITM 0DTE auto-exercises — the hard-close +
  failsafe redundancy exists precisely to make this improbable.
