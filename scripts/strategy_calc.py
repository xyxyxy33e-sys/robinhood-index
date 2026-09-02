#!/usr/bin/env python3
"""Deterministic math for the 0DTE strategy: sentiment score, sizing, stop prices.

Subcommands
-----------
score --input bars.json [--config config/strategy.yaml]
    Composite sentiment score per symbol + market score + regime checks.

    bars.json schema:
    {
      "vix": 15.2,                      # optional
      "symbols": {
        "SPY": {
          "prior_close": 738.18,
          "bars": [{"t": "2026-07-27T13:01:00Z", "o":..., "h":..., "l":..., "c":..., "v":...}, ...]
        }, ...
      }
    }
    Bars are 1-minute, RFC3339 UTC timestamps, any session (extended bounds);
    the script splits pre-market vs regular at 9:30 America/New_York.

size --price ASK --budget USD
    Contracts affordable at ASK (per-share premium) within the budget. 0 = skip.

persistence --input bars.json [--config ...] [--symbol S] [--minutes P]
    REAL, GATING entry condition (added 2026-08-07, owner decision). The entry
    signal must hold |score| >= entry_threshold for `entry_persistence_min`
    (config, default 3) CONSECUTIVE minutes with the same sign, measured on
    backfilled 1-minute bars — NOT on polling checks, so a session polling every
    few minutes must backfill the minute bars and run this before entering.
    Returns trailing_qualifying_run_min, direction, and entry_gate_met as of the
    latest bar. Rationale: minute-level replay of the 7/24-8/7 forward period
    showed 1-2 minute score spikes (2026-08-06 10:18, 2026-08-07 10:25) are
    noise, while every winning entry's signal held for 10+ minutes; P=3 chosen
    by the owner to bias toward catching trend entries early (delays winners
    2-4 min on the forward sample) over maximal spike filtering. See
    logs/backtest/entry_confirmation_test.md. Entry must still be at or before
    entry_latest (11:30:00 ET inclusive).

stops --fill AVG_FILL [--peak PEAK_PRICE] [--config ...]
    Stop trigger, take-profit and EOD carry floor for a filled long option. The
    stop is a stop-MARKET order, so there is no limit floor to compute.

    TRAILING STOP REMOVED 2026-08-07 (owner decision): the consider_exit_pct
    (+10%) activation / trail_stop_distance_pct (14pp) mechanism that was live
    2026-07-30 -> 2026-08-07 never fired in 8 forward trades and is
    near-redundant under the +30% take_profit (its trail only beats breakeven
    when peak gain > +24%, but TP fires at +30%) — see
    logs/analysis/2026-08-07_forward_review.md finding 4. `effective_stop` is
    now ALWAYS the static stop_trigger; the resting stop is never moved. --peak
    still reports peak_gain_pct, but as a diagnostic only.

    eod_carry_floor (config `eod_carry_min_unrealized_pct`, default -14%) is
    the Phase 5 overnight-carry gate added 2026-08-07: a position at or below
    this unrealized loss at the 15:45 ET verification is closed before 16:00
    instead of carried overnight (gap-through-stop risk — see
    logs/backtest/take_profit_30pct_test.md). Only stop_trigger, take_profit,
    the time stop / DTE floor, the daily halt and the EOD carry gate are real,
    gating exits — signal decay remains diagnostic-only.

decay --entry-score X --current-score Y [--floor 20]
    Signal-decay check for an OPEN position: has the thesis that justified the entry
    died? Triggers when |current| < floor (default 20, half the entry threshold) OR
    the sign flipped vs entry. DIAGNOSTIC ONLY during dry-run — it is journaled, not
    acted on. Evidence so far is 4 trades (logs/backtest/signal_decay_test.md), far
    too thin to gate exits, and 30-min backtest checkpoints cannot model the live
    1-minute cadence.

velocity --score-now X --score-prev Y --minutes-elapsed N [--velocity-prev V] [--config ...]
    Score RATE OF CHANGE between two consecutive readings (points/minute), distinct
    from the entry gate which only looks at the absolute level |score| >= threshold.
    Motivation (2026-07-27 session): the score sat in a -18..-31 band the entire
    entry window and never crossed +/-40, yet it moved -21.8 -> -30.6 in 12 minutes
    (9:44 -> 9:56 ET) — a real, fast directional move that the absolute-level gate
    never saw. DIAGNOSTIC ONLY: journal it, do not gate entries on it. Also NOTE:
    once drive/range_pos clamp (as they did by 9:59 that day), the score's
    derivative saturates to ~0 too, for the same reason the level does — so this
    is most informative in the pre-clamp window, not a fix for the clamped-floor
    problem. `velocity_watch_pts_per_min` (config, default 1.0) just flags readings
    worth a second look; it is an unvalidated starting guess, not a threshold.

    Optional --velocity-prev (the prior points_per_minute reading) additionally
    computes the SECOND DERIVATIVE: acceleration = (velocity_now - velocity_prev) /
    minutes_elapsed, in points/min^2. Approximation only — reuses the current
    step's dt rather than the gap between the two velocities' midpoints, since
    sampling is irregular. `notable_accel` flags |acceleration| >=
    `acceleration_watch_pts_per_min2` (config, default 0.5 — also an unvalidated
    starting guess). Same rule as velocity: DIAGNOSTIC ONLY, never gates entries.

    This is a generic delta/dt tool — --score-now/--score-prev is any numeric
    series, not just the sentiment score. Also used to track 0DTE call and put
    MID PRICE velocity/acceleration every flat re-check (both directions, not
    just whichever way the sentiment score currently points), extending the
    existing shadow-0DTE-leg diagnostic from a signal-time snapshot into a
    continuous forward series. Option premiums are dollar-scale, not -100..100,
    so pass --watch-threshold / --accel-watch-threshold to override the config
    defaults — see `option_velocity_watch_usd_per_min` /
    `option_acceleration_watch_usd_per_min2` in config/strategy.yaml.

rvol --closes C1,C2,C3,...
    Annualised close-to-close realised volatility (%) over trailing 5/10/20-day
    windows, from daily closes in chronological order (oldest first). Pair with a
    contract's implied_volatility to get the IV/RV ratio: we are LONG premium, so a
    high ratio means we are paying up for movement the underlying has not been
    delivering. Recorded at every signal so the hypothesis can be tested on live
    forward data — historical IV is not available through the Robinhood tools.

reentry-distance --first-entry-price P --reentry-price P --direction call|put [--minutes-elapsed N]
    DIAGNOSTIC ONLY (added 2026-08-28) — never gates the re-entry decision, see
    docs/STRATEGY.md "Re-entry distance diagnostic". Run this at every same-day
    re-entry (an entry into a symbol that already had a position opened AND
    closed earlier the same day). Reports how far the underlying has already
    moved, in the position's favor, since the day's FIRST entry in that symbol
    — the day's first entry itself has no "distance" to report, so this command
    only ever applies to the second+ entry of a day. `extended_pct` is signed:
    positive means the underlying has moved further in the trade's favorable
    direction since the original fill (the re-entry may be chasing an already-
    extended move); negative means it has given back some of that move. Motivated
    by the 2026-08-28 forward loss (SPY 775C re-entry, -28.04%) but NOT backed by
    enough same-day-re-entry evidence to gate on (5W-3L combined across every
    instance in this repo's backtests + forward record as of 2026-08-28, net
    positive — see docs/STRATEGY.md). Log it every re-entry; revisit only once
    more instances accumulate under the current persistence-gate methodology.

ledger open  --contract C --instrument-id ID --qty N --fill F [--date D] [--note ...]
ledger close (--instrument-id ID | --contract C) --exit X --reason R [--qualifier Q] [--date-closed D] [--note ...]
    The ONLY supported way to write data/paper_ledger.json (added 2026-09-02).
    Three of the last four sessions drifted the ledger by hand-editing it —
    `open_positions` left empty at entry (8/31, 9/1) and a required field dropped
    in a later edit pass (9/2) — so the manual step is gone. `open` appends an
    `open_positions` row (premium_usd computed, never typed) and refuses when the
    slot is already taken (`max_concurrent_positions`) or the premium exceeds
    `max_premium_per_trade_usd`. `close` moves that row to `realized`, computing
    pnl_usd / return_pct from the recorded fill, and clears the slot. Both are
    append-only on settled rows (a realized row is never edited or deleted, per
    CLAUDE.md), write atomically, and print the updated `paper` summary so the
    journal figure comes from the same run. Reasons are the real exits only:
    take_profit, stop, eod_carry_gate, time_stop, dte_floor, daily_halt, manual;
    use --qualifier for the established annotations ("GAPPED THROUGH",
    "RETROACTIVE - wake gap"). Modeled prices go in exactly as the journal
    convention dictates (trigger price for an intraday cross, first print for a
    gap) — this command records, it does not decide.

Stdlib only. Output is JSON on stdout.
"""

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

