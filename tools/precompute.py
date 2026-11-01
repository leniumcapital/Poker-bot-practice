#!/usr/bin/env python3
"""Generate bot/data/<variant>.json. Target: <= ~5 minutes for any variant.

  python3 tools/precompute.py                       # active variant, default trials
  python3 tools/precompute.py --variant shortdeck
  python3 tools/precompute.py --quick               # fast and noisier, for a first pass

Steps: 1) equity vs 1-7 random opponents  2) class-vs-class equity matrix
3) strength ordering -> percentiles  4) equity vs top-X% ranges
5) push/fold charts by iterated best response.
"""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import time

import _paths  # noqa: F401


def setup(variant):
    if variant:
        os.environ["POKERBOT_VARIANT"] = variant


def _class_hands(rng):
    """All hands per class (2 cards), or a large random sample per bucket (3+ cards)."""
    from bot import evaluator as E, tables as T
    hands = {}
    if E.HOLE_CARDS == 2:
        for a in E.DECK:
            for b in E.DECK:
                if a < b:
                    hands.setdefault(T.class_of([a, b]), []).append((a, b))
        return hands, {c: float(len(h)) for c, h in hands.items()}
    weights = {}
    for _ in range(200_000):
        hole = tuple(rng.sample(E.DECK, E.HOLE_CARDS))
        c = T.class_of(hole)
        weights[c] = weights.get(c, 0) + 1.0
        lst = hands.setdefault(c, [])
        if len(lst) < 2000:
            lst.append(hole)
    return hands, weights


def _eq_random_job(args):
    cls, hands, trials, seed = args
    from bot import evaluator as E
    rng = random.Random(seed)
    evaluate = E.evaluate
    deck = E.DECK
    h = E.HOLE_CARDS
    bc = E.BOARD_CARDS
    out = []
    for opps in range(1, 8):
        score = 0.0
        for _ in range(trials):
            mine = rng.choice(hands)
            rest = [c for c in deck if c not in mine]
            cards = rng.sample(rest, opps * h + bc)
            board = cards[:bc]
            me = evaluate(mine, board)
            best = me
            ties = 1
            for k in range(opps):
                v = evaluate(cards[bc + k * h:bc + (k + 1) * h], board)
                if v > best:
                    best = v
                    ties = 0
                elif v == best:
                    ties += 1
            if best == me and ties > 0:
                score += 1.0 / ties
        out.append(score / trials)
    return cls, out


def _matrix_job(args):
    a, row_classes, all_hands, trials, seed = args
    from bot import evaluator as E
    rng = random.Random(seed)
    evaluate = E.evaluate
    deck = E.DECK
    bc = E.BOARD_CARDS
    hands_a = all_hands[a]
    out = {}
    for b in row_classes:
        hands_b = all_hands[b]
        score = 0.0
        done = 0
        attempts = 0
        while done < trials and attempts < trials * 20:
            attempts += 1
            x = rng.choice(hands_a)
            y = rng.choice(hands_b)
            if set(x) & set(y):
                continue
            used = set(x) | set(y)
            board = []
            while len(board) < bc:
                c = rng.choice(deck)
                if c not in used:
                    used.add(c)
                    board.append(c)
            va = evaluate(x, board)
            vb = evaluate(y, board)
            score += 1.0 if va > vb else (0.5 if va == vb else 0.0)
            done += 1
        out[b] = score / done if done else 0.5
    return a, out


def compat_weights(classes, hands, weights):
    """Combos of b still possible given a representative hand of a (card removal)."""
    from bot import evaluator as E
    if E.HOLE_CARDS != 2:
        return None
    out = {}
    for a in classes:
        rep = set(hands[a][0])
        out[a] = {b: sum(1 for h in hands[b] if not (rep & set(h))) for b in classes}
    return out


