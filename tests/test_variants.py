"""Variant rules run in subprocesses: the variant is fixed when the evaluator is imported."""
import os
import subprocess
import sys
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(variant, code):
    env = dict(os.environ, POKERBOT_VARIANT=variant)
    r = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


PRE = """
from bot import evaluator as E
c = lambda s: [E.CARD_INT[x] for x in s.split()]
"""


class TestVariants(unittest.TestCase):
    def check(self, variant, code):
        rc, out = run(variant, PRE + textwrap.dedent(code))
        self.assertEqual(rc, 0, out)

    def test_shortdeck_flush_beats_full_house(self):
        self.check("shortdeck", """
            assert len(E.DECK) == 36
            flush = E.eval_cards(c("Ah Th 8h 7h 6h"))
            boat = E.eval_cards(c("Ah Ad Ac Kh Kd"))
            assert flush > boat
        """)

    def test_shortdeck_low_straight(self):
        self.check("shortdeck", """
            low = E.eval_cards(c("Ah 6d 7c 8s 9h"))
            assert E.category(low) == E.STRAIGHT
            assert E.eval_cards(c("6h 7d 8c 9s Th")) > low
        """)

    def test_omaha_must_use_exactly_two(self):
        self.check("omaha", """
            # Four spades on board plus one spade in hand is no flush: two must come from the hand.
            board = c("As Ks Qs Js 2d")
            no_flush = E.evaluate(c("Ts 3d 4c 5h"), board)
            assert E.category(no_flush) != E.FLUSH and E.category(no_flush) != E.STRAIGHT_FLUSH
            # Both hole spades must play, so the 3s plays too: an ace-high flush, not a royal.
            flush = E.evaluate(c("Ts 3s 4c 5h"), board)
            assert E.category(flush) == E.FLUSH
            # Pocket aces on a KKK board: two aces plus three kings, never four of a kind.
            v = E.evaluate(c("Ah Ad 3c 4c"), c("Kh Kd Kc 7s 2d"))
            assert E.category(v) == E.FULL_HOUSE
        """)

    def test_three_hole_cards_use_any_five_of_eight(self):
        self.check("holdem3", """
            v = E.evaluate(c("Ah Kh Qh"), c("Jh Th 2c 3d 4s"))
            assert E.category(v) == E.STRAIGHT_FLUSH
        """)

    def test_every_variant_plays_clean_tables(self):
        for variant in ("shortdeck", "omaha", "holdem3"):
            self.check(variant, """
                from bot.agent import Agent
                from baselines import REGISTRY
                from sim.tournament import play_table
                import random
                rng = random.Random(1)
                names = list(REGISTRY)
                for t in range(10):
                    agents = [Agent(seed=s) if s < 3 else REGISTRY[rng.choice(names)](seed=s) for s in range(8)]
                    r = play_table(agents, [100, 50, 25, 10, 5, 0, 0, 0], t, time_limit_ns=None)
                    assert sum(r["stacks"]) == 16000
                    assert all(st.exceptions == 0 and st.illegal == 0 for st in r["stats"])
            """)

    def test_bot_plays_with_no_data_file(self):
        # Right after a variant switch, before precompute has finished.
        self.check("shortdeck", """
            from bot import tables as T
            data = T._fallback()
            assert len(data["pct"]) == T.N_CLASSES
            T.PCT[:] = data["pct"]; T.EQ_TOP[:] = data["eq_top"]; T.EQ_RANDOM[:] = data["eq_random"]
            T.PUSH[:] = data["push"]; T.CALL[:] = data["call"]
            from bot.agent import Agent
            from baselines import REGISTRY
            from sim.tournament import play_table
            agents = [Agent(seed=s) if s < 4 else REGISTRY["simple_tag"](seed=s) for s in range(8)]
            r = play_table(agents, [100, 50, 25, 10, 5, 0, 0, 0], 3, time_limit_ns=None)
            assert all(st.exceptions == 0 and st.illegal == 0 for st in r["stats"])
        """)


if __name__ == "__main__":
    unittest.main()
