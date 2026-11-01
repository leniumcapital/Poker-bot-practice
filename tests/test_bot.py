"""Safety and strategy edge cases for the bot through its public entry point."""
import random
import unittest

from baselines import REGISTRY
from bot import config, evaluator as E, postflop, tables as T
from bot.actions import legalize, fallback, SHOVE, RAISE, CALL, FOLD, CHECK
from bot.agent import Agent
from bot.state import parse_state, GameState
from sim.engine import validate
from sim.tournament import play_table

PAY = [100, 50, 25, 10, 5, 0, 0, 0]


def state(**kw):
    """A legal default: 3 players, preflop, seat 0 first to act."""
    s = {
        "hand_number": 1, "seat": 0, "button": 0, "hole_cards": ["Ah", "Ad"], "board": [],
        "street": "preflop", "pot": 30, "to_call": 20, "current_bet": 20, "my_bet": 0,
        "min_raise_to": 40, "max_raise_to": 2000, "can_raise": True, "stack": 2000,
        "stacks": [2000, 1990, 1980], "bets": [0, 10, 20], "folded": [False, False, False],
        "dealt_in": [True, True, True], "small_blind": 10, "big_blind": 20, "ante": 0,
        "history": [(0, 1, "sb", 10, False), (0, 2, "bb", 20, False)],
    }
    s.update(kw)
    return s


def assert_legal(tc, s, a):
    r = validate(a, s["to_call"], s["stack"], s["can_raise"], s["min_raise_to"], s["max_raise_to"])
    tc.assertIsNotNone(r, f"illegal action {a} for {s}")


class TestSafety(unittest.TestCase):
    def test_malformed_states_never_raise(self):
        ag = Agent(seed=1)
        bad = [{}, {"hole_cards": None}, {"hole_cards": ["Zz", "??"], "to_call": 5},
               {"hole_cards": ["Ah"], "to_call": 0}, {"to_call": "lots"}, {"stacks": "x"},
               {"history": [("garbage",)], "hole_cards": ["Ah", "Ad"]},
               state(history=[(0, 1, "teleport", 10, False)]),
               state(history=[(0, 99, "raise", 10, True)]),
               state(stacks=[]), state(button=77), state(seat=44), state(big_blind=0),
               state(street="flop", board=["Ah"]), None, 42, "state", [1, 2]]
        for raw in bad:
            a = ag.act(raw)
            self.assertIn(a["action"], ("fold", "check", "call", "raise"), raw)

    def test_fallback_is_check_when_free(self):
        self.assertEqual(fallback({"to_call": 0})["action"], "check")
        self.assertEqual(fallback({"to_call": 10})["action"], "fold")
        self.assertEqual(fallback(None)["action"], "fold")

    def test_internal_exception_falls_back(self):
        ag = Agent(seed=1)
        ag.opp = None     # any attribute access now blows up inside the try block
        self.assertEqual(ag.act(state(to_call=0))["action"], "check")
        self.assertEqual(ag.act(state())["action"], "fold")
        self.assertEqual(ag.fallbacks, 2)


class TestLegalize(unittest.TestCase):
    def gs(self, **kw):
        g = GameState()
        for k, v in kw.items():
            setattr(g, k, v)
        return g

    def test_raise_below_min_is_bumped(self):
        g = self.gs(to_call=20, current_bet=20, min_raise_to=40, max_raise_to=2000, can_raise=True, stack=2000)
        self.assertEqual(legalize(RAISE, g, 25), {"action": "raise", "amount": 40})

    def test_raise_above_stack_is_all_in(self):
        g = self.gs(to_call=20, current_bet=20, min_raise_to=40, max_raise_to=500, can_raise=True, stack=500)
        self.assertEqual(legalize(RAISE, g, 9999)["amount"], 500)

    def test_raise_when_not_allowed_calls(self):
        g = self.gs(to_call=20, current_bet=20, min_raise_to=40, max_raise_to=2000, can_raise=False, stack=2000)
        self.assertEqual(legalize(RAISE, g, 100)["action"], "call")
        self.assertEqual(legalize(SHOVE, g)["action"], "call")

    def test_shove_when_stack_only_covers_call(self):
        g = self.gs(to_call=50, current_bet=100, my_bet=50, min_raise_to=50 + 50, max_raise_to=100, can_raise=False, stack=50)
        self.assertEqual(legalize(SHOVE, g), {"action": "call", "amount": 50})

    def test_all_in_for_less_than_min_raise(self):
        # Stack 30 behind, 20 to call: only an all-in to 50 is possible, below the full min of 60.
        g = self.gs(to_call=20, current_bet=40, my_bet=20, min_raise_to=50, max_raise_to=50, can_raise=True, stack=30)
        self.assertEqual(legalize(SHOVE, g), {"action": "raise", "amount": 50})

    def test_free_fold_becomes_check_and_paid_check_becomes_fold(self):
        g = self.gs(to_call=0)
        self.assertEqual(legalize(FOLD, g)["action"], "check")
        g = self.gs(to_call=5)
        self.assertEqual(legalize(CHECK, g)["action"], "fold")


