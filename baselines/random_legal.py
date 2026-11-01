from .common import Base, fold_or_check, call_or_check, raise_to


class RandomLegal(Base):
    """Uniform over fold/call/raise, random raise size."""
    def act(self, state):
        x = self.rng.random()
        if x < 0.34:
            return fold_or_check(state)
        if x < 0.67:
            return call_or_check(state)
        return raise_to(state, self.rng.randint(state["min_raise_to"], max(state["min_raise_to"], state["max_raise_to"])))
