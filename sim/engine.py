"""One hand of No-Limit Hold'em (or configured variant) for 2-8 players.

Rules enforced: button/heads-up blinds, short blinds, min-raise, short all-ins that
do not reopen betting, side pots, split pots (odd chip left of the button).
"""
from time import perf_counter_ns, thread_time_ns

from bot import evaluator as E

STREET_NAMES = ["preflop", "flop", "turn", "river", "street4", "street5", "street6"]
_HOLE = E.HOLE_CARDS
_CARD_STR = E.CARD_STR
_EVAL = E.evaluate


class SeatStats:
    """Rule-enforcement counters for one seat."""
    __slots__ = ("decisions", "timeouts", "jitter", "exceptions", "illegal",
                 "total_ns", "max_ns", "max_cpu_ns")

    def __init__(self):
        self.decisions = self.timeouts = self.jitter = self.exceptions = self.illegal = 0
        self.total_ns = self.max_ns = self.max_cpu_ns = 0


def validate(action, to_call, stack, can_raise, min_to, max_to):
    """Return (kind, raise_to) if legal, else None."""
    if isinstance(action, dict):
        kind = action.get("action")
        amount = action.get("amount", 0)
    elif isinstance(action, (tuple, list)) and action:
        kind = action[0]
        amount = action[1] if len(action) > 1 else 0
    else:
        return None
    if kind == "fold":
        return ("fold", 0)
    if kind == "check":
        return ("check", 0) if to_call == 0 else None
    if kind == "call":
        return ("call", 0) if to_call > 0 else None
    if kind == "raise":
        if not can_raise or not isinstance(amount, int) or isinstance(amount, bool):
            return None
        if amount < min_to or amount > max_to:
            return None
        return ("raise", amount)
    return None


def pay_pots(contrib, folded, stacks, order_from_button, board, holes):
    """Distribute all chips by layered side pots. Mutates stacks. Returns shown {seat: value}."""
    live = [s for s in order_from_button if not folded[s]]
    if len(live) == 1:
        stacks[live[0]] += sum(contrib)
        return {}
    values = {s: _EVAL(holes[s], board) for s in live}
    levels = sorted(set(c for c in contrib if c > 0))
    prev = 0
    carry = 0
    n = len(contrib)
    for level in levels:
        layer = carry
        carry = 0
        eligible = []
        for s in range(n):
            if contrib[s] > prev:
                layer += min(contrib[s], level) - prev
                if contrib[s] >= level and not folded[s]:
                    eligible.append(s)
        prev = level
        if not eligible:
            carry = layer            # only folded money at this level: roll it up
            continue
        best = max(values[s] for s in eligible)
        winners = [s for s in order_from_button if s in eligible and values[s] == best]
        share, odd = divmod(layer, len(winners))
        for i, s in enumerate(winners):
            stacks[s] += share + (1 if i < odd else 0)
    if carry:                        # folded money above every live player
        best_seat = max(live, key=lambda s: values[s])
        stacks[best_seat] += carry
    return values


