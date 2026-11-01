#!/usr/bin/env python3
"""Compare two bot versions on identical seeds: same decks, same opponents, same seat.

  python3 tools/ab_test.py --b-set CBET_FREQ=0.5                   # config vs config
  python3 tools/ab_test.py --a-path versions/m3                     # old tree vs working tree
  python3 tools/ab_test.py --b-set CBET_FREQ=0.5 --quick --fields soft --payouts flat

Paired per table. A change is adopted only when the 95% CI of (B - A) excludes zero
in its favor; the verdict also sums every cell as a percent of its even share.
"""
import argparse
import math
import time

import _paths  # noqa: F401
from run_sim import parse_overrides
from sim import settings as S
from sim.runner import run_tables, mean_ci, default_workers


def compare(a, b, field, payout_name, tables, seed, workers):
    payouts = S.PAYOUTS[payout_name]
    ra = run_tables(a, field, payouts, tables, seed, workers)
    rb = run_tables(b, field, payouts, tables, seed, workers)
    diffs = [y["points"] - x["points"] for x, y in zip(ra, rb)]
    mean_a = sum(r["points"] for r in ra) / len(ra)
    mean_b = sum(r["points"] for r in rb) / len(rb)
    d, ci = mean_ci(diffs)
    faults = sum(r["exceptions"] + r["timeouts"] + r["illegal"] + r["fallbacks"] for r in ra + rb)
    return {"a": mean_a, "b": mean_b, "d": d, "ci": ci, "faults": faults,
            "unit": sum(payouts) / len(payouts)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a-path", default=None)
    ap.add_argument("--b-path", default=None)
    ap.add_argument("--a-set", action="append")
    ap.add_argument("--b-set", action="append")
    ap.add_argument("--self-path", default=None, help="bot used for 'self' field seats in both arms")
    ap.add_argument("--tables", type=int, default=1000)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--fields", default="soft,tough,all_tag,with_self")
    ap.add_argument("--payouts", default=",".join(S.PAYOUTS))
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--workers", type=int, default=default_workers())
    args = ap.parse_args()
    tables = 500 if args.quick else args.tables
    common = {"self_path": args.self_path}
    a = dict(common, path=args.a_path, overrides=parse_overrides(args.a_set))
    b = dict(common, path=args.b_path, overrides=parse_overrides(args.b_set))
    t0 = time.time()
    print(f"{'field':<11}{'payout':<11}{'A':>9}{'B':>9}{'B-A':>9}{'+/-95%':>8}{'sig':>6}{'faults':>8}")
    rel = []
    rel_var = []
    for field in args.fields.split(","):
        for pay in args.payouts.split(","):
            r = compare(a, b, field, pay, tables, args.seed, args.workers)
            sig = "B+" if r["d"] - r["ci"] > 0 else ("A+" if r["d"] + r["ci"] < 0 else "-")
            print(f"{field:<11}{pay:<11}{r['a']:>9.3f}{r['b']:>9.3f}{r['d']:>+9.3f}{r['ci']:>8.3f}{sig:>6}{r['faults']:>8}", flush=True)
            rel.append(r["d"] / r["unit"])
            rel_var.append((r["ci"] / 1.96 / r["unit"]) ** 2)
    overall = sum(rel) / len(rel)
    overall_ci = 1.96 * math.sqrt(sum(rel_var)) / len(rel)
    verdict = "ADOPT B" if overall - overall_ci > 0 else ("KEEP A (A better)" if overall + overall_ci < 0 else "NO SIGNIFICANT DIFFERENCE")
    print(f"\noverall B-A: {overall*100:+.2f}% of even share, +/-{overall_ci*100:.2f}%  -> {verdict}   ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
