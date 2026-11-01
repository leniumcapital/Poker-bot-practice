"""Malmuth-Harville ICM and the risk premium it implies.

Chips aren't points: doubling up rarely doubles my points, but busting loses them
all. The premium is how much equity above chip-EV break-even a call needs.
"""
from time import perf_counter

from . import config as C


def icm_equities(stacks, payouts):
    """Expected payout per player: P(next place) is proportional to chips."""
    n = len(stacks)
    ev = [0.0] * n
    alive = [i for i in range(n) if stacks[i] > 0]
    k = len(alive)
    if k == 0:
        return ev
    chips = [stacks[i] for i in alive]
    paid = len(payouts)
    while paid > 0 and payouts[paid - 1] == 0:
        paid -= 1
    size = 1 << k
    prob = [0.0] * size
    prob[0] = 1.0
    used = [0] * size            # chips already placed for each subset
    places = [0] * size          # how many players already placed
    total = sum(chips)
    for mask in range(size):
        p = prob[mask]
        if p == 0.0:
            continue
        place = places[mask]
        if place >= paid or place >= k:
            continue
        pay = payouts[place]
        rem = total - used[mask]
        for j in range(k):
            bit = 1 << j
            if mask & bit:
                continue
            nxt = mask | bit
            q = p * chips[j] / rem
            prob[nxt] += q
            ev[alive[j]] += q * pay
            used[nxt] = used[mask] + chips[j]
            places[nxt] = place + 1
    return ev


def _my_ev(stacks, me, payouts):
    """My expected points. A busted me earns the place right after all survivors."""
    if stacks[me] <= 0:
        alive = sum(1 for s in stacks if s > 0)
        return payouts[alive] if alive < len(payouts) else 0.0
    return icm_equities(stacks, payouts)[me]


def _required_equity(stacks_fold, stacks_win, stacks_lose, me, payouts):
    """Equity at which calling and folding have the same expected points."""
    ev_f = _my_ev(stacks_fold, me, payouts)
    ev_w = _my_ev(stacks_win, me, payouts)
    ev_l = _my_ev(stacks_lose, me, payouts)
    span = ev_w - ev_l
    if span <= 1e-9:
        return 1.0
    return (ev_f - ev_l) / span


# ------------------------------------------------- precomputed premium table ---
_TABLES = {}


def _scenario_premium(n, my_mult, opp_ratio, payouts):
    """Even-money all-in, equal stacks elsewhere: required equity minus the chip price of 0.5."""
    me = my_mult
    opp = my_mult * opp_ratio
    others = n - 2
    rest = max(0.05, (n - me - opp) / others) if others > 0 else 0.0
    base = [me, opp] + [rest] * others
    cover = min(me, opp)
    win = list(base)
    win[0] += cover
    win[1] -= cover
    lose = list(base)
    lose[0] -= cover
    lose[1] += cover
    return _required_equity(base, win, lose, 0, payouts) - 0.5


def build_table(payouts):
    """premium[n][i_my][i_opp]. Runs once per payout list, never in act()."""
    key = tuple(payouts)
    if key in _TABLES:
        return _TABLES[key]
    table = {}
    for n in range(2, len(payouts) + 1):
        grid = []
        for my in C.ICM_GRID_MY_STACK:
            grid.append([_scenario_premium(n, my, ratio, payouts) for ratio in C.ICM_GRID_OPP_RATIO])
        table[n] = grid
    _TABLES[key] = table
    return table


def _nearest(grid, x):
    best = 0
    gap = abs(grid[0] - x)
    for i in range(1, len(grid)):
        d = abs(grid[i] - x)
        if d < gap:
            gap = d
            best = i
    return best


def table_premium(table, n, my_vs_avg, opp_ratio):
    grid = table.get(n)
    if grid is None:
        return 0.0
    return grid[_nearest(C.ICM_GRID_MY_STACK, my_vs_avg)][_nearest(C.ICM_GRID_OPP_RATIO, opp_ratio)]


# ------------------------------------------------------------------ hot path ---

def risk_premium(gs, ctx, opp_seat, cost, pot_if_called):
    """Extra equity to demand on a call of `cost` that makes the pot `pot_if_called`."""
    if not gs.payouts:
        return 0.0
    n = ctx.n_alive
    stack = gs.stack
    if cost <= 0 or stack <= 0:
        return 0.0
    if not 0 <= opp_seat < len(gs.stacks):
        return 0.0
    if n <= C.ICM_EXACT_MAX_PLAYERS and perf_counter() - gs.t0 < C.TIME_BUDGET_S:
        p = _exact_premium(gs, opp_seat, cost, pot_if_called)
    else:
        opp_total = gs.stacks[opp_seat] + gs.bets[opp_seat]
        ratio = opp_total / ctx.stack_total if ctx.stack_total > 0 else 1.0
        p = table_premium(gs.icm_table, n, ctx.stack_vs_avg, ratio)
    return _shape(p, ctx)


def _exact_premium(gs, opp_seat, cost, pot_if_called):
    seat = gs.seat
    fold = list(gs.stacks)
    pot = gs.pot
    opp_add = pot_if_called - pot - cost        # what the opponent still puts in
    if opp_add < 0:
        opp_add = 0
    fold[opp_seat] += pot                       # I fold: the pot goes to them
    win = list(gs.stacks)
    win[seat] += pot_if_called - cost
    win[opp_seat] -= opp_add
    lose = list(gs.stacks)
    lose[seat] -= cost
    lose[opp_seat] += pot_if_called - opp_add
    if win[opp_seat] < 0:
        win[opp_seat] = 0
    need = _required_equity(fold, win, lose, seat, gs.payouts)
    return need - cost / pot_if_called


def _shape(p, ctx):
    """Scale by knob and by proximity to the cap, where ICM is the literal final payout."""
    if ctx.hands_to_cap < C.ICM_CAP_WINDOW:
        p *= 1 + C.ICM_CAP_BOOST * (1 - ctx.hands_to_cap / C.ICM_CAP_WINDOW)
    p *= C.ICM_WEIGHT
    if p > C.ICM_MAX_PREMIUM:
        return C.ICM_MAX_PREMIUM
    return p if p > C.ICM_MIN_PREMIUM else C.ICM_MIN_PREMIUM


def shove_factor(gs, ctx, opp):
    """Multiplier on shove ranges from the table premium vs the biggest stack behind me."""
    if not gs.payouts or ctx.n_alive < 3:
        return 1.0
    biggest = 0
    seat = gs.seat
    stacks, bets, folded = gs.stacks, gs.bets, gs.folded
    for i in range(len(stacks)):
        if i != seat and not folded[i] and gs.dealt_in[i]:
            t = stacks[i] + bets[i]
            if t > biggest:
                biggest = t
    ratio = biggest / ctx.stack_total if ctx.stack_total > 0 else 1.0
    p = _shape(table_premium(gs.icm_table, ctx.n_alive, ctx.stack_vs_avg, ratio), ctx)
    factor = 1.0 - C.ICM_SHOVE_TIGHTEN * (p if p > 0 else 0.0)
    if ctx.hands_to_cap <= C.CAP_SURVIVE_HANDS:
        # Close to the cap, if the remaining blinds can't bust me, folding locks in my place.
        blinds_left = ctx.hands_to_cap * (gs.sb + gs.bb) / max(1, ctx.n_alive) * 2
        if blinds_left < ctx.stack_total * 0.8:
            factor *= C.CAP_SURVIVE_FACTOR
    return factor if factor > 0.2 else 0.2
