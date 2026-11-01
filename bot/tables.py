"""Precomputed preflop data, loaded once at import.

A hand class groups equivalent starting hands. Two hole cards: rank grid (169 in
hold'em). More hole cards: coarse feature buckets. With no data file, a formula
fills the same tables so the bot still plays reasonably right after a variant switch.
"""
import json
import os

from . import config
from .evaluator import RANK_OF, SUIT_OF, NR, NS, HOLE_CARDS

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                         config.ACTIVE_VARIANT + ".json")
MAX_CHART_BB = 15
MAX_BEHIND = 7
N_DECK = NR * NS

if HOLE_CARDS == 2:
    N_CLASSES = NR * NR
    _CLASS2 = [0] * (N_DECK * N_DECK)
    for _a in range(N_DECK):
        for _b in range(N_DECK):
            _hi, _lo = max(RANK_OF[_a], RANK_OF[_b]), min(RANK_OF[_a], RANK_OF[_b])
            if SUIT_OF[_a] == SUIT_OF[_b]:
                _CLASS2[_a * N_DECK + _b] = _hi * NR + _lo      # suited: upper triangle
            else:
                _CLASS2[_a * N_DECK + _b] = _lo * NR + _hi      # offsuit & pairs

    def class_of(hole):
        return _CLASS2[hole[0] * N_DECK + hole[1]]
else:
    N_CLASSES = 81

    def class_of(hole):
        """Bucket: top card (3), pairs (3), suitedness (3), connectedness (3)."""
        ranks = sorted(RANK_OF[c] for c in hole)
        top = ranks[-1]
        hi = 2 if top == NR - 1 else (1 if top >= NR - 3 else 0)
        pairs = 0
        conn = 0
        for i in range(len(ranks) - 1):
            gap = ranks[i + 1] - ranks[i]
            if gap == 0:
                pairs += 1
            elif gap <= 2:
                conn += 1
        suit_counts = [0] * NS
        for c in hole:
            suit_counts[SUIT_OF[c]] += 1
        suited = sum(1 for x in suit_counts if x >= 2)
        return (hi * 27 + min(pairs, 2) * 9 + min(suited, 2) * 3 + min(conn, 2))


def _class_score(cls):
    """Formula strength for the no-data fallback. Bigger is better."""
    if HOLE_CARDS == 2:
        a, b = cls // NR, cls % NR
        hi, lo = max(a, b), min(a, b)
        s = hi * 0.6 + lo * 0.25
        if a == b:
            s += NR * 0.35
        elif a > b:
            s += 0.8                 # suited
        s -= min(hi - lo, 4) * 0.15 if a != b else 0
        return s
    hi, rest = cls // 27, cls % 27
    pairs, rest = rest // 9, rest % 9
    suited, conn = rest // 3, rest % 3
    return hi * 2.0 + pairs * 1.2 + suited * 1.5 + conn * 1.0


def _class_weight(cls):
    if HOLE_CARDS != 2:
        return 1.0
    a, b = cls // NR, cls % NR
    if a == b:
        return NS * (NS - 1) / 2
    return NS if a > b else NS * (NS - 1)


def _fallback():
    order = sorted(range(N_CLASSES), key=_class_score, reverse=True)
    total = sum(_class_weight(c) for c in order)
    pct = [0.0] * N_CLASSES
    run = 0.0
    for c in order:
        run += _class_weight(c)
        pct[c] = run / total
    eq_top = []
    eq_random = []
    for c in range(N_CLASSES):
        # Linear stand-in: a hand's equity falls with its percentile, rises as the range widens.
        row = []
        for p in range(101):
            row.append(max(0.15, min(0.85, 0.5 + 0.38 * (p / 100 * 0.5 - pct[c] * 0.5) / 0.5)))
        eq_top.append(row)
        eq_random.append([max(0.05, (1 - pct[c] * 0.65) ** (1 + k * 0.6) * 0.85) for k in range(7)])
    push = [[0.0] * (MAX_CHART_BB + 1) for _ in range(MAX_BEHIND + 1)]
    for b in range(1, MAX_BEHIND + 1):
        for s in range(1, MAX_CHART_BB + 1):
            push[b][s] = min(1.0, (0.55 / b + 0.08) * (1.0 + 4.0 / s) / 1.3)
    call = [[[0.0] * (MAX_CHART_BB + 1) for _ in range(MAX_BEHIND + 1)] for _ in range(MAX_BEHIND + 1)]
    for sb in range(1, MAX_BEHIND + 1):
        for cb in range(sb):
            for s in range(1, MAX_CHART_BB + 1):
                call[sb][cb][s] = min(1.0, push[sb][s] * 0.6)
    return {"pct": pct, "order": order, "eq_top": eq_top, "eq_random": eq_random,
            "push": push, "call": call, "source": "fallback"}


def _load():
    try:
        with open(DATA_PATH) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return _fallback()
    # Stored as per-mille ints to stay compact; convert once here.
    d["eq_top"] = [[v / 1000.0 for v in row] for row in d["eq_top"]]
    d["eq_random"] = [[v / 1000.0 for v in row] for row in d["eq_random"]]
    d["source"] = "file"
    return d


DATA = _load()
SOURCE = DATA["source"]
PCT = DATA["pct"]
ORDER = DATA["order"]
EQ_TOP = DATA["eq_top"]
EQ_RANDOM = DATA["eq_random"]
PUSH = DATA["push"]
CALL = DATA["call"]


def eq_vs_top(cls, range_pct):
    """Equity of a hand class against the top range_pct of hands."""
    i = int(range_pct * 100 + 0.5)
    if i < 1:
        i = 1
    elif i > 100:
        i = 100
    return EQ_TOP[cls][i]


def _clamp_chart(behind, bb):
    s = int(bb + 0.5)
    if s < 1:
        s = 1
    elif s > MAX_CHART_BB:
        s = MAX_CHART_BB
    if behind > MAX_BEHIND:
        behind = MAX_BEHIND
    return behind, s


def push_pct(behind, bb):
    """Shove threshold (top X%) with `behind` players still to act and bb effective BBs."""
    behind, s = _clamp_chart(behind, bb)
    return PUSH[behind][s]


def call_pct(shover_behind, caller_behind, bb):
    """Calling threshold against a shove."""
    shover_behind, s = _clamp_chart(shover_behind, bb)
    if caller_behind >= shover_behind:
        caller_behind = shover_behind - 1 if shover_behind > 0 else 0
    return CALL[shover_behind][caller_behind][s]
