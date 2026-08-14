# Wake-delivery audit — 2026-08-14

**Trigger:** a fully-qualifying SPY put entry met the P=3 persistence gate at
11:21 ET and sat qualifying for 9 minutes inside the entry window with no session
turn to act on it. Owner asked, twice, "why is there a gap." This is the answer.

**Outcome:** `interval_open_minutes` / `interval_flat_minutes` 1 → 5, the
2026-08-12 fallback-wake pattern removed, and per-minute replay promoted from an
exception (only when a wake is late) to the normal path on every wake.

## Method

Every `send_later` trigger record carries a requested time (`run_once_at`) and,
once delivered, an actual delivery (`last_fired_at`). Pulled all of today's via
`list_triggers` and differenced them. Two sessions were active on this account
today, so both are tabulated — this strategy (`session_01LYbUn21tPxhdDr2LoioESx`)
and the independently-operated Daily Momentum Calls strategy
(`session_01GCXxKHzVXVvbVootS4gtbU`), which shares the account per CLAUDE.md.

## Measured — this strategy's session

| trigger | requested | delivered | lag |
| --- | --- | --- | --- |
| Phase 1 final premarket | 13:32Z | 13:38:35Z | 6.6 min |
| Phase 2 second checkpoint | 13:46Z | 15:00:48Z | **74.8 min** |
| Phase 3 cycle 1 | 13:59Z | 14:09:44Z | 10.7 min |
| Phase 3 cycle 2 | 14:13Z | **never** | **stranded** |
| Phase 3 cycle 3 | 15:05Z | 15:36:06Z | 31.1 min |
| fallback backup wake | 15:19Z | **never** | **stranded** |

4 delivered, 2 stranded. Actual wall-clock delivery times: 13:38, 14:09, 15:00,
15:36 — intervals of 31, 51 and 36 minutes.

## Measured — the parallel session, same window

| requested | delivered | lag |
| --- | --- | --- |
| 13:41Z | 13:52:52Z | 11.9 min |
| 13:43Z | 13:49:57Z | 6.9 min |
| 13:53Z | 14:10:18Z | 17.3 min |
| 14:14Z | 14:17:40Z | 3.7 min |
| 14:21Z | 14:25:55Z | 4.9 min |
| 14:30Z | 14:34:50Z | 4.8 min |
| 14:38Z | 14:59:17Z | 21.3 min |
| 15:02Z | 15:10:19Z | 8.3 min |
| 15:13Z | 15:41:56Z | 28.9 min |

9 delivered, 0 stranded, max lag 28.9 min, median ~8 min.

## Findings

**1. Stranding is real and distinct from lag.** Two triggers never fired at all.
Both still read `enabled: true` with no `last_fired_at`; the 14:13Z one was over
3h25m past due at time of audit. These are not slow deliveries — they are dead.
This is the first time the operation has *confirmed* the silent-failure mode that
was only hypothesised after 2026-08-10's four-hour dark gap.

**2. Delivery is not FIFO.** At 15:00:48 the system delivered the 13:46Z trigger
while the 14:13Z trigger — created later, but due 47 minutes before that delivery
moment — was passed over and never fired. Ordering cannot be relied on.

**3. More triggers did not buy more wakes.** This session received one wake per
~31–51 minutes regardless of how many were queued. Critically, the fallback backup
wake armed at 15:19Z specifically to catch a dark chain was itself stranded. The
2026-08-12 mitigation does not work, and the pattern of piling on redundant
triggers plausibly contributed to the backlog it was meant to survive.

**4. The two sessions were treated very differently.** Same account, same window:
the other session got 9 deliveries with no stranding and a 28.9-min worst case;
this one got 4 with two stranded and a 74.8-min worst case. **Cause unknown.** The
sessions differ in more than trigger rate (prompt sizes, turn durations, session
age), so this is not attributable to contention on the evidence available. Worth
re-measuring on a day when only one session is active.

## What this means for the strategy

The 1-minute cadence was a fiction. Effective monitoring resolution on 2026-08-14
was ~30–50 minutes, so the 11:21 ET signal was **not catchable at any trigger
scheduling rate**. This partially revises the same-day journal entry, which
attributed the miss primarily to a process failure (not arming a backup wake after
two earlier disruptions). That process failure was real and is still owned — but
the backup wake, once finally armed, was stranded. It would not have saved the
entry. Both statements are true and the journal now reflects both.

The fix is to stop trying to poll at signal resolution and instead **recover
signal resolution from the data**: poll less often, and on every wake replay every
intervening minute from backfilled bars. A threshold crossing plus a complete
3-minute persistence run can begin and end inside one 5-minute interval, so the
replay is mandatory, not conditional.

## Change made

- `config/strategy.yaml`: `interval_open_minutes` and `interval_flat_minutes`
  1 → 5, with provenance.
- `docs/PLAYBOOK.md` Prime Directive 5: fallback-wake pattern replaced with
  "poll every 5 minutes and replay the gap — never trust the endpoint score."
- `docs/PLAYBOOK.md` Phase 4: cadence rewritten; **one wake per turn, no stacked
  backups**; per-minute replay is now the normal path on every wake; a >15-min
  late wake is treated as possible stranding and journalled plainly.

## Caveats and open questions

- **One day of data.** The stranding finding is from a single session-day. Do not
  treat the ~30–50 min delivery interval as a stable constant.
- **5 minutes is a first step, not a validated answer** (owner: "change to 5
  minutes first"). The 2026-08-12 audit found ~20-min cadence delivering with
  sub-1-minute lag. If 5 min still strands triggers or shows >10 min lag, step
  down toward 20 and record it.
- **Known cost of the slower poll.** The entry window (9:45–11:30) now yields ~21
  looks instead of a notional 105, and an entry is detected up to 5 minutes after
  its gate is met. For a 7DTE multi-day hold that is tolerable. The exit side is
  more exposed in principle, but in live mode the resting GTC stop — not the
  polling loop — is what actually protects an open position (Hard Invariant 1);
  the loop's exit role is take-profit, time stop, DTE floor and the EOD carry
  gate, none of which are minute-critical.
- **Not investigated:** why the two sessions differ. Flagged to the owner
  separately, since both run on the same account and one of them trades live.
