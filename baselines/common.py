"""Helpers shared by the baseline bots. Deliberately simple: this is the field, not us."""
import random

from bot.evaluator import CARD_INT, RANK_OF, SUIT_OF, NR, evaluate, category, PAIR, TWO_PAIR, TRIPS


class Base:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def act(self, state):
        raise NotImplementedError


def fold_or_check(state):
    return {"action": "check"} if state["to_call"] <= 0 else {"action": "fold"}


def call_or_check(state):
    return {"action": "call"} if state["to_call"] > 0 else {"action": "check"}


def raise_to(state, amount):
    """Raise clamped into the legal window, or just call when raising isn't allowed."""
    if not state["can_raise"]:
        return call_or_check(state)
    amount = int(max(state["min_raise_to"], min(state["max_raise_to"], amount)))
    return {"action": "raise", "amount": amount}


def shove(state):
    return raise_to(state, state["max_raise_to"])


def chen_score(hole_strs):
    """Chen-style hand score, roughly -1 to 20. Uses only the best two hole cards' ranks."""
    ranks = sorted((RANK_OF[CARD_INT[c]] for c in hole_strs), reverse=True)[:2]
    hi, lo = ranks[0], ranks[1]
    suits = [SUIT_OF[CARD_INT[c]] for c in hole_strs]
    suited = len(set(suits)) < len(suits)
    top = NR - 1
    base = {top: 10, top - 1: 8, top - 2: 7, top - 3: 6}.get(hi, (hi + 2) / 2)
    if hi == lo:
        return max(5, base * 2)
    score = base + (2 if suited else 0)
    gap = hi - lo - 1
    score -= {0: 0, 1: 1, 2: 2, 3: 4}.get(gap, 5)
    if gap <= 1 and hi < top - 2:
        score += 1
    return score


def made_strength(state):
    """0 nothing, 1 pair, 2 two pair, 3 trips or better. Needs a flop."""
    board = [CARD_INT[c] for c in state["board"]]
    hole = [CARD_INT[c] for c in state["hole_cards"]]
    if len(board) < 3:
        return 0
    if len(hole) + len(board) < 5:
        return 0
    cat = category(evaluate(hole, board))
    if cat == PAIR:
        return 1
    if cat == TWO_PAIR:
        return 2
    if cat >= TRIPS:
        return 3
    return 0