def build_eq_top(classes, order, weights, matrix, compat):
    """eq_top[a][p] = equity of class a vs the top p% (p = 0..100) of the ordering."""
    total = sum(weights[c] for c in classes)
    eq_top = {}
    for a in classes:
        row = [0.5] * 101
        cum_w = 0.0        # weight of the range so far (raw combos)
        sum_w = 0.0        # weight actually available after card removal
        sum_eq = 0.0
        i = 0
        for p in range(1, 101):
            target = total * p / 100
            while i < len(order) and cum_w + weights[order[i]] <= target + 1e-9:
                b = order[i]
                w = compat[a][b] if compat else weights[b]
                if a == b and not compat:
                    w = weights[b] * 0.8
                sum_w += w
                sum_eq += w * matrix[a][b]
                cum_w += weights[b]
                i += 1
            if sum_w > 0:
                row[p] = sum_eq / sum_w
            elif i < len(order):
                # The range is still inside the first class: use that class's equity.
                row[p] = matrix[a][order[0]]
        eq_top[a] = row
    return eq_top


def best_threshold(order, pct, weights, ev_of):
    """Best response restricted to 'top X%': the cut with the highest cumulative EV.

    Strength order is not monotonic in shove EV (suited connectors sit above weak
    offsuit aces), so stopping at the first -EV hand cuts ranges far too tight.
    """
    run = 0.0
    best_run = 0.0
    best = 0.0
    for c in order:
        run += weights[c] * ev_of(c)
        if run > best_run:
            best_run = run
            best = pct[c]
    return best


