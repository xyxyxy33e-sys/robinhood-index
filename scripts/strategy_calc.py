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

stops --fill AVG_FILL [--config ...]
    Stop trigger / stop limit / take-profit prices for a filled long option.

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
    "min_agreement": 2,
    "stop_trigger_frac": 0.72,
    "stop_limit_frac": 0.65,
    "take_profit_pct": 60.0,
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
    market = sum(scores) / len(scores) if scores else 0.0
    agree = sum(1 for s in scores if s * market > 0)
    penalized = agree < int(cfg["min_agreement"]) and market != 0
    if penalized:
        market *= 0.6

    regime = []
    spy = per_symbol.get("SPY", {}).get("detail", {})
    if abs(spy.get("gap_pct", 0.0)) > cfg["gap_limit_pct"]:
        regime.append(f"SPY gap {spy['gap_pct']}% exceeds {cfg['gap_limit_pct']}% limit")
    vix = data.get("vix")
    if vix is not None and vix > cfg["vix_max"]:
        regime.append(f"VIX {vix} above {cfg['vix_max']}")

    market = round(market, 1)
    tradeable = not regime and abs(market) >= cfg["entry_threshold"]
    direction = "call" if market > 0 else "put" if market < 0 else None
    pick = None
    if tradeable:
        aligned = {s: v["score"] for s, v in per_symbol.items() if v["score"] * market > 0}
        if aligned:
            pick = max(aligned, key=lambda s: abs(aligned[s]))

    print(json.dumps({
        "per_symbol": per_symbol,
        "market_score": market,
        "agreement": agree,
        "agreement_penalty_applied": penalized,
        "regime_blocks": regime,
        "entry_threshold": cfg["entry_threshold"],
        "signal": {"tradeable": tradeable, "direction": direction if tradeable else None,
                   "instrument": pick},
    }, indent=2))


def cmd_size(args):
    per_contract = args.price * 100.0
    qty = math.floor(args.budget / per_contract) if per_contract > 0 else 0
    print(json.dumps({
        "contracts": qty,
        "premium_total": round(qty * per_contract, 2),
        "skip": qty < 1,
    }, indent=2))


def cmd_stops(args):
    cfg = load_config(args.config)
    print(json.dumps({
        "stop_trigger": round(args.fill * cfg["stop_trigger_frac"], 2),
        "stop_limit": round(args.fill * cfg["stop_limit_frac"], 2),
        "take_profit": round(args.fill * (1 + cfg["take_profit_pct"] / 100.0), 2),
        "max_loss_at_trigger_pct": round((1 - cfg["stop_trigger_frac"]) * 100, 1),
    }, indent=2))


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

    s = sub.add_parser("stops")
    s.add_argument("--fill", type=float, required=True, help="avg fill, per share")
    s.add_argument("--config", default="config/strategy.yaml")
    s.set_defaults(fn=cmd_stops)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
