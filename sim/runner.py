"""Multiprocess table runner. A table's cards and field depend only on (seed, index),
so two hero versions run on the same seeds see identical decks and opponents."""
import gc
import math
import multiprocessing as mp
import os
import random

from . import settings as S
from .loader import load_agent_class
from .tournament import play_table

_baselines = None


def _baseline_classes():
    global _baselines
    if _baselines is None:
        from baselines import REGISTRY
        _baselines = REGISTRY
    return _baselines


def _make_bot(name, seed, payouts, self_cls):
    if name == "self":
        return self_cls(seed=seed, payouts=payouts)
    return _baseline_classes()[name](seed=seed)


def _table_seed(seed, index):
    return (seed * 1_000_003 + index) & 0x7FFFFFFF


def run_chunk(args):
    """Runs tables [start, end) with one hero. Returns one row per table."""
    hero, field, payouts, seed, start, end, time_limit_ns, wall_clock = args
    hero_cls = load_agent_class(hero.get("path"), hero.get("overrides"))
    self_cls = load_agent_class(hero.get("self_path"), hero.get("self_overrides"))
    weights = S.FIELDS[field]
    names = list(weights)
    w = [weights[k] for k in names]
    gc.collect()
    gc.freeze()
    rows = []
    for index in range(start, end):
        ts = _table_seed(seed, index)
        rng = random.Random(ts)
        hero_seat = rng.randrange(S.SEATS)
        field_names = rng.choices(names, weights=w, k=S.SEATS)
        agents = []
        seat_names = []
        for s in range(S.SEATS):
            bot_seed = rng.getrandbits(32)
            if s == hero_seat:
                agents.append(hero_cls(seed=bot_seed, payouts=payouts))
                seat_names.append("HERO")
            else:
                agents.append(_make_bot(field_names[s], bot_seed, payouts, self_cls))
                seat_names.append(field_names[s])
        r = play_table(agents, payouts, ts + 1, time_limit_ns=time_limit_ns, wall_clock=wall_clock)
        by_name = {}
        field_faults = 0
        for s, nm in enumerate(seat_names):
            by_name.setdefault(nm, []).append(r["points"][s])
            st = r["stats"][s]
            if s != hero_seat:
                field_faults += st.timeouts + st.exceptions + st.illegal
        hs = r["stats"][hero_seat]
        hero_bot = agents[hero_seat]
        rows.append({
            "index": index, "points": r["points"][hero_seat], "place": r["places"][hero_seat],
            "hands": r["hands"], "capped": r["capped"],
            "decisions": hs.decisions, "timeouts": hs.timeouts, "exceptions": hs.exceptions,
            "illegal": hs.illegal, "total_ns": hs.total_ns, "max_ns": hs.max_ns,
            "max_cpu_ns": hs.max_cpu_ns, "jitter": hs.jitter,
            "fallbacks": getattr(hero_bot, "fallbacks", 0),
            "last_error": repr(getattr(hero_bot, "last_error", None)) if getattr(hero_bot, "fallbacks", 0) else None,
            "field_faults": field_faults, "by_name": by_name,
        })
    return rows


def default_workers():
    return max(1, (os.cpu_count() or 2) - 1)


def run_tables(hero, field, payouts, tables, seed=1, workers=None, time_limit_ns=S.TIME_LIMIT_NS,
               wall_clock=False):
    """hero: {'path', 'overrides', 'self_path', 'self_overrides'}. Rows come back sorted by table."""
    workers = workers or default_workers()
    chunk = max(5, min(100, tables // (workers * 4) or 5))
    jobs = [(hero, field, payouts, seed, i, min(i + chunk, tables), time_limit_ns, wall_clock)
            for i in range(0, tables, chunk)]
    rows = []
    if workers == 1:
        for j in jobs:
            rows.extend(run_chunk(j))
    else:
        with mp.get_context("spawn").Pool(workers) as pool:
            for part in pool.imap_unordered(run_chunk, jobs):
                rows.extend(part)
    rows.sort(key=lambda r: r["index"])
    return rows


def mean_ci(xs):
    """Mean and 95% half-width."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    m = sum(xs) / n
    if n == 1:
        return m, 0.0
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, 1.96 * math.sqrt(var / n)


def summarize(rows, n_places=S.SEATS):
    pts = [r["points"] for r in rows]
    m, ci = mean_ci(pts)
    dist = [0.0] * n_places
    for r in rows:
        p = r["place"]
        lo = int(p)
        if p == lo:
            dist[lo] += 1
        else:                # tied busts split the place
            dist[lo] += 0.5
            dist[lo + 1] += 0.5
    t = len(rows) or 1
    field_points = {}
    for r in rows:
        for name, vals in r["by_name"].items():
            field_points.setdefault(name, []).extend(vals)
    return {
        "tables": len(rows), "mean": m, "ci": ci, "dist": [d / t for d in dist],
        "decisions": sum(r["decisions"] for r in rows),
        "timeouts": sum(r["timeouts"] for r in rows),
        "exceptions": sum(r["exceptions"] for r in rows),
        "illegal": sum(r["illegal"] for r in rows),
        "field_faults": sum(r["field_faults"] for r in rows),
        "avg_us": sum(r["total_ns"] for r in rows) / max(1, sum(r["decisions"] for r in rows)) / 1000,
        "max_us": max((r["max_ns"] for r in rows), default=0) / 1000,
        "max_cpu_us": max((r["max_cpu_ns"] for r in rows), default=0) / 1000,
        "jitter": sum(r["jitter"] for r in rows),
        "fallbacks": sum(r["fallbacks"] for r in rows),
        "errors": sorted({r["last_error"] for r in rows if r["last_error"]})[:5],
        "avg_hands": sum(r["hands"] for r in rows) / t,
        "capped": sum(1 for r in rows if r["capped"]) / t,
        "field_points": {k: sum(v) / len(v) for k, v in field_points.items()},
    }
