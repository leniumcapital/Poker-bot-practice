"""One 8-seat sit-and-go: blinds, eliminations, 200-hand cap, finishing points."""
import random

from bot import evaluator as E
from bot.icm import icm_equities
from . import settings as S
from .engine import play_hand, SeatStats

_DECK = E.DECK
_DEAL = S.SEATS * E.HOLE_CARDS + E.BOARD_CARDS


def blinds_for(hand_no, schedule=None, per_level=None):
    schedule = schedule or S.BLIND_SCHEDULE
    per_level = per_level or S.HANDS_PER_LEVEL
    level = min((hand_no - 1) // per_level, len(schedule) - 1)
    return schedule[level]


def award_busted(busted, start_stacks, next_place, payouts, points, places):
    """Bust order: bigger start-of-hand stack finishes higher; equal stacks split the places."""
    busted = sorted(busted, key=lambda s: -start_stacks[s])
    i = 0
    place = next_place
    while i < len(busted):
        j = i
        while j < len(busted) and start_stacks[busted[j]] == start_stacks[busted[i]]:
            j += 1
        tied = busted[i:j]
        share = sum(payouts[place + k] for k in range(len(tied))) / len(tied)
        for s in tied:
            points[s] = share
            places[s] = place + (len(tied) - 1) / 2
        place += len(tied)
        i = j


def play_table(agents, payouts, seed, time_limit_ns=S.TIME_LIMIT_NS, schedule=None,
               max_hands=S.MAX_HANDS, starting_stack=S.STARTING_STACK, wall_clock=False):
    """Returns dict with points, places, stats and hands played."""
    n = len(agents)
    rng = random.Random(seed)
    stacks = [starting_stack] * n
    stats = [SeatStats() for _ in range(n)]
    points = [0.0] * n
    places = [0.0] * n
    button = rng.randrange(n)
    hand_no = 0
    hooks = [a for a in agents if hasattr(a, "on_hand_end")]
    alive = n
    while hand_no < max_hands and alive > 1:
        hand_no += 1
        sb, bb = blinds_for(hand_no, schedule)
        deck = rng.sample(_DECK, _DEAL)
        start = list(stacks)
        result = play_hand(agents, stats, stacks, button, sb, bb, S.ANTE, deck, hand_no, time_limit_ns, wall_clock)
        for h in hooks:
            h.on_hand_end(result)
        busted = [s for s in range(n) if start[s] > 0 and stacks[s] == 0]
        if busted:
            alive -= len(busted)
            award_busted(busted, start, alive, payouts, points, places)
        button = (button + 1) % n
        while stacks[button] == 0 and alive > 0:
            button = (button + 1) % n
    if alive == 1:
        winner = next(s for s in range(n) if stacks[s] > 0)
        points[winner] = payouts[0]
        places[winner] = 0
    else:
        # Cap reached: survivors split the remaining points by ICM.
        eq = icm_equities(stacks, payouts[:alive])
        for s in range(n):
            if stacks[s] > 0:
                points[s] = eq[s]
        order = sorted((s for s in range(n) if stacks[s] > 0), key=lambda s: -stacks[s])
        for rank, s in enumerate(order):
            places[s] = rank
    return {"points": points, "places": places, "stats": stats, "hands": hand_no,
            "capped": alive > 1, "stacks": stacks}
