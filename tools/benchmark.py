#!/usr/bin/env python3
"""Time act() on realistic states captured from real tables.

Gates: wall-clock p99 <= 0.25 ms and CPU max <= 0.6 ms. The wall max is printed next
to a no-op control because this machine's scheduler preempts even empty sections
(see ASSUMPTIONS.md); a wall max in line with the control says nothing about the bot.
"""
import argparse
import random
import sys
from time import perf_counter_ns, thread_time_ns

import _paths  # noqa: F401
from baselines import REGISTRY
from sim.loader import load_agent_class
from sim.tournament import play_table

P99_LIMIT_US = 250.0
MAX_LIMIT_US = 600.0


class Recorder:
    """Plays through the real agent and keeps a copy of every state it was asked about."""
    def __init__(self, inner, store):
        self.inner = inner
        self.store = store

    def act(self, state):
        snap = dict(state)
        snap["history"] = list(state["history"])
        self.store.append(snap)
        return self.inner.act(state)

    def on_hand_end(self, result):
        self.inner.on_hand_end(result)


def capture(agent_cls, count, seed):
    rng = random.Random(seed)
    names = list(REGISTRY)
    states = []
    table = 0
    while len(states) < count:
        table += 1
        store = []
        hero = rng.randrange(8)
        agents = []
        for s in range(8):
            if s == hero or rng.random() < 0.25:
                a = agent_cls(seed=rng.getrandbits(32))
                agents.append(Recorder(a, store) if s == hero else a)
            else:
                agents.append(REGISTRY[rng.choice(names)](seed=rng.getrandbits(32)))
        play_table(agents, [100, 50, 25, 10, 5, 0, 0, 0], rng.getrandbits(32), time_limit_ns=None)
        states.append(store)
        count -= len(store) - 1
    return states


def pct(sorted_vals, p):
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * p))] / 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calls", type=int, default=100_000)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--path", default=None)
    args = ap.parse_args()
    agent_cls = load_agent_class(args.path)
    tables = capture(agent_cls, args.calls, args.seed)
    n_states = sum(len(t) for t in tables)
    wall, cpu, ctl = [], [], []
    wa, ca = wall.append, cpu.append
    pc, tc = perf_counter_ns, thread_time_ns
    calls = 0
    while calls < args.calls:
        for table in tables:
            bot = agent_cls(seed=calls)
            act = bot.act
            for state in table:
                c0 = tc()
                t0 = pc()
                act(state)
                t1 = pc()
                c1 = tc()
                wa(t1 - t0)
                ca(c1 - c0)
                calls += 1
            if calls >= args.calls:
                break
    # Control: the same measurement around nothing at all.
    for _ in range(args.calls):
        t0 = pc()
        t1 = pc()
        ctl.append(t1 - t0)
    wall.sort()
    cpu.sort()
    ctl.sort()
    print(f"states captured {n_states}, calls {calls}, tables {len(tables)}")
    print(f"{'':<8}{'mean_us':>9}{'p50_us':>9}{'p99_us':>9}{'p99.9_us':>10}{'max_us':>10}")
    for name, v in (("wall", wall), ("cpu", cpu), ("no-op", ctl)):
        print(f"{name:<8}{sum(v)/len(v)/1000:>9.1f}{pct(v,.5):>9.1f}{pct(v,.99):>9.1f}{pct(v,.999):>10.1f}{v[-1]/1000:>10.1f}")
    p99 = pct(wall, .99)
    cpu_max = cpu[-1] / 1000
    ok = p99 <= P99_LIMIT_US and cpu_max <= MAX_LIMIT_US
    print(f"gate: wall p99 {p99:.1f} us (limit {P99_LIMIT_US:.0f}), cpu max {cpu_max:.1f} us "
          f"(limit {MAX_LIMIT_US:.0f}) -> {'PASS' if ok else 'FAIL'}")
    print(f"wall max {wall[-1]/1000:.1f} us; over 600 us: {sum(1 for x in wall if x > 600_000)} calls, "
          f"over 1 ms: {sum(1 for x in wall if x > 1_000_000)} calls")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
