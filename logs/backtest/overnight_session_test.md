# Test: overnight (20:00–04:00 ET) SPY session as a signal input — NULL RESULT

**Date:** 2026-09-17. **Trigger:** owner asked whether Webull (and the other newly
attached data sources) carry anything that improves the strategy — see
`logs/analysis/2026-09-17_external_data_review.md` for the full source audit.

## Hypothesis

The score's `gap` and `premarket` components read SPY's 04:00–09:29 ET tape, which
`docs/PLAYBOOK.md` already notes is thin and "swings hard". Webull exposes the
overnight ATS session (20:00 ET → 04:00 ET, `trading_sessions=OVN`) that Robinhood's
`bounds=extended` does not. If the overnight move carried directional information
about the regular session, it would be a cheap, causally-clean improvement to the
pre-open read (and a substitute for ES futures, which are subscription-gated).

## Data

Webull `get_stock_bars`, SPY, M5 bars, sessions OVN / PRE / RTH, **2026-06-12 →
2026-09-16, n = 52 trading days** (every day with all three sessions present; the
holiday-adjacent 9/7 and the two June days without OVN data are dropped).
Definitions, all relative to the prior RTH close (last 15:55 M5 bar):

| series | window |
|---|---|
| `ovn_pct` | overnight close (last bar ≤ 03:59 ET, i.e. 03:55) vs prior close |
| `pre_leg_pct` | 04:00 → 09:29 ET leg alone (09:25 bar close vs overnight close) |
| `pre_full_pct` | 09:25 bar close vs prior close (≈ what `gap`+`premarket` see) |
| `gap_pct` | 09:30 open vs prior close |
| targets | open→09:45, open→11:30, open→close, 09:45→11:30, 09:45→close |

## Result — no lead in any window, in any month

Pearson correlation, with sign-agreement count:

| lead \ target | open→09:45 | open→11:30 | open→close | 09:45→11:30 | 09:45→close |
|---|---|---|---|---|---|
| `ovn_pct` | −0.15 (29/52) | −0.04 (30/52) | 0.08 (25/52) | 0.06 (31/52) | 0.16 (26/52) |
| `pre_leg_pct` | −0.14 (23/52) | −0.13 (22/52) | −0.00 (23/52) | −0.03 (25/52) | 0.08 (26/52) |
| `pre_full_pct` | −0.19 (29/52) | −0.10 (30/52) | 0.06 (29/52) | 0.03 (31/52) | 0.17 (32/52) |
| `gap_pct` | −0.19 (29/52) | −0.10 (30/52) | 0.07 (29/52) | 0.03 (31/52) | 0.17 (32/52) |

Sign agreement is coin-flip everywhere (22–32 of 52). Per month (Jun n=12, Jul 13,
Aug 16, Sep 11) the overnight → open→11:30 correlation is −0.21 / −0.09 / 0.27 /
0.19 — it changes sign month to month, which is noise, not a regime story.
Conditioning on large overnight moves (|ovn| ≥ 0.4%, n=12) or large premarket legs
(|pre_leg| ≥ 0.3%, n=12) does not produce anything either (nothing beyond ±0.3 with
n=12, and 9/12 sign agreement at best).

Two structural facts did come out cleanly:
- `ovn_pct` → `gap_pct` correlation **0.87**: by 04:00 ET, most of the day's gap is
  already in. The 04:00–09:29 leg adds little to *where* the open will be.
- Mean absolute moves: overnight 0.29%, premarket leg 0.20%, gap 0.39%,
  open→11:30 0.26%. The overnight session is not a small tail — it is most of the gap.

Cross-check against the 16 paper trades (8/14 → 9/15): 11 entries were in the
overnight direction (net +$146, 5 wins), 5 against it (net +$175, 3 wins). 12 were
in the premarket-leg direction (net −$61, 5 wins), 4 against (net +$382, 3 wins).
Nothing separable at n=16, and if anything the sign is the wrong way.

## Conclusion: do not adopt. Overnight SPY data does not improve the pre-open read.

The gap/premarket components' ≈0 raw correlation with the subsequent drive is also
worth stating plainly: on Jun–Sep 2026 they carry no *directional* information on
their own. That is consistent with everything already in `logs/backtest/` — whatever
edge exists lives in the persistence-gated intraday drive, not in the pre-open
snapshot. This test does not touch the score (which is not used raw) and proposes no
change to it.

Overnight bars (Webull OVN, or Public.com `preMarketOvernight`) remain available as a
**journal-only context line** (`strategy_calc.py context`) — cheap to record, and a
forward series may show something a 52-day slice cannot. No threshold, no gate.

## Process note — a look-ahead bug was caught before this was written

The first full-sample pass grouped OVN bars by **Eastern date**, which put each
day's 20:00–23:59 ET bars (the evening *after* that day's close) into that day's
"overnight" bucket. The last bar in the bucket was therefore ~23:55 ET, and the
"overnight close" was a post-close price. That version showed `ovn_pct` → open→close
correlation **0.55** (0.49–0.69 every month) and the 04:00–09:29 leg as strongly
*contrarian* (−0.74, 6/52 sign agreement) — a result far too clean to be real, which
is what prompted the session-boundary check (`ET hours present: 0,1,2,3,20,21,22,23`
for OVN). Corrected grouping: trading date = UTC date of the bar (the 20:00→04:00 ET
session is 00:00→08:00Z on one UTC date), and only bars at or before 03:59 ET are
kept, asserted in code. Recorded here so the next person who pulls Webull OVN data
does not repeat it.

Reproduction data: `overnight_study.csv` in the session scratchpad (not committed —
regenerate from Webull `get_stock_bars` M5 with the three sessions; ~13 calls).