DEFAULTS = {
    "entry_threshold": 40.0,
    "max_concurrent_positions": 1.0,
    "gap_limit_pct": 1.5,
    "vix_max": 30.0,
    "stop_trigger_frac": 0.72,
    "take_profit_pct": 30.0,
    "eod_carry_min_unrealized_pct": -14.0,
    "entry_persistence_min": 3.0,
    "max_premium_per_trade_usd": 1000.0,
    "velocity_watch_pts_per_min": 1.0,
    "acceleration_watch_pts_per_min2": 0.5,
    "option_velocity_watch_usd_per_min": 0.01,
    "option_acceleration_watch_usd_per_min2": 0.005,
}

WEIGHTS = {"gap": 25.0, "premarket": 25.0, "drive": 35.0, "range_pos": 15.0}
FULL_SCALE = {"gap": 0.50, "premarket": 0.30, "drive": 0.30}  # percent moves worth full weight


def load_config(path):
    """Minimal flat YAML reader for the few numeric keys we need (no yaml dep)."""
    cfg = dict(DEFAULTS)
    if not path:
        return cfg
    try:
        with open(path) as f:
            for line in f:
                m = re.match(r"\s*([a-z_]+):\s*(-?[0-9.]+)\s*(#.*)?$", line)
                if m and m.group(1) in cfg:
                    cfg[m.group(1)] = float(m.group(2))
    except FileNotFoundError:
        pass
    return cfg


def clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def pct(a, b):
    """Percent change from b to a."""
    return (a - b) / b * 100.0 if b else 0.0


def split_bars(bars):
    pre, reg = [], []
    for bar in bars:
        ts = datetime.fromisoformat(bar["t"].replace("Z", "+00:00")).astimezone(ET)
        (reg if ts.timetz().replace(tzinfo=None) >= time(9, 30) else pre).append(bar)
    return pre, reg


def score_symbol(prior_close, bars):
    pre, reg = split_bars(bars)
    comp, detail = {}, {}

    pm_last = pre[-1]["c"] if pre else None
    if pm_last is not None:
        gap = pct(pm_last, prior_close)
        comp["gap"] = clamp(gap / FULL_SCALE["gap"]) * WEIGHTS["gap"]
        detail["gap_pct"] = round(gap, 3)
    if len(pre) >= 2:
        pm = pct(pre[-1]["c"], pre[0]["c"])
        comp["premarket"] = clamp(pm / FULL_SCALE["premarket"]) * WEIGHTS["premarket"]
        detail["premarket_pct"] = round(pm, 3)
    if reg:
        drive = pct(reg[-1]["c"], reg[0]["o"])
        comp["drive"] = clamp(drive / FULL_SCALE["drive"]) * WEIGHTS["drive"]
        detail["drive_pct"] = round(drive, 3)
        hi = max(b["h"] for b in reg)
        lo = min(b["l"] for b in reg)
        if hi > lo:
            rp = (reg[-1]["c"] - lo) / (hi - lo)
            comp["range_pos"] = (2 * rp - 1) * WEIGHTS["range_pos"]
            detail["range_pos"] = round(rp, 3)

    # Rescale so missing components (e.g. pre-open: no drive yet) don't dilute the score.
    weight_present = sum(WEIGHTS[k] for k in comp)
    total = sum(comp.values()) * (100.0 / weight_present) if weight_present else 0.0
    return {
        "score": round(total, 1),
        "components": {k: round(v, 1) for k, v in comp.items()},
        "detail": detail,
    }


def cmd_score(args):
    cfg = load_config(args.config)
    with open(args.input) as f:
        data = json.load(f)

    per_symbol = {}
    for sym, payload in data["symbols"].items():
        per_symbol[sym] = score_symbol(payload["prior_close"], payload["bars"])

    scores = [s["score"] for s in per_symbol.values()]
    market = round(sum(scores) / len(scores), 1) if scores else 0.0

    regime = []
    spy = per_symbol.get("SPY", {}).get("detail", {})
    if abs(spy.get("gap_pct", 0.0)) > cfg["gap_limit_pct"]:
        regime.append(f"SPY gap {spy['gap_pct']}% exceeds {cfg['gap_limit_pct']}% limit")
    vix = data.get("vix")
    if vix is not None and vix > cfg["vix_max"]:
        regime.append(f"VIX {vix} above {cfg['vix_max']}")

    # Each symbol qualifies independently in its own direction; mixed calls/puts allowed.
    entries = []
    if not regime:
        for sym, val in per_symbol.items():
            if abs(val["score"]) >= cfg["entry_threshold"]:
                entries.append({"instrument": sym,
                                "direction": "call" if val["score"] > 0 else "put",
                                "score": val["score"]})
        entries.sort(key=lambda e: -abs(e["score"]))

    print(json.dumps({
        "per_symbol": per_symbol,
        "market_score": market,
        "regime_blocks": regime,
        "entry_threshold": cfg["entry_threshold"],
        "signal": {"tradeable": bool(entries), "entries": entries},
    }, indent=2))


