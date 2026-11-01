#!/usr/bin/env python3
"""Run a quick sim plus one recorded table and write the data the visual page uses.

  python3 tools/export_viz.py --out results/viz.json     # about 40 s
"""
import argparse
import json
import random
import time

import _paths  # noqa: F401
from baselines import REGISTRY
from bot.agent import Agent
from bot import evaluator as E
from sim import settings as S
from sim.runner import run_tables, summarize, default_workers
from sim.tournament import blinds_for, award_busted
from sim.engine import play_hand, SeatStats
from bot.icm import icm_equities

CATS = ["High card", "Pair", "Two pair", "Trips", "Straight", "Flush", "Full house", "Quads", "Straight flush"]


def record_table(payouts, seed, lineup):
    """Same flow as play_table, keeping every hand for replay."""
    n = len(lineup)
    rng = random.Random(seed)
    agents = [Agent(seed=rng.getrandbits(32), payouts=payouts) if nm == "OUR BOT"
              else REGISTRY[nm](seed=rng.getrandbits(32)) for nm in lineup]
    stacks = [S.STARTING_STACK] * n
    stats = [SeatStats() for _ in range(n)]
    points = [None] * n
    places = [0] * n
    button = rng.randrange(n)
    alive = n
    hand_no = 0
    deal = n * E.HOLE_CARDS + E.BOARD_CARDS
    hands = []
    while hand_no < S.MAX_HANDS and alive > 1:
        hand_no += 1
        sb, bb = blinds_for(hand_no)
        deck = rng.sample(E.DECK, deal)
        start = list(stacks)
        r = play_hand(agents, stats, stacks, button, sb, bb, S.ANTE, deck, hand_no, None)
        for a in agents:
            if hasattr(a, "on_hand_end"):
                a.on_hand_end(r)
        shown = {s: CATS[E.category(v)] for s, v in r["values"].items()}
        hands.append({
            "n": hand_no, "button": button, "sb": sb, "bb": bb, "start": start, "end": list(stacks),
            "holes": [[E.CARD_STR[c] for c in h] if start[i] > 0 else None for i, h in enumerate(r["holes"])],
            "board": [E.CARD_STR[c] for c in r["board"]],
            "actions": [[e[0], e[1], e[2], e[3], bool(e[4])] for e in r["history"]],
            "shown": {str(k): v for k, v in shown.items()},
        })
        busted = [s for s in range(n) if start[s] > 0 and stacks[s] == 0]
        if busted:
            alive -= len(busted)
            award_busted(busted, start, alive, payouts, points, places)
        button = (button + 1) % n
        while stacks[button] == 0 and alive > 0:
            button = (button + 1) % n
    if alive == 1:
        w = next(s for s in range(n) if stacks[s] > 0)
        points[w] = payouts[0]
        places[w] = 0
    else:
        eq = icm_equities(stacks, payouts[:alive])
        order = sorted((s for s in range(n) if stacks[s] > 0), key=lambda s: -stacks[s])
        for rank, s in enumerate(order):
            points[s] = eq[s]
            places[s] = rank
    return {"lineup": lineup, "hands": hands, "points": points, "places": places,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", type=int, default=500)
    ap.add_argument("--seed", type=int, default=21)
    ap.add_argument("--out", default="results/viz.json")
    args = ap.parse_args()
    t0 = time.time()
    out = {"tables": args.tables, "cells": [], "benchmarks": {}}
    for field in S.FIELDS:
        for pay in S.PAYOUTS:
            s = summarize(run_tables({}, field, S.PAYOUTS[pay], args.tables, args.seed, default_workers()))
            out["cells"].append({"field": field, "payout": pay, "even": sum(S.PAYOUTS[pay]) / 8,
                                 **{k: s[k] for k in ("mean", "ci", "dist", "decisions", "timeouts", "exceptions",
                                                      "illegal", "fallbacks", "jitter", "avg_us", "max_cpu_us",
                                                      "avg_hands", "capped", "field_points")}})
            print(field, pay, round(s["mean"], 2), flush=True)
    # Pick a table that shows off a full game: our bot in with a mixed field.
    lineup = ["OUR BOT", "simple_tag", "naive_equity", "maniac", "calling_station", "nit", "simple_tag", "naive_equity"]
    out["replay"] = record_table(S.PAYOUTS["top_heavy"], args.seed, lineup)
    with open(args.out, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {args.out}, hands in replay {len(out['replay']['hands'])}, place {out['replay']['places'][0]}, {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
