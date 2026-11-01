from .common import Base, chen_score, fold_or_check, shove, call_or_check


class Nit(Base):
    """Shove-or-fold with roughly the top 10% of hands. Check/call once in a pot."""
    def __init__(self, seed=None, threshold=9.5):
        super().__init__(seed)
        self.threshold = threshold

    def act(self, state):
        if state["street"] != "preflop":
            return call_or_check(state) if state["my_bet"] or state["to_call"] == 0 else fold_or_check(state)
        if chen_score(state["hole_cards"]) >= self.threshold:
            return shove(state)
        return fold_or_check(state)