def cmd_size(args):
    per_contract = args.price * 100.0
    qty = math.floor(args.budget / per_contract) if per_contract > 0 else 0
    print(json.dumps({
        "contracts": qty,
        "premium_total": round(qty * per_contract, 2),
        "skip": qty < 1,
    }, indent=2))


def paper_summary(led, cfg, mark=None):
    """Paper equity = starting balance + realized hypothetical P&L (owner, 2026-08-17:
    "embed the P&L on to the paper balance"). This is the sizing basis in dry_run; the
    real account balance is NOT re-read, so the other agentic strategies' cash
    reservations cannot lock this strategy out of a paper trade.

    Open positions are reported as unrealized marks only when `mark` is supplied, and
    NEVER folded into the sizing budget: an unrealized gain is not spendable, and
    sizing off it would let a paper position inflate the next position's size.
    """
    start = float(led["starting_balance_usd"])
    realized = led.get("realized", [])
    realized_total = round(sum(float(r["pnl_usd"]) for r in realized), 2)
    equity = round(start + realized_total, 2)

    out = {
        "starting_balance_usd": start,
        "ledger_start_date": led.get("ledger_start_date"),
        "realized_trades": len(realized),
        "realized_pnl_usd": realized_total,
        "paper_equity_usd": equity,
        "return_since_start_pct": round((equity / start - 1) * 100, 2) if start else None,
    }

    cap = cfg["max_premium_per_trade_usd"]
    out["max_premium_per_trade_usd"] = cap
    out["sizing_budget_usd"] = round(min(cap, equity), 2)
    out["budget_basis"] = "cap" if cap <= equity else "paper_equity (equity below cap)"
    if equity <= 0:
        out["HALT"] = "paper equity is exhausted - no further entries"

    opens = led.get("open_positions", [])
    if opens:
        out["open_positions"] = len(opens)
        out["open_premium_usd"] = round(sum(float(o["premium_usd"]) for o in opens), 2)
        if mark is not None:
            if len(opens) != 1:
                sys.exit("--mark needs exactly one open position")
            o = opens[0]
            unreal = round((mark - float(o["fill"])) * 100 * int(o["qty"]), 2)
            out["open_mark"] = mark
            out["open_unrealized_usd"] = unreal
            out["equity_incl_unrealized_usd"] = round(equity + unreal, 2)
            out["note"] = ("unrealized is REPORTING ONLY - sizing_budget_usd "
                           "deliberately excludes it")
    return out


def cmd_paper(args):
    with open(args.ledger) as f:
        led = json.load(f)
    print(json.dumps(paper_summary(led, load_config(args.config), args.mark), indent=2))


LEDGER_CLOSE_REASONS = ["take_profit", "stop", "eod_carry_gate", "time_stop",
                        "dte_floor", "daily_halt", "manual"]


def _load_ledger(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"no ledger at {path} — see CLAUDE.md (paper ledger) before creating one")
    except json.JSONDecodeError as e:
        sys.exit(f"ledger {path} is not valid JSON ({e}); fix it before writing")