class TestAgentActions(unittest.TestCase):
    def test_all_in_short_of_big_blind(self):
        s = state(stack=7, to_call=7, max_raise_to=7, min_raise_to=7, can_raise=False, stacks=[7, 1990, 1980])
        a = Agent(seed=1).act(s)
        assert_legal(self, s, a)

    def test_heads_up_position(self):
        s = state(stacks=[1990, 1980], bets=[10, 20], folded=[False, False], dealt_in=[True, True],
                  my_bet=10, to_call=10, button=0, seat=0, stack=1990, pot=30, max_raise_to=2000,
                  history=[(0, 0, "sb", 10, False), (0, 1, "bb", 20, False)])
        g = parse_state(s)
        self.assertEqual(g.behind, 1)
        assert_legal(self, s, Agent(seed=1).act(s))

    def test_aces_never_fold_preflop_any_stack(self):
        for stack in (10, 40, 100, 300, 600, 2000, 10000):
            s = state(stack=stack, max_raise_to=stack, min_raise_to=min(40, stack), stacks=[stack, 1990, 1980],
                      to_call=min(20, stack), can_raise=stack > 20)
            a = Agent(seed=1).act(s)
            self.assertNotEqual(a["action"], "fold", stack)

    def test_short_stack_never_min_raises(self):
        for hole in (["Ah", "Ad"], ["Ks", "Qs"], ["9h", "9d"], ["As", "7d"]):
            s = state(hole_cards=hole, stack=160, max_raise_to=160, min_raise_to=40, stacks=[160, 1990, 1980])
            a = Agent(seed=1).act(s)
            if a["action"] == "raise":
                self.assertEqual(a["amount"], 160, "short stacks shove, they don't min-raise")

    def test_trash_folds_to_a_shove(self):
        s = state(hole_cards=["7h", "2d"], bets=[0, 2000, 20], to_call=2000, current_bet=2000,
                  pot=2030, min_raise_to=2000, max_raise_to=2000, can_raise=False,
                  stacks=[2000, 0, 1980], history=[(0, 1, "sb", 10, False), (0, 2, "bb", 20, False), (0, 1, "raise", 2000, True)])
        self.assertEqual(Agent(seed=1).act(s)["action"], "fold")

    def test_unknown_history_actions_are_ignored(self):
        s = state(history=[(0, 1, "sb", 10, False), (0, 2, "bb", 20, False), (0, 2, "wiggle", 0, False)])
        assert_legal(self, s, Agent(seed=1).act(s))


class TestClassify(unittest.TestCase):
    def read(self, hole, board, street=None):
        g = GameState()
        g.hole = [E.CARD_INT[c] for c in hole.split()]
        g.board = [E.CARD_INT[c] for c in board.split()]
        g.street = street or {3: 1, 4: 2, 5: 3}[len(g.board)]
        return postflop.classify(g)

    def test_tiers(self):
        self.assertEqual(self.read("As Ad", "Kh 7d 2c").tier, 3)     # overpair
        self.assertEqual(self.read("Ks Qd", "Kh 7d 2c").tier, 3)     # top pair good kicker
        self.assertEqual(self.read("Ks 4d", "Kh 7d 2c").tier, 2)     # top pair weak kicker
        self.assertEqual(self.read("7s 4d", "Kh 7d 2c").tier, 2)     # second pair
        self.assertEqual(self.read("2s 4d", "Kh 7d 2c").tier, 1)     # bottom pair
        self.assertEqual(self.read("As Qd", "Kh 7d 2c").tier, 0)     # air
        self.assertEqual(self.read("7s 7c", "Kh 7d 2c").tier, 5)     # set
        self.assertEqual(self.read("Ks 7c", "Kh 7d 2c").tier, 4)     # top two pair
        self.assertEqual(self.read("Ah 2h", "Kh 7h 3h").tier, 5)     # nut flush
        self.assertEqual(self.read("As Qd", "3h 3d 3c").tier, 0)     # trips on board only

    def test_playing_the_board_is_not_strong(self):
        self.assertLessEqual(self.read("2s 2c", "5h 6d 7c 8s 9h").tier, 1)
        self.assertLessEqual(self.read("As Kd", "Th Jh Qh Kh Ah").tier, 1)

    def test_draw_outs(self):
        fd = self.read("Ah 5h", "Kh 7h 2c")
        self.assertTrue(fd.flush_draw)
        self.assertAlmostEqual(fd.draw_eq, 9 * 0.04, places=3)
        oe = self.read("5s 4d", "7h 6c 2c")
        self.assertAlmostEqual(oe.outs, 8, places=3)
        self.assertAlmostEqual(self.read("9s 8d", "7h 6c 2c").outs, 8 + 3, places=3)  # plus overcards
        gut = self.read("9s 5d", "7h 6c 2c")
        self.assertAlmostEqual(gut.outs, 4, places=3)
        self.assertEqual(self.read("As Kd", "Th Jh Qh 2c 3c").draw_eq, 0)  # river: no outs

    def test_board_draws_dont_count_as_mine(self):
        # Four to a straight on the board: the out isn't improved by my low cards.
        self.assertEqual(self.read("2s 3d", "9h Tc Jd Qs", street=2).outs, 0)


class TestIntegration(unittest.TestCase):
    def test_full_tables_no_faults_all_baselines(self):
        rng = random.Random(3)
        names = list(REGISTRY)
        for t in range(40):
            hero = rng.randrange(8)
            agents = [Agent(seed=rng.getrandbits(32), payouts=PAY) if s == hero or rng.random() < .2
                      else REGISTRY[rng.choice(names)](seed=rng.getrandbits(32)) for s in range(8)]
            r = play_table(agents, PAY, t, time_limit_ns=None)
            self.assertEqual(sum(r["stacks"]), 16000)
            for st in r["stats"]:
                self.assertEqual(st.exceptions, 0)
                self.assertEqual(st.illegal, 0)
            for a in agents:
                # act() hides its own exceptions, so check the counter too.
                self.assertEqual(getattr(a, "fallbacks", 0), 0, getattr(a, "last_error", None))

    def test_table_data_loaded(self):
        self.assertEqual(T.SOURCE, "file")
        self.assertEqual(len(T.ORDER), 169)
        self.assertLess(T.PCT[T.class_of([E.CARD_INT["Ah"], E.CARD_INT["Ad"]])], 0.01)


if __name__ == "__main__":
    unittest.main()