def iterated_best_response(order, pct, eq_top, weights, max_behind=7, max_bb=15, ante_dead=0.0, iters=40):
    """Chip-EV shove/call equilibrium approximation.

    The players who already folded do not matter (no antes), so charts key on how many
    players are still to act behind the shover. Stacks are equal; at most the first
    caller is modeled, which is close enough when calling ranges are tight.
    """
    push = [[0.0] * (max_bb + 1) for _ in range(max_behind + 1)]
    call = [[[0.0] * (max_bb + 1) for _ in range(max_behind + 1)] for _ in range(max_behind + 1)]
    post = lambda behind: 0.5 if behind == 1 else (1.0 if behind == 0 else 0.0)
    for s in range(1, max_bb + 1):
        cur_push = [0.0] + [min(1.0, 0.5 / b + 0.1) for b in range(1, max_behind + 1)]
        cur_call = [[0.2 for _ in range(max_behind + 1)] for _ in range(max_behind + 1)]
        for it in range(iters):
            damp = 1.0 / (1 + it * 0.25)
            # Callers respond to the shovers.
            for sb in range(1, max_behind + 1):
                ridx = max(1, int(cur_push[sb] * 100 + 0.5))
                dead = 1.5 + ante_dead
                for cb in range(sb):
                    risk = s - post(cb)
                    pot = 2 * s + dead - post(sb) - post(cb)
                    best = best_threshold(order, pct, weights,
                                          lambda c: eq_top[c][ridx] * pot - risk)
                    cur_call[sb][cb] += damp * (best - cur_call[sb][cb])
            # Shovers respond to the callers.
            for sb in range(1, max_behind + 1):
                probs = []
                folded = 1.0
                for cb in range(sb - 1, -1, -1):
                    f = cur_call[sb][cb]
                    probs.append((cb, folded * f, max(1, int(f * 100 + 0.5))))
                    folded *= 1 - f
                dead = 1.5 + ante_dead

                def shove_ev(c):
                    ev = folded * (dead - post(sb))
                    for cb, p, ridx in probs:
                        pot = 2 * s + dead - post(sb) - post(cb)
                        ev += p * (eq_top[c][ridx] * pot - (s - post(sb)))
                    return ev
                best = best_threshold(order, pct, weights, shove_ev)
                cur_push[sb] += damp * (best - cur_push[sb])
        for b in range(1, max_behind + 1):
            push[b][s] = round(cur_push[b], 4)
            for cb in range(b):
                call[b][cb][s] = round(cur_call[b][cb], 4)
    return push, call


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default=None)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--random-trials", type=int, default=None)
    ap.add_argument("--matrix-trials", type=int, default=None)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()
    setup(args.variant)
    from bot import config, evaluator as E, tables as T

    t0 = time.time()
    rng = random.Random(args.seed)
    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
    hands, weights = _class_hands(rng)
    classes = sorted(hands)
    big = E.HOLE_CARDS > 2 or E.MUST_USE
    rand_trials = args.random_trials or (800 if args.quick else (1500 if big else 6000))
    mat_trials = args.matrix_trials or (150 if args.quick else (300 if big else 1200))
    print(f"variant={config.ACTIVE_VARIANT} classes={len(classes)} random_trials={rand_trials} "
          f"matrix_trials={mat_trials} workers={workers}", flush=True)

    ctx = mp.get_context("spawn")
    env = {"POKERBOT_VARIANT": config.ACTIVE_VARIANT}
    os.environ.update(env)
    with ctx.Pool(workers) as pool:
        jobs = [(c, hands[c], rand_trials, rng.getrandbits(32)) for c in classes]
        eq_random = dict(pool.imap_unordered(_eq_random_job, jobs))
        print(f"  equity vs random done {time.time()-t0:.0f}s", flush=True)
        matrix = {c: {} for c in classes}
        rows = []
        for i, a in enumerate(classes):
            rows.append((a, classes[i:], hands, mat_trials, rng.getrandbits(32)))
        for a, out in pool.imap_unordered(_matrix_job, rows):
            for b, v in out.items():
                matrix[a][b] = v
                matrix[b][a] = 1.0 - v if a != b else 0.5
    print(f"  matrix done {time.time()-t0:.0f}s", flush=True)

    # Strength order: blend of heads-up and multiway equity, so suited and connected
    # hands rank above weak offsuit aces the way real open ranges do.
    score = {c: 0.6 * eq_random[c][0] + 0.4 * eq_random[c][2] * 2.2 for c in classes}
    order = sorted(classes, key=lambda c: -score[c])
    total = sum(weights[c] for c in classes)
    pct = [1.0] * T.N_CLASSES
    run = 0.0
    for c in order:
        run += weights[c]
        pct[c] = round(run / total, 5)

    compat = compat_weights(classes, hands, weights)
    eq_top_d = build_eq_top(classes, order, weights, matrix, compat)
    print(f"  eq_top done {time.time()-t0:.0f}s", flush=True)

    eq_top = [[500] * 101 for _ in range(T.N_CLASSES)]
    eq_rand = [[200] * 7 for _ in range(T.N_CLASSES)]
    for c in classes:
        eq_top[c] = [int(round(v * 1000)) for v in eq_top_d[c]]
        eq_rand[c] = [int(round(v * 1000)) for v in eq_random[c]]

    eq_top_float = {c: eq_top_d[c] for c in classes}
    push, call = iterated_best_response(order, pct, eq_top_float, weights)
    print(f"  push/fold done {time.time()-t0:.0f}s", flush=True)

    data = {"variant": config.ACTIVE_VARIANT, "order": order, "pct": pct, "eq_top": eq_top,
            "eq_random": eq_rand, "push": push, "call": call}
    os.makedirs(os.path.dirname(T.DATA_PATH), exist_ok=True)
    tmp = T.DATA_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, T.DATA_PATH)      # atomic: a failed run never leaves half a table
    size = os.path.getsize(T.DATA_PATH)
    t1 = time.time()
    with open(T.DATA_PATH) as f:
        json.load(f)
    print(f"wrote {T.DATA_PATH}  {size/1024:.0f} KB  json load {(time.time()-t1)*1000:.1f} ms  "
          f"total {time.time()-t0:.0f}s")


if __name__ == "__main__":
    sys.exit(main())