def _write_ledger(path, led):
    """Write via temp file + rename so a crash mid-write can never leave a truncated
    ledger behind (the 2026-09-01 malformed-fragment incident was a hand edit; this
    closes the equivalent failure mode for the tool)."""
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(led, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _today_et():
    return datetime.now(ET).date().isoformat()


def cmd_ledger_open(args):
    led = _load_ledger(args.ledger)
    cfg = load_config(args.config)
    opens = led.setdefault("open_positions", [])
    if args.qty < 1:
        sys.exit("refusing: --qty must be >= 1")
    if args.fill <= 0:
        sys.exit("refusing: --fill must be > 0")
    if any(o.get("instrument_id") == args.instrument_id for o in opens):
        sys.exit(f"refusing: instrument {args.instrument_id} is already in open_positions")
    max_open = int(cfg["max_concurrent_positions"])
    if len(opens) >= max_open:
        sys.exit(f"refusing: {len(opens)} position(s) already open and "
                 f"max_concurrent_positions is {max_open} — close first")
    premium = round(args.fill * 100 * args.qty, 2)
    cap = cfg["max_premium_per_trade_usd"]
    if premium > cap + 1e-9:
        sys.exit(f"refusing: premium {premium:.2f} exceeds max_premium_per_trade_usd {cap:.2f}")
    row = {
        "date_opened": args.date or _today_et(),
        "contract": args.contract,
        "instrument_id": args.instrument_id,
        "qty": args.qty,
        "fill": args.fill,
        "premium_usd": premium,
        "note": args.note or "",
    }
    opens.append(row)
    _write_ledger(args.ledger, led)
    print(json.dumps({"opened": row, "paper": paper_summary(led, cfg)}, indent=2))


def cmd_ledger_close(args):
    led = _load_ledger(args.ledger)
    cfg = load_config(args.config)
    opens = led.get("open_positions", [])
    if args.instrument_id:
        matches = [o for o in opens if o.get("instrument_id") == args.instrument_id]
    else:
        matches = [o for o in opens if o.get("contract") == args.contract]
    if len(matches) != 1:
        sys.exit(f"refusing: expected exactly one matching open position, found {len(matches)} "
                 f"(open: {[o.get('contract') for o in opens]})")
    if args.exit <= 0:
        sys.exit("refusing: --exit must be > 0")
    o = matches[0]
    fill, qty = float(o["fill"]), int(o["qty"])
    reason = args.reason + (f" ({args.qualifier})" if args.qualifier else "")
    row = {
        "date_opened": o["date_opened"],
        "date_closed": args.date_closed or _today_et(),
        "contract": o["contract"],
        "instrument_id": o.get("instrument_id"),
        "qty": qty,
        "fill": fill,
        "exit": args.exit,
        "pnl_usd": round((args.exit - fill) * 100 * qty, 2),
        "return_pct": round((args.exit / fill - 1) * 100, 2),
        "reason": reason,
        "note": args.note if args.note is not None else o.get("note", ""),
    }
    # Append-only: settled rows are never edited or deleted (CLAUDE.md paper rule 2).
    led.setdefault("realized", []).append(row)
    led["open_positions"] = [p for p in opens if p is not o]
    _write_ledger(args.ledger, led)
    print(json.dumps({"closed": row, "paper": paper_summary(led, cfg)}, indent=2))


def cmd_decay(args):
    e, c, floor = args.entry_score, args.current_score, args.floor
    flipped = (e > 0 and c < 0) or (e < 0 and c > 0)
    faded = abs(c) < floor
    reasons = []
    if flipped:
        reasons.append("sign_flip")
    if faded:
        reasons.append(f"|score| {abs(c):.1f} < floor {floor}")
    print(json.dumps({
        "entry_score": e,
        "current_score": c,
        "retained_pct": round(abs(c) / abs(e) * 100, 1) if e else None,
        "triggered": bool(flipped or faded),
        "reasons": reasons,
        "note": "DIAGNOSTIC ONLY - journal it, do not act on it",
    }, indent=2))


def cmd_reentry_distance(args):
    first, now, direction = args.first_price, args.reentry_price, args.direction
    pct_move = (now - first) / first * 100 if first else None
    if pct_move is None:
        extended_pct = None
    elif direction == "call":
        extended_pct = pct_move
    else:  # put: underlying falling further is what "extends" the move
        extended_pct = -pct_move
    print(json.dumps({
        "first_entry_price": first,
        "reentry_price": now,
        "direction": direction,
        "pct_move_since_first_entry": round(pct_move, 3) if pct_move is not None else None,
        "extended_pct": round(extended_pct, 3) if extended_pct is not None else None,
        "minutes_since_first_entry": args.minutes_elapsed,
        "note": ("DIAGNOSTIC ONLY (added 2026-08-28) - never gates the re-entry decision. "
                 "See docs/STRATEGY.md 'Re-entry distance diagnostic' - journal it, do not "
                 "act on it."),
    }, indent=2))


def cmd_velocity(args):
    cfg = load_config(args.config)
    # Generic delta/dt tool: --score-now/--score-prev is any numeric series (sentiment
    # score, an option's mid price, ...). --watch-threshold/--accel-watch-threshold
    # override the config defaults (calibrated to the -100..100 sentiment score) for
    # series on a different scale, e.g. option premiums in dollars.
    now, prev, dt = args.score_now, args.score_prev, args.minutes_elapsed
    watch = args.watch_threshold if args.watch_threshold is not None else cfg["velocity_watch_pts_per_min"]
    accel_watch = args.accel_watch_threshold if args.accel_watch_threshold is not None \
        else cfg["acceleration_watch_pts_per_min2"]

    delta = round(now - prev, 4)
    pts_per_min = round(delta / dt, 4) if dt else None
    direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
    notable = pts_per_min is not None and abs(pts_per_min) >= watch

    # Percentage change (added 2026-08-04 for VIX; makes sense for any series where 0 is
    # not a meaningful/reachable value, e.g. VIX or an option's mid price — NOT the
    # sentiment score, which crosses zero routinely, making pct change unstable/meaningless
    # near the crossing. No config default: only becomes "notable" if the caller explicitly
    # opts in via --pct-watch-threshold (no forced default the way --watch-threshold has,
    # since there is no scale-appropriate default that would make sense across every series
    # this command gets reused for).
    pct_change = round(pct(now, prev), 2) if prev else None
    notable_pct = None
    if args.pct_watch_threshold is not None and pct_change is not None:
        notable_pct = abs(pct_change) >= args.pct_watch_threshold

    # Second derivative: acceleration = change in velocity over this same interval.
    # Approximation, not a rigorous continuous derivative — sampling is irregular/noisy
    # and this reuses minutes_elapsed (the current step's dt) rather than the gap
    # between the two velocity readings' midpoints. Requires the PRIOR velocity
    # reading as input (same carry-forward pattern as decay's entry_score).
    accel = None
    accel_direction = None
    notable_accel = False
    if args.velocity_prev is not None and pts_per_min is not None and dt:
        accel = round((pts_per_min - args.velocity_prev) / dt, 4)
        if accel == 0:
            accel_direction = "steady"
        elif (accel > 0) == (pts_per_min > 0):
            accel_direction = "accelerating"  # speeding up in the direction it's already moving
        else:
            accel_direction = "decelerating"  # slowing down, possibly about to reverse
        notable_accel = abs(accel) >= accel_watch

    print(json.dumps({
        "score_now": now,
        "score_prev": prev,
        "minutes_elapsed": dt,
        "delta": delta,
        "points_per_minute": pts_per_min,
        "pct_change": pct_change,
        "direction": direction,
        "notable": notable,
        "notable_pct": notable_pct,
        "velocity_prev": args.velocity_prev,
        "acceleration_pts_per_min2": accel,
        "accel_direction": accel_direction,
        "notable_accel": notable_accel,
        "note": "DIAGNOSTIC ONLY - journal it, do not gate entries on it",
    }, indent=2))


def cmd_rvol(args):
    closes = [float(x) for x in args.closes.replace(" ", "").split(",") if x]
    if len(closes) < 6:
        print(json.dumps({"error": "need at least 6 closes"})); return
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]

    def ann(n):
        w = rets[-n:]
        if len(w) < n:
            return None
        mean = sum(w) / len(w)
        var = sum((r - mean) ** 2 for r in w) / (len(w) - 1)
        return round(math.sqrt(var) * math.sqrt(252) * 100, 2)

    out = {f"rv{n}_annualised_pct": ann(n) for n in (5, 10, 20)}
    out["samples"] = len(rets)
    print(json.dumps(out, indent=2))


