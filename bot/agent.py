"""Entry point. When the organizers publish their interface, only this file should change."""
import gc
import random
from time import perf_counter

from . import config, context, icm, opponents, preflop, postflop
from .actions import fallback
from .state import parse_state


class Agent:
    """One instance per table. Opponent stats reset automatically on a new table."""

    def __init__(self, seed=None, payouts=None):
        self.rng = random.Random(seed)
        self.opp = opponents.OpponentModel()
        self.last_hand = -1
        self.fallbacks = 0            # strategy exceptions caught here; must stay 0 in sims
        self.last_error = None
        self.payouts = list(payouts) if payouts else list(config.PAYOUTS)
        self.icm_table = icm.build_table(self.payouts)   # cached; not in act()

    def act(self, raw):
        """Must return a legal action and never raise."""
        t0 = perf_counter()
        try:
            gs = parse_state(raw)
            gs.payouts = self.payouts
            gs.icm_table = self.icm_table
            gs.t0 = t0
            if gs.hand_no < self.last_hand:
                self.opp.reset()      # hand numbers went backwards: a new table
            self.last_hand = gs.hand_no
            self.opp.observe(gs)
            ctx = context.build(gs)
            if gs.street == 0:
                return preflop.decide(gs, ctx, self.opp, self.rng, t0)
            return postflop.decide(gs, ctx, self.opp, self.rng, t0)
        except Exception as e:
            self.fallbacks += 1
            self.last_error = e
            return fallback(raw)

    def on_hand_end(self, result):
        """Optional hook: full hand history, to see the action after we folded."""
        try:
            self.opp.on_hand_end(result)
        except Exception as e:
            self.fallbacks += 1
            self.last_error = e


icm.build_table(config.PAYOUTS)

# Everything is loaded by now. Freezing moves tables out of the GC's reach, so a
# collection during act() doesn't have to walk them (that was the max-time spike).
gc.collect()
gc.freeze()
gc.set_threshold(*config.GC_THRESHOLDS)
