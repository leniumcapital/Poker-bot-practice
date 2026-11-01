from .common import Base, chen_score, made_strength, raise_to, shove, call_or_check, fold_or_check


class SimpleTag(Base):
    """Standard tight-aggressive: position-based opens, value bets, c-bets, pot odds."""
    def act(self, state):
        return self._preflop(state) if state["street"] == "preflop" else self._postflop(state)

    def _preflop(self, state):
        bb = state["big_blind"]
        score = chen_score(state["hole_cards"])
        stack_bb = (state["stack"] + state["my_bet"]) / bb
        unraised = state["current_bet"] <= bb
        # Late position by distance from the button.
        n = len(state["stacks"])
        dist = (state["button"] - state["seat"]) % n
        need = 6.5 if dist <= 1 else (8 if dist <= 3 else 9)
        if stack_bb < 10:
            if score >= (need - 1.5 if unraised else 9):
                return shove(state)
            return fold_or_check(state)
        if unraised:
            if score >= need:
                return raise_to(state, 3 * bb)
            return fold_or_check(state)
        if score >= 12:
            return raise_to(state, state["current_bet"] * 3)
        if score >= 9.5 and state["to_call"] <= 0.12 * state["stack"]:
            return call_or_check(state)
        return fold_or_check(state)

    def _postflop(self, state):
        strength = made_strength(state)
        pot = state["pot"]
        to_call = state["to_call"]
        if to_call == 0:
            if strength >= 1:
                return raise_to(state, int(pot * 0.65))
            if self.rng.random() < 0.3:
                return raise_to(state, int(pot * 0.5))
            return {"action": "check"}
        if strength >= 3:
            return raise_to(state, state["current_bet"] * 3)
        if strength == 2:
            return call_or_check(state)
        if strength == 1 and to_call <= 0.5 * pot:
            return call_or_check(state)
        return fold_or_check(state)