def cmd_stops(args):
    cfg = load_config(args.config)
    take_profit_pct = args.take_profit_pct if args.take_profit_pct is not None else cfg["take_profit_pct"]
    stop_trigger = round(args.fill * cfg["stop_trigger_frac"], 2)
    out = {
        "stop_trigger": stop_trigger,
        "order_type": "stop_market",
        "take_profit": round(args.fill * (1 + take_profit_pct / 100.0), 2),
        "take_profit_pct_used": take_profit_pct,
        "max_loss_at_trigger_pct": round((1 - cfg["stop_trigger_frac"]) * 100, 1),
        "eod_carry_floor": round(args.fill * (1 + cfg["eod_carry_min_unrealized_pct"] / 100.0), 2),
        "eod_carry_note": "REAL - Phase 5 (15:45 ET) overnight-carry gate added 2026-08-07: "
                          "mid <= eod_carry_floor -> close before 16:00 instead of carrying",
        "effective_stop": stop_trigger,
    }
    if args.peak is not None:
        out["peak"] = args.peak
        out["peak_gain_pct"] = round(pct(args.peak, args.fill), 2)
        out["peak_note"] = ("DIAGNOSTIC ONLY - trailing stop REMOVED 2026-08-07 (never fired in "
                            "8 forward trades; near-redundant under +30% take_profit). The "
                            "resting stop stays at stop_trigger for the life of the position.")
    print(json.dumps(out, indent=2))


