from bot import tables as T
from bot.evaluator import CARD_INT
from .common import Base, made_strength, raise_to, call_or_check, fold_or_check


class NaiveEquity(Base):
    """The likely default AI-written bot: raw equity vs random, no position or ICM."""
    def act(self, state):
        live = sum(1 for i, f in enumerate(state["folded"]) if not f and i != state["seat"])
        pot = state["pot"]
        to_call = state["to_call"]
        price = to_call / (pot + to_call) if to_call else 0
        if state["street"] == "preflop":
            cls = T.class_of([CARD_INT[c] for c in state["hole_cards"]])
            eq = T.EQ_RANDOM[cls][max(0, min(6, live - 1))]
            fair = 1.0 / (live + 1)
            if eq > fair * 1.6:
                return raise_to(state, state["current_bet"] + int(pot))
            if eq > max(fair * 1.15, price):
                return call_or_check(state)
            return fold_or_check(state)
        s = made_strength(state)
        eq = (0.3, 0.6, 0.8, 0.92)[s] ** max(1, live)
        if eq > 0.6:
            return raise_to(state, state["current_bet"] + int(pot * 0.75))
        if eq >= price and to_call > 0:
            return call_or_check(state)
        return fold_or_check(state)
