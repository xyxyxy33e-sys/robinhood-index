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

stops --fill AVG_FILL [--peak PEAK_PRICE] [--config ...]
    Stop trigger and take-profit prices for a filled long option. The stop is a
    stop-MARKET order, so there is no limit floor to compute. Also returns
    consider_exit (config `consider_exit_pct`, default 10%).

    consider_exit is a REAL, GATING trailing-stop ACTIVATION level as of
    2026-07-30 (previously diagnostic-only 2026-07-29 -> 2026-07-30). Pass
    --peak (the highest price the position has reached since entry) to compute
    the trailing stop: once peak's unrealized gain first reaches consider_exit_pct,
    the effective stop tightens off the original stop_trigger to sit
    `trail_stop_distance_pct` (config, default 14) percentage points behind the
    peak's gain, and only ever moves up as new peaks are made. Without --peak,
    only the static stop_trigger/take_profit/consider_exit levels are returned
    (e.g. for a not-yet-filled sizing check). Only stop_trigger, take_profit,
    and (once active) the trailing stop are real, gating exits — signal decay
    remains diagnostic-only.

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

Stdlib only. Output is JSON on stdout.
"""

import argparse
import json
import math
import re
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

DEFAULTS = {
    "entry_threshold": 40.0,
    "gap_limit_pct": 1.5,
    "vix_max": 30.0,
    "stop_trigger_frac": 0.72,
    "take_profit_pct": 30.0,
    "consider_exit_pct": 10.0,
    "trail_stop_distance_pct": 14.0,
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
                m = re.match(r"\s*([a-z_]+):\s*([0-9.]+)\s*(#.*)?$", line)
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
        "direction": direction,
        "notable": notable,
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
        "consider_exit": round(args.fill * (1 + cfg["consider_exit_pct"] / 100.0), 2),
        "consider_exit_note": "REAL - trailing-stop activation level as of 2026-07-30 (pass --peak to compute the trailing stop)",
    }
    if args.peak is not None:
        peak_gain_pct = pct(args.peak, args.fill)
        out["peak"] = args.peak
        out["peak_gain_pct"] = round(peak_gain_pct, 2)
        active = peak_gain_pct >= cfg["consider_exit_pct"]
        out["trailing_stop_active"] = active
        if active:
            trail_gain_pct = peak_gain_pct - cfg["trail_stop_distance_pct"]
            trailing_stop = round(args.fill * (1 + trail_gain_pct / 100.0), 2)
            out["trailing_stop"] = trailing_stop
            out["trail_stop_distance_pct_used"] = cfg["trail_stop_distance_pct"]
            out["effective_stop"] = round(max(trailing_stop, stop_trigger), 2)
        else:
            out["effective_stop"] = stop_trigger
    else:
        out["effective_stop"] = stop_trigger
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
    s.add_argument("--config", default="config/strategy.yaml")
    s.set_defaults(fn=cmd_velocity)

    s = sub.add_parser("rvol")
    s.add_argument("--closes", required=True,
                   help="comma-separated daily closes, oldest first (>= 21 for rv20)")
    s.set_defaults(fn=cmd_rvol)

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
                    help="highest price reached since entry — computes the trailing stop "
                         "(effective_stop/trailing_stop/trailing_stop_active) once "
                         "consider_exit_pct has been crossed. Omit for a static/pre-fill "
                         "check with no trailing-stop computation.")
    s.set_defaults(fn=cmd_stops)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
