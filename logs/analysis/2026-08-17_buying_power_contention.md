# Buying-power contention — 2026-08-17

**Owner change:** "I have added another strategy to utilize the buying power, going
forward with the account balance as potential buying power, and continue doing dry
run." Recorded here with the measurement that makes it concrete.

## Measured (2026-08-17, pre-open)

`get_portfolio` on 576391551:

| field | value |
| --- | --- |
| total_value | $11,858.54 |
| cash | $11,858.54 |
| equity_value / options_value | $0 / $0 |
| **buying_power** | **$60.54** |

`get_accounts`: account type **`cash`**, `unsettled_funds` **$0.00**. So the gap is
not settlement — it is reservation by working orders.

`get_equity_orders` (created ≥ 2026-08-14) explains it exactly. Ten **queued**,
`gfd`, `market` **buy** orders, all `placed_agent: agentic`, created 03:23–03:24Z
today (11:24 PM ET Sunday), i.e. queued for Monday's open:

| symbol | reserved |
| --- | --- |
| CAT | $549 |
| INTC | $568 |
| XOM | $660 |
| LRCX | $795 |
| AMD | $889 |
| JNJ | $958 |
| AVGO | $1,435 |
| GOOGL | $1,691 |
| NVDA | $1,942 |
| MU | $2,311 |
| **total** | **$11,798.00** |

$11,858.54 − $11,798.00 = **$60.54** — the reported buying power to the cent. The
arithmetic closes, so the cause is established, not inferred.

An earlier batch of similar orders (BRK.B, WMT, VRT, AMD, GOOGL, IWM, NVDA, and a
first pass at the same ten) was cancelled and re-placed at slightly different dollar
amounts between 03:17Z and 03:24Z. That is the other strategy's business; noted only
because it shows the reservation is actively re-sized and can move between wakes.

## Consequence for this strategy

**At $60.54 of buying power, this strategy cannot fund any entry at all.** A typical
7DTE SPY entry at the $1,000 cap is 2 contracts of ~$3.50 premium ≈ $700. Even one
contract is roughly an order of magnitude out of reach. If a qualifying signal fired
today, the correct outcome is `blocked - insufficient buying power`.

This is not a defect to route around. The account is a **cash account** — no margin,
and sale proceeds are not spendable until settled. The only honest response is to
size against what is actually available and log the block.

## Changes made

- **`CLAUDE.md`** — new bullet under the shared-account section: buying power is
  shared and contested; `max_premium_per_trade_usd` is a cap, not an entitlement;
  effective budget = `min(cap, live buying_power)`; live read is mandatory before
  sizing; insufficient buying power is a blocked signal, never a reason to shrink or
  skip the stop or exceed a `risk:` limit; never touch another strategy's orders to
  free cash.
- **`config/strategy.yaml`** — provenance comment on `max_premium_per_trade_usd`, and
  a new `require_live_buying_power_check: true` gating key.
- **`docs/PLAYBOOK.md`** Phase 3 step 2e — rewritten from "Premium ≤ settled cash"
  into an explicit gate: `get_portfolio` in the same wake, budget =
  `min(max_premium_per_trade_usd, buying_power)`, `size` returning 0 → log
  `blocked - insufficient buying power` (no trade slot consumed).

**No strategy or risk parameter changed.** Entry threshold, P=3 persistence gate,
−28% stop, +30% TP, EOD carry gate and every `risk:` limit are untouched.
**`mode: dry_run` is unchanged and confirmed** — no order will be placed either way.

## Open question for the owner

The two strategies are not merely sharing an account, they are competing for the same
dollars, and the equity strategy queues its orders overnight — so it claims the cash
before this strategy's 9:45 ET entry window even opens. As configured, this strategy
will be locked out on any day that happens. If it is meant to keep trading, it needs a
reserved allocation (e.g. the equity strategy capped below the full balance, or a
carve-out this strategy can rely on). Flagging rather than assuming: choosing how to
split the capital is the owner's call, not this strategy's.

---

## Resolution — same day, owner decision

> "this strategy will only do test run, not with real money, just copy the account
> balance now and continue with this number"

The open question above is answered: this strategy does not compete for the cash at
all. It sizes against a **fixed paper balance**, `paper_buying_power_usd: 11858.54`
(the 2026-08-17 pre-open snapshot), and ignores live buying power entirely while in
`dry_run`.

Effective budget = `min($1,000 cap, $11,858.54)` = **$1,000** — the cap binds, so
sizing behaves exactly as it did before the equity strategy existed. The $60.54
lockout is moot: nothing is being funded, so there is nothing to be short of.

The gate added earlier today is therefore **narrowed, not removed**. It now applies in
live mode only, where real contested buying power would govern and
`paper_buying_power_usd` is ignored. That keeps the protection in place for the case
where it matters, without letting another strategy's cash reservations block a paper
trade.

`paper_buying_power_usd` is deliberately **static** — it does not drift with
hypothetical P&L. That keeps every session's sizing comparable to every other
session's, which is what a forward test needs. If the owner later wants paper equity
to compound, that is a different design and should be an explicit change.

**Unchanged:** `mode: dry_run`, every `risk:` limit, the entry threshold, the P=3
persistence gate, the −28% stop, the +30% take-profit, and the EOD carry gate.
