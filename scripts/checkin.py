#!/usr/bin/env python3
"""Wake check-in helper: merge bars, replay the interval, check exits.

Added 2026-08-14. Every monitoring wake used to hand-roll ~40 lines of ad-hoc
merge/replay Python. That is error-prone (a transcription slip silently corrupts
the day's bar file) and slow. This does the same work in three commands.

All scoring still goes through scripts/strategy_calc.py — this shells out to it
rather than reimplementing any strategy math, per CLAUDE.md.

USAGE
  # 1. merge fresh bars (stdin: "HH:MM open high low close volume" per line, UTC)
  python3 scripts/checkin.py merge --date 2026-08-14 --symbol SPY < bars.txt

  # 2. per-minute score replay over the interval since the last check
  python3 scripts/checkin.py scan --date 2026-08-14 --symbol SPY --since 17:53

  # 3. exit check against an option's own high/low across the interval
  python3 scripts/checkin.py exits --fill 3.56 --low 3.68 --high 3.79

`scan` is the load-bearing safety check at a 5-minute cadence: a threshold
crossing plus a complete persistence run can begin and end inside one interval,
so the endpoint score alone is not sufficient. It prints every minute whose
|score| >= threshold and exits non-zero if any crossing is found, so a wake can
branch on it.

`--since` is UTC (matching the bar timestamps). Pass `--et` to give it in
Eastern instead. Minutes before the 09:30 ET open are skipped unless
`--include-premarket`: pre-open the score is gap + premarket only, rescaled to
full weight, so it swings hard on thin early tape and is never actionable
(entries open 09:45 ET). On 2026-09-02 a `--since 09:58` meant as ET replayed
from 05:58 ET and printed 44 "crossings" at 06:00-07:10 ET — real prices, real
math, but noise for the purpose of the check. This guard stops that.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CALC = ROOT / "scripts" / "strategy_calc.py"
CONFIG = ROOT / "config" / "strategy.yaml"
ET = ZoneInfo("America/New_York")


def et_to_utc_hhmm(date, hhmm):
    """'HH:MM' Eastern on `date` -> 'HH:MM' UTC (DST-aware)."""
    d = datetime.strptime(date, "%Y-%m-%d").date()
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=ET).astimezone(timezone.utc).strftime("%H:%M")


def regular_open_utc(date):
    """UTC 'HH:MM' of the 09:30 ET open on `date` (13:30Z in EDT, 14:30Z in EST)."""
    return et_to_utc_hhmm(date, "09:30")


def bars_path(date):
    return ROOT / "data" / f"{date}-bars.json"


def load(date):
    p = bars_path(date)
    if not p.exists():
        sys.exit(f"no bar file: {p}")
    return json.loads(p.read_text())


def score_at(doc, cutoff, symbol):
    """Score using only bars at or before cutoff (an 'HH:MM' UTC string)."""
    clipped = {"vix": doc.get("vix"), "symbols": {}}
    for sym, data in doc["symbols"].items():
        clipped["symbols"][sym] = {
            "prior_close": data["prior_close"],
            "bars": [b for b in data["bars"] if b["t"][11:16] <= cutoff],
        }
    tmp = ROOT / "data" / ".checkin_tmp.json"
    tmp.write_text(json.dumps(clipped))
    out = subprocess.run(
        ["python3", str(CALC), "score", "--input", str(tmp), "--config", str(CONFIG)],
        capture_output=True, text=True,
    )
    tmp.unlink(missing_ok=True)
    if out.returncode != 0:
        sys.exit(f"strategy_calc failed: {out.stderr.strip()}")
    r = json.loads(out.stdout)
    return r["per_symbol"][symbol]["score"], r["entry_threshold"]


def cmd_merge(args):
    doc = load(args.date)
    if args.symbol not in doc["symbols"]:
        sys.exit(f"{args.symbol} not in bar file")
    existing = {b["t"] for b in doc["symbols"][args.symbol]["bars"]}
    added = skipped = 0
    for line in sys.stdin:
        parts = line.split()
        if len(parts) != 6:
            continue
        hhmm, o, h, l, c, v = parts
        key = f"{args.date}T{hhmm}:00Z"
        if key in existing:
            skipped += 1
            continue
        doc["symbols"][args.symbol]["bars"].append(
            {"t": key, "o": float(o), "h": float(h), "l": float(l), "c": float(c), "v": int(v)}
        )
        added += 1
    doc["symbols"][args.symbol]["bars"].sort(key=lambda b: b["t"])
    bars_path(args.date).write_text(json.dumps(doc, indent=2))
    total = len(doc["symbols"][args.symbol]["bars"])
    print(f"{args.symbol}: +{added} merged, {skipped} already present, {total} total")


def cmd_scan(args):
    doc = load(args.date)
    since = et_to_utc_hhmm(args.date, args.since) if args.et else args.since
    open_utc = regular_open_utc(args.date)
    if since < open_utc and not args.include_premarket:
        print(f"note: --since {since}Z is before the 09:30 ET open ({open_utc}Z); replaying from "
              f"the open. Pre-open minutes score on gap+premarket only and are never actionable "
              f"-- pass --include-premarket to see them anyway.")
        since = open_utc
    minutes = sorted({b["t"][11:16] for b in doc["symbols"][args.symbol]["bars"]})
    window = [m for m in minutes if m >= since]
    if not window:
        sys.exit(f"no bars at/after {since}Z")
    rows, crossings, threshold = [], [], None
    for m in window:
        s, threshold = score_at(doc, m, args.symbol)
        rows.append((m, s))
        if abs(s) >= threshold:
            crossings.append((m, s))
    lo = min(r[1] for r in rows)
    hi = max(r[1] for r in rows)
    print(f"replayed {len(rows)} min ({window[0]}-{window[-1]}Z) {args.symbol}: "
          f"score {lo:+.1f} to {hi:+.1f}, threshold +/-{threshold:.0f}")
    if crossings:
        print(f"*** {len(crossings)} MINUTE(S) AT/OVER THRESHOLD ***")
        for m, s in crossings:
            tag = "  (pre-open, not actionable)" if m < open_utc else ""
            print(f"    {m}Z  {s:+.1f}{tag}")
        print("-> run: strategy_calc.py persistence --input data/"
              f"{args.date}-bars.json --symbol {args.symbol}")
        print("-> then check the entry time against entry_latest before acting")
        sys.exit(2)
    print("no threshold crossing in interval")


def cmd_exits(args):
    stop = round(args.fill * args.stop_frac, 2)
    tp = round(args.fill * (1 + args.tp_pct / 100), 2)
    floor = round(args.fill * (1 + args.floor_pct / 100), 2)
    hit_stop = args.low <= stop
    hit_tp = args.high >= tp
    print(f"fill {args.fill:.2f} | interval {args.low:.2f}-{args.high:.2f}")
    print(f"  stop  {stop:.2f}  touched: {'YES *** EXIT ***' if hit_stop else 'no'}")
    print(f"  tp    {tp:.2f}  touched: {'YES *** EXIT ***' if hit_tp else 'no'}")
    print(f"  carry floor {floor:.2f} (Phase 5 gate only)")
    if args.mid is not None:
        pnl = (args.mid - args.fill) * 100 * args.qty
        print(f"  mid {args.mid:.2f} -> {(args.mid/args.fill-1)*100:+.1f}% "
              f"({pnl:+.2f} USD on {args.qty})")
        print(f"  carry: {'BELOW floor -> close before 16:00' if args.mid <= floor else 'above floor -> carry'}")
    if hit_stop or hit_tp:
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("merge", help="merge 'HH:MM o h l c v' lines from stdin")
    m.add_argument("--date", required=True)
    m.add_argument("--symbol", required=True)
    m.set_defaults(fn=cmd_merge)

    s = sub.add_parser("scan", help="per-minute score replay over an interval")
    s.add_argument("--date", required=True)
    s.add_argument("--symbol", default="SPY")
    s.add_argument("--since", required=True, help="HH:MM to replay from (UTC unless --et)")
    s.add_argument("--et", action="store_true", help="interpret --since as Eastern time")
    s.add_argument("--include-premarket", action="store_true", dest="include_premarket",
                   help="also replay minutes before the 09:30 ET open (never actionable)")
    s.set_defaults(fn=cmd_scan)

    e = sub.add_parser("exits", help="stop/TP/carry check against interval high-low")
    e.add_argument("--fill", type=float, required=True)
    e.add_argument("--low", type=float, required=True)
    e.add_argument("--high", type=float, required=True)
    e.add_argument("--mid", type=float)
    e.add_argument("--qty", type=int, default=2)
    e.add_argument("--stop-frac", type=float, default=0.72)
    e.add_argument("--tp-pct", type=float, default=30.0)
    e.add_argument("--floor-pct", type=float, default=-14.0)
    e.set_defaults(fn=cmd_exits)

    args = ap.parse_args()
    try:
        args.fn(args)
    except BrokenPipeError:  # e.g. `scan ... | head` — not an error worth a traceback
        sys.stderr.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