def cmd_persistence(args):
    """REAL, GATING entry condition (added 2026-08-07, owner decision): the entry
    signal must hold |score| >= entry_threshold for `entry_persistence_min`
    CONSECUTIVE minutes (same sign), measured on backfilled 1-minute bars — not
    on polling checks, so the gate is polling-cadence-independent. This command
    computes the trailing qualifying run from the same bars.json the score
    command uses and says whether the gate is met as of the latest bar."""
    cfg = load_config(args.config)
    P = args.minutes if args.minutes is not None else int(cfg["entry_persistence_min"])
    threshold = cfg["entry_threshold"]
    with open(args.input) as f:
        data = json.load(f)
    sym = args.symbol or sorted(data["symbols"].keys())[0]
    payload = data["symbols"][sym]
    bars = sorted(payload["bars"], key=lambda b: b["t"])

    def is_reg(b):
        ts = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET)
        return ts.timetz().replace(tzinfo=None) >= time(9, 31)

    # Only regular-session cutoffs count: pre-9:31 scores are a different regime
    # (gap+premarket only, systematically inflated) and must not seed a run.
    reg_ts = [b["t"] for b in bars if is_reg(b)]
    out = {"symbol": sym, "persistence_required_min": P, "entry_threshold": threshold}
    lookback = max(P + 5, 45)
    tail = reg_ts[-lookback:] if reg_ts else []
    if not tail:
        out.update({"as_of": bars[-1]["t"] if bars else None, "score_as_of": None,
                    "direction": None, "trailing_qualifying_run_min": 0,
                    "run_started_at": None, "entry_gate_met": False,
                    "note": "no regular-session bars yet - gate cannot be met pre-open"})
        print(json.dumps(out, indent=2))
        return
    scores = {}
    for t in tail:
        cut = [b for b in bars if b["t"] <= t]
        scores[t] = score_symbol(payload["prior_close"], cut)["score"]
    last = tail[-1]
    s_last = scores[last]
    sign = 1 if s_last >= threshold else (-1 if s_last <= -threshold else 0)
    run_start = None
    if sign:
        run_start = last
        for t in reversed(tail[:-1]):
            s = scores[t]
            if (sign > 0 and s >= threshold) or (sign < 0 and s <= -threshold):
                run_start = t
            else:
                break
    if run_start:
        t0 = datetime.fromisoformat(run_start.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(last.replace("Z", "+00:00"))
        run_min = int((t1 - t0).total_seconds() // 60) + 1
    else:
        run_min = 0
    out.update({
        "as_of": last,
        "score_as_of": s_last,
        "direction": ("call" if sign > 0 else "put") if sign else None,
        "trailing_qualifying_run_min": run_min,
        "run_started_at": run_start,
        "entry_gate_met": bool(sign) and run_min >= P,
        "run_hit_lookback_limit": bool(run_start == tail[0] and len(reg_ts) > len(tail)),
        "note": ("REAL - entry persistence gate (added 2026-08-07, owner decision). Entry "
                 "additionally requires entry time <= entry_latest (11:30:00 ET inclusive, "
                 "later exclusive). Wall-clock minutes: bars missing INSIDE an otherwise "
                 "unbroken qualifying streak count toward the run (no disqualifying "
                 "observation breaks it)."),
    })
    print(json.dumps(out, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("score")
    s.add_argument("--input", required=True)
    s.add_argument("--config", default="config/strategy.yaml")
    s.set_defaults(fn=cmd_score)

    s = sub.add_parser("size")
    s.add_argument("--price", type=float, required=True, help="ask, per share")
    s.add_argument("--budget", type=float, required=True)
    s.set_defaults(fn=cmd_size)

    s = sub.add_parser("decay")
    s.add_argument("--entry-score", type=float, required=True, dest="entry_score")
    s.add_argument("--current-score", type=float, required=True, dest="current_score")
    s.add_argument("--floor", type=float, default=20.0)
    s.set_defaults(fn=cmd_decay)

    s = sub.add_parser("reentry-distance")
    s.add_argument("--first-entry-price", type=float, required=True, dest="first_price",
                   help="underlying price at the day's FIRST entry in this symbol")
    s.add_argument("--reentry-price", type=float, required=True, dest="reentry_price",
                   help="underlying price now, at the re-entry")
    s.add_argument("--direction", choices=["call", "put"], required=True)
    s.add_argument("--minutes-elapsed", type=float, default=None, dest="minutes_elapsed",
                   help="minutes since the day's first entry (optional, for the journal)")
    s.set_defaults(fn=cmd_reentry_distance)

    s = sub.add_parser("velocity")
    s.add_argument("--score-now", type=float, required=True, dest="score_now")
    s.add_argument("--score-prev", type=float, required=True, dest="score_prev")
    s.add_argument("--minutes-elapsed", type=float, required=True, dest="minutes_elapsed")
    s.add_argument("--velocity-prev", type=float, default=None, dest="velocity_prev",
                   help="prior points_per_minute reading, to compute acceleration (2nd derivative)")
    s.add_argument("--watch-threshold", type=float, default=None, dest="watch_threshold",
                   help="override velocity_watch_pts_per_min — for non-score series (e.g. option $)")
    s.add_argument("--accel-watch-threshold", type=float, default=None, dest="accel_watch_threshold",
                   help="override acceleration_watch_pts_per_min2 — for non-score series")
    s.add_argument("--pct-watch-threshold", type=float, default=None, dest="pct_watch_threshold",
                   help="pct_change is always reported when score_prev != 0; pass this to also "
                        "set notable_pct. No config default (unlike --watch-threshold) — pct "
                        "change isn't meaningful for the sentiment score, only opt-in series "
                        "like VIX or an option's mid price.")
    s.add_argument("--config", default="config/strategy.yaml")
    s.set_defaults(fn=cmd_velocity)

    s = sub.add_parser("rvol")
    s.add_argument("--closes", required=True,
                   help="comma-separated daily closes, oldest first (>= 21 for rv20)")
    s.set_defaults(fn=cmd_rvol)

    s = sub.add_parser("persistence")
    s.add_argument("--input", required=True, help="bars.json (same schema as score)")
    s.add_argument("--config", default=None)
    s.add_argument("--symbol", default=None,
                   help="symbol key inside bars.json (default: first alphabetically)")
    s.add_argument("--minutes", type=int, default=None,
                   help="override entry_persistence_min from config (default: config value)")
    s.set_defaults(fn=cmd_persistence)

    s = sub.add_parser("paper")
    s.add_argument("--ledger", default="data/paper_ledger.json")
    s.add_argument("--config", default="config/strategy.yaml")
    s.add_argument("--mark", type=float, default=None,
                    help="current mid of the single open position - reports unrealized "
                         "P&L. Reporting only: it is never added to sizing_budget_usd.")
    s.set_defaults(fn=cmd_paper)

    s = sub.add_parser("ledger", help="the only supported writer for data/paper_ledger.json")
    ls = s.add_subparsers(dest="ledger_cmd", required=True)
    lo = ls.add_parser("open", help="record a paper entry in open_positions")
    lo.add_argument("--contract", required=True, help='e.g. "SPY 767C 2026-09-09"')
    lo.add_argument("--instrument-id", required=True, dest="instrument_id")
    lo.add_argument("--qty", type=int, required=True)
    lo.add_argument("--fill", type=float, required=True, help="modeled fill, per share")
    lo.add_argument("--date", default=None, help="date_opened YYYY-MM-DD (default: today ET)")
    lo.add_argument("--note", default=None)
    lo.add_argument("--ledger", default="data/paper_ledger.json")
    lo.add_argument("--config", default="config/strategy.yaml")
    lo.set_defaults(fn=cmd_ledger_open)
    lc = ls.add_parser("close", help="move an open position to realized")
    g = lc.add_mutually_exclusive_group(required=True)
    g.add_argument("--instrument-id", dest="instrument_id")
    g.add_argument("--contract")
    lc.add_argument("--exit", type=float, required=True,
                    help="modeled exit, per share — trigger price for an intraday cross, "
                         "first available print for a gap-through (journal convention)")
    lc.add_argument("--reason", required=True, choices=LEDGER_CLOSE_REASONS)
    lc.add_argument("--qualifier", default=None,
                    help='appended in parentheses, e.g. "GAPPED THROUGH" or "RETROACTIVE - wake gap"')
    lc.add_argument("--date-closed", default=None, dest="date_closed",
                    help="YYYY-MM-DD (default: today ET)")
    lc.add_argument("--note", default=None,
                    help="replaces the open row's note (default: the open row's note carries over)")
    lc.add_argument("--ledger", default="data/paper_ledger.json")
    lc.add_argument("--config", default="config/strategy.yaml")
    lc.set_defaults(fn=cmd_ledger_close)

    s = sub.add_parser("stops")
    s.add_argument("--fill", type=float, required=True, help="avg fill, per share")
    s.add_argument("--config", default="config/strategy.yaml")
    s.add_argument("--take-profit-pct", type=float, default=None,
                    help="override config take_profit_pct — use for the shadow 0DTE leg, "
                         "which must stay fixed at the original DTE-comparison geometry "
                         "(60%%) regardless of the live 7DTE position's take_profit_pct, "
                         "so it remains an apples-to-apples comparison. See "
                         "logs/backtest/dte_comparison.md.")
    s.add_argument("--peak", type=float, default=None,
                    help="highest price reached since entry — reports peak_gain_pct as a "
                         "DIAGNOSTIC only (trailing stop removed 2026-08-07; effective_stop "
                         "is always the static stop_trigger). Omit for a static/pre-fill "
                         "check.")
    s.set_defaults(fn=cmd_stops)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
