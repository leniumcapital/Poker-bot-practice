#!/usr/bin/env python3
"""Screen config candidates against one shared baseline run on identical seeds.

  python3 tools/tune.py --only open_tight,cbet_50 --seed 12   # about 25 s per candidate

Name a few candidates: running all of them takes about 10 minutes even at the default size.

Reading the output: at 95% confidence about 1 candidate in 20 "wins" by luck, so
treat a screen win as a lead. Adopt only after it repeats on a new seed.
"""
import argparse
import json
import math
import time

import _paths  # noqa: F401
from bot import config as BOT_CONFIG
from sim import settings as S
from sim.runner import run_tables, mean_ci, default_workers

_OPEN = BOT_CONFIG.OPEN_PCT      # candidates scale whatever the config currently holds


def open_scale(x):
    return {f"OPEN_PCT.{k}": round(v * x, 3) for k, v in _OPEN.items()}


CANDIDATES = {
    "open_tight": open_scale(0.8),
    "open_loose": open_scale(1.2),
    "icm_w_60": {"ICM_WEIGHT": 0.6},
    "icm_w_150": {"ICM_WEIGHT": 1.5},
    "icm_shove_75": {"ICM_SHOVE_TIGHTEN": 0.75},
    "icm_shove_250": {"ICM_SHOVE_TIGHTEN": 2.5},
    "tier_down": {"TIER_EQUITY": [0.10, 0.30, 0.50, 0.68, 0.84, 0.96]},
    "tier_up": {"TIER_EQUITY": [0.16, 0.42, 0.60, 0.76, 0.88, 0.96]},
    "betpen_08": {"BET_SIZE_PENALTY": 0.08},
    "betpen_22": {"BET_SIZE_PENALTY": 0.22},
    "cbet_50": {"CBET_FREQ": 0.50},
    "cbet_85": {"CBET_FREQ": 0.85},
    "fe_04": {"RESHOVE_FE_BONUS": 0.04},
    "fe_12": {"RESHOVE_FE_BONUS": 0.12},
    "value_big": {"VALUE_BET_DRY": 0.70, "VALUE_BET_WET": 0.90},
    "short_10": {"SHORT_MAX_BB": 10},
    "short_15": {"SHORT_MAX_BB": 15},
    "tbet_5": {"THREEBET_VALUE_PCT": 0.05},
    "allin_margin_p2": {"CALL_ALLIN_MARGIN": 0.02},
    "allin_margin_m2": {"CALL_ALLIN_MARGIN": -0.02},
    # Round 2: further along the trends, and the winners combined.
    "open_140": open_scale(1.4),
    "tier_down2": {"TIER_EQUITY": [0.08, 0.25, 0.46, 0.65, 0.82, 0.96]},
    "betpen_30": {"BET_SIZE_PENALTY": 0.30},
    "combo_call": {"TIER_EQUITY": [0.10, 0.30, 0.50, 0.68, 0.84, 0.96], "BET_SIZE_PENALTY": 0.22},
    "combo_all": dict(open_scale(1.2), TIER_EQUITY=[0.10, 0.30, 0.50, 0.68, 0.84, 0.96],
                      BET_SIZE_PENALTY=0.22, ICM_SHOVE_TIGHTEN=0.75),
}


def run_cells(hero, tables, seed, workers, fields, payouts):
    return {(f, p): run_tables(hero, f, S.PAYOUTS[p], tables, seed, workers)
            for f in fields for p in payouts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", type=int, default=500)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--only", default=None)
    ap.add_argument("--base-set", default="{}", help="JSON overrides applied to base and every candidate")
    ap.add_argument("--fields", default="soft,tough,all_tag,with_self")
    ap.add_argument("--payouts", default=",".join(S.PAYOUTS))
    ap.add_argument("--workers", type=int, default=default_workers())
    args = ap.parse_args()
    fields = args.fields.split(",")
    payouts = args.payouts.split(",")
    names = args.only.split(",") if args.only else list(CANDIDATES)
    base_over = json.loads(args.base_set)
    t0 = time.time()
    base = run_cells({"overrides": base_over}, args.tables, args.seed, args.workers, fields, payouts)
    print(f"baseline done {time.time()-t0:.0f}s   seed={args.seed} tables/cell={args.tables}", flush=True)
    print(f"{'candidate':<18}{'overall %even':>14}{'+/-95%':>8}{'verdict':>10}  "
          f"{'worst cell':<24}{'sig wins':>9}{'sig losses':>11}{'faults':>7}", flush=True)
    for name in names:
        over = dict(base_over)
        over.update(CANDIDATES[name])
        cand = run_cells({"overrides": over}, args.tables, args.seed, args.workers, fields, payouts)
        rel, var = [], []
        wins = losses = faults = 0
        worst = ("", 1e9)
        for key, rows in cand.items():
            unit = sum(S.PAYOUTS[key[1]]) / len(S.PAYOUTS[key[1]])
            diffs = [y["points"] - x["points"] for x, y in zip(base[key], rows)]
            d, ci = mean_ci(diffs)
            rel.append(d / unit)
            var.append((ci / 1.96 / unit) ** 2)
            wins += d - ci > 0
            losses += d + ci < 0
            faults += sum(r["exceptions"] + r["timeouts"] + r["illegal"] + r["fallbacks"] for r in rows)
            if d / unit < worst[1]:
                worst = (f"{key[0]}/{key[1]}", d / unit)
        overall = sum(rel) / len(rel)
        oci = 1.96 * math.sqrt(sum(var)) / len(rel)
        verdict = "better" if overall - oci > 0 else ("worse" if overall + oci < 0 else "-")
        print(f"{name:<18}{overall*100:>+14.2f}{oci*100:>8.2f}{verdict:>10}  "
              f"{worst[0]:<16}{worst[1]*100:>+7.1f}%{wins:>9}{losses:>11}{faults:>7}", flush=True)
    print(f"total {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
