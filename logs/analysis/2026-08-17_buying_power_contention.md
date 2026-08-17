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

---

## Amendment — paper equity now compounds

> "embed the P&L on to the paper balance"

The static snapshot is replaced by a **compounding paper ledger**.

- `data/paper_ledger.json` — `starting_balance_usd` $11,858.54 (2026-08-17 pre-open
  real-account snapshot), plus one appended row per realized paper trade.
- `scripts/strategy_calc.py paper` — the only sanctioned way to compute it.
  Equity = starting balance + realized. Reports `paper_equity_usd` and
  `sizing_budget_usd` = `min(max_premium_per_trade_usd, paper_equity_usd)`.

Current state: 0 realized rows, equity **$11,858.54**, sizing budget **$1,000** (the
cap binds), one open position carried in — the 2x SPY 776P 8/21 at $3.56 ($712
premium) from 2026-08-14, which realizes into the ledger when it closes.

### Three deliberate design choices

**1. Unrealized P&L never funds sizing.** `paper --mark <mid>` reports it for the
journal, but `sizing_budget_usd` excludes it. An unrealized gain is not spendable, and
sizing off a mark would let one paper position inflate the next one's size — a
compounding error that flatters a forward test exactly when it is running hot.

**2. The ledger starts today, not at the strategy's inception.** `starting_balance_usd`
is a *real* account snapshot taken 2026-08-17. It already contains the two REAL trades
of 2026-08-04 (+$258.00, +$182.00). The seven earlier *hypothetical* trades
(2026-07-28 → 2026-08-13, net **-$241.50**) are recorded under
`pre_ledger_hypotheticals` for the record but **not applied**, because mixing paper
results into a real-balance snapshot from a later date would double-count one
accounting and misdate the other. **This is an assumption, and it is reversible**: if
the owner wants the full paper history embedded, set `starting_balance_usd` to
11858.54 - 241.50 = **11617.04** and move those rows into `realized`. Flagged rather
than chosen silently, since it changes the equity curve's origin.

**3. The 2026-08-10 missed-entry reconstruction (~-$278) is excluded** — it was never
taken and never tracked to a close as an active position. The 2026-08-14 miss IS
included, because it was reconstructed at a real historical price and has been carried
forward as an active position ever since.

### Guard rails
- Append a realized row **at the moment a position closes**; never edit or delete a
  settled row.
- Never hand-compute equity — `strategy_calc.py paper` or nothing (CLAUDE.md: all math
  goes through the calculator).
- If equity ever reaches $0, `paper` emits a `HALT` field and entries stop.
- In live mode the ledger is ignored entirely and real buying power governs.
