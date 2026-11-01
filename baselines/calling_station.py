from .common import Base, call_or_check, fold_or_check


class CallingStation(Base):
    """Calls almost everything, never raises."""
    def act(self, state):
        if state["to_call"] > 0 and self.rng.random() < 0.05:
            return fold_or_check(state)
        return call_or_check(state)