def play_hand(agents, stats, stacks, button, sb, bb, ante, deck, hand_no, time_limit_ns=None,
              wall_clock=False):
    """Play one hand. `stacks` is mutated. `deck` holds n_seats*hole + board cards.

    Timeouts: by default a decision is penalized when its CPU time exceeds the limit.
    Wall-only overruns are OS preemption (a no-op section shows them too) and are counted
    as `jitter` without a penalty, which keeps identical seeds reproducible.
    wall_clock=True penalizes on wall time instead.
    """
    n = len(stacks)
    dealt_in = [s > 0 for s in stacks]
    order = [(button + i) % n for i in range(1, n + 1) if dealt_in[(button + i) % n]]
    n_dealt = len(order)
    # `order` runs SB, BB, ..., button. Postflop action starts at the front of this list.
    if n_dealt == 2:
        sb_seat, bb_seat = order[1], order[0]      # heads-up: button is the small blind
    else:
        sb_seat, bb_seat = order[0], order[1]

    holes = [deck[s * _HOLE:(s + 1) * _HOLE] for s in range(n)]
    hole_strs = [[_CARD_STR[c] for c in h] for h in holes]
    board_all = deck[n * _HOLE:]
    board_strs_all = [_CARD_STR[c] for c in board_all]

    contrib = [0] * n                # chips from finished streets
    bets = [0] * n                   # chips on the current street
    folded = [not d for d in dealt_in]
    history = []

    if ante:
        for s in order:
            a = min(ante, stacks[s])
            stacks[s] -= a
            contrib[s] += a
            history.append((0, s, "ante", a, stacks[s] == 0))
    a = min(sb, stacks[sb_seat])
    stacks[sb_seat] -= a
    bets[sb_seat] = a
    history.append((0, sb_seat, "sb", a, stacks[sb_seat] == 0))
    a = min(bb, stacks[bb_seat])
    stacks[bb_seat] -= a
    bets[bb_seat] = a
    history.append((0, bb_seat, "bb", a, stacks[bb_seat] == 0))

    board_len = 0
    street_cards = E.STREET_CARDS
    n_streets = len(street_cards) + 1
    idx_of_seat = {s: i for i, s in enumerate(order)}

    for street in range(n_streets):
        if street > 0:
            board_len += street_cards[street - 1]
        board_strs = board_strs_all[:board_len]
        live_count = sum(1 for s in order if not folded[s])
        if live_count <= 1:
            break
        current_bet = bb if street == 0 else 0
        raise_inc = bb
        acted = [False] * n          # acted since the last full raise (cannot re-raise)
        if street == 0:
            start = idx_of_seat[bb_seat] + 1
        else:
            start = 0
        i = start % n_dealt
        idle = 0                     # consecutive seats with nothing to do
        while idle < n_dealt:
            s = order[i]
            i = (i + 1) % n_dealt
            if folded[s] or stacks[s] == 0:
                idle += 1
                continue
            if acted[s] and bets[s] >= current_bet:
                idle += 1
                continue
            live_with_chips = 0
            live_count = 0
            for o in order:
                if not folded[o]:
                    live_count += 1
                    if o != s and stacks[o] > 0:
                        live_with_chips += 1
            if live_count <= 1:
                break
            to_call = current_bet - bets[s]
            if to_call <= 0 and live_with_chips == 0:
                idle += 1            # everyone else is all-in: nothing to decide
                continue
            idle = 0
            stack = stacks[s]
            capped_call = to_call if to_call < stack else stack
            max_to = stack + bets[s]
            min_to = current_bet + raise_inc
            if min_to > max_to:
                min_to = max_to      # all-in for less than a full raise
            can_raise = (not acted[s]) and stack > to_call and live_with_chips > 0
            state = {
                "hand_number": hand_no, "seat": s, "button": button,
                "hole_cards": hole_strs[s], "board": board_strs,
                "street": STREET_NAMES[street],
                "pot": sum(contrib) + sum(bets), "to_call": capped_call,
                "current_bet": current_bet, "my_bet": bets[s],
                "min_raise_to": min_to, "max_raise_to": max_to, "can_raise": can_raise,
                "stack": stack, "stacks": list(stacks), "bets": list(bets),
                "folded": list(folded), "dealt_in": dealt_in,
                "small_blind": sb, "big_blind": bb, "ante": ante, "history": history,
            }
            st = stats[s]
            result = None
            bad = False
            c0 = thread_time_ns()
            t0 = perf_counter_ns()
            try:
                action = agents[s].act(state)
            except Exception:
                action = None
                bad = True
            dt = perf_counter_ns() - t0
            dc = thread_time_ns() - c0
            st.decisions += 1
            st.total_ns += dt
            if dt > st.max_ns:
                st.max_ns = dt
            if dc > st.max_cpu_ns:
                st.max_cpu_ns = dc
            over = False
            if time_limit_ns is not None:
                if dt > time_limit_ns and dc <= time_limit_ns:
                    st.jitter += 1
                over = dc > time_limit_ns or (wall_clock and dt > time_limit_ns)
            if bad:
                st.exceptions += 1
            elif over:
                st.timeouts += 1
            else:
                result = validate(action, capped_call, stack, can_raise, min_to, max_to)
                if result is None:
                    st.illegal += 1
            if result is None:       # penalty: fold, or check when checking is free
                result = ("check", 0) if to_call <= 0 else ("fold", 0)
            kind, amount = result
            if kind == "fold":
                folded[s] = True
                history.append((street, s, "fold", 0, False))
            elif kind == "check":
                acted[s] = True
                history.append((street, s, "check", 0, False))
            elif kind == "call":
                stacks[s] -= capped_call
                bets[s] += capped_call
                acted[s] = True
                history.append((street, s, "call", bets[s], stacks[s] == 0))
            else:                    # raise to `amount`
                added = amount - bets[s]
                stacks[s] -= added
                bets[s] = amount
                inc = amount - current_bet
                if inc >= raise_inc:
                    # A full raise reopens betting for everyone.
                    raise_inc = inc
                    acted = [False] * n
                # A short all-in leaves `acted` alone: earlier actors may call or fold only.
                current_bet = amount
                acted[s] = True
                history.append((street, s, "raise", amount, stacks[s] == 0))
        for s in range(n):
            contrib[s] += bets[s]
            bets[s] = 0

    board_len = sum(street_cards)
    board = board_all[:board_len]
    values = pay_pots(contrib, folded, stacks, order, board, holes)
    return {"history": history, "values": values, "holes": holes, "board": board,
            "contrib": contrib, "folded": folded}
