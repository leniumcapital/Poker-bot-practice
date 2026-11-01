#!/usr/bin/env python3
"""Run tables and print a results table per field mix and point distribution.

  python3 tools/run_sim.py --quick                     # ~500 tables per cell
  python3 tools/run_sim.py --tables 5000               # full mode
  python3 tools/run_sim.py --fields soft --payouts flat --set OPEN_PCT.2=0.5
"""
import argparse
import json
import sys
import time

import _paths  # noqa: F401
from sim import settings as S
from sim.runner import run_tables, summarize, default_workers


def parse_overrides(items):
    out = {}
    for item in items or []:
        key, _, value = item.partition("=")
        try:
            out[key] = json.loads(value)
        except ValueError:
            out[key] = value
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="500 tables per cell")
    ap.add_argument("--tables", type=int, default=5000)
    ap.add_argument("--fields", default=",".join(S.FIELDS))
    ap.add_argument("--payouts", default=",".join(S.PAYOUTS))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=default_workers())
    ap.add_argument("--path", default=None, help="bot directory to test")
    ap.add_argument("--set", action="append", help="config override KEY=JSON")
    ap.add_argument("--no-time-limit", action="store_true")
    ap.add_argument("--wall-clock", action="store_true", help="penalize wall-clock overruns too (OS jitter included)")
    args = ap.parse_args()
    tables = 500 if args.quick else args.tables
    hero = {"path": args.path, "overrides": parse_overrides(args.set)}
    limit = None if args.no_time_limit else S.TIME_LIMIT_NS
    print(f"{'field':<11}{'payout':<11}{'tables':>7}{'points':>9}{'+/-95%':>8}{'even':>7} "
          f"{'1st%':>6}{'2nd%':>6}{'3rd%':>6}{'last%':>6} {'crash':>6}{'t/out':>6}{'illeg':>6}{'fallbk':>7}{'jitter':>7}"
          f"{'fieldflt':>9}{'avg_us':>8}{'maxCPU':>8}{'hands':>7}{'cap%':>6}")
    bad = 0
    t0 = time.time()
    for field in args.fields.split(","):
        for pay in args.payouts.split(","):
            payouts = S.PAYOUTS[pay]
            rows = run_tables(hero, field, payouts, tables, args.seed, args.workers, limit, args.wall_clock)
            s = summarize(rows)
            even = sum(payouts) / len(payouts)
            d = s["dist"]
            print(f"{field:<11}{pay:<11}{s['tables']:>7}{s['mean']:>9.2f}{s['ci']:>8.2f}{even:>7.1f} "
                  f"{d[0]*100:>6.1f}{d[1]*100:>6.1f}{d[2]*100:>6.1f}{d[-1]*100:>6.1f} "
                  f"{s['exceptions']:>6}{s['timeouts']:>6}{s['illegal']:>6}{s['fallbacks']:>7}{s['jitter']:>7}{s['field_faults']:>9}"
                  f"{s['avg_us']:>8.1f}{s['max_cpu_us']:>8.0f}{s['avg_hands']:>7.1f}{s['capped']*100:>6.1f}",
                  flush=True)
            bad += s["exceptions"] + s["timeouts"] + s["illegal"] + s["fallbacks"]
            for err in s["errors"]:
                print("   caught inside act():", err)
    print(f"\nelapsed {time.time()-t0:.1f}s  hero crash+timeout+illegal+fallback = {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
