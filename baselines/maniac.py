from .common import Base, raise_to, shove, call_or_check, fold_or_check


class Maniac(Base):
    """Raises and shoves far too often, rarely folds."""
    def act(self, state):
        x = self.rng.random()
        if state["street"] == "preflop":
            if x < 0.18:
                return shove(state)
            if x < 0.65:
                return raise_to(state, state["big_blind"] * self.rng.randint(3, 6) + state["current_bet"])
        else:
            if x < 0.10:
                return shove(state)
            if x < 0.60:
                return raise_to(state, state["current_bet"] + int(state["pot"] * self.rng.uniform(0.6, 1.2)))
        if state["to_call"] > 0 and self.rng.random() < 0.12:
            return fold_or_check(state)
        return call_or_check(state)
