import unittest

from bot import config as C, icm
from bot.agent import Agent
from bot.icm import icm_equities
from bot.opponents import OpponentModel
from bot.state import parse_state
from sim.engine import validate
from tests.test_bot import state

TOP = [100, 50, 25, 10, 5, 0, 0, 0]
FLAT = [8, 7, 6, 5, 4, 3, 2, 1]


class TestICM(unittest.TestCase):
    def test_equal_stacks_split_evenly(self):
        for pay in (TOP, FLAT):
            ev = icm_equities([1000] * 8, pay)
            for v in ev:
                self.assertAlmostEqual(v, sum(pay) / 8, places=6)

    def test_known_three_player_value(self):
        # Worked by hand. P1 first .5; second .3*(50/70) + .2*(50/80) = .3393; third .1607.
        # EV = .5*50 + .3393*30 + .1607*20 = 38.393. Same method for the others.
        ev = icm_equities([50, 30, 20], [50, 30, 20])
        self.assertAlmostEqual(ev[0], 38.3929, places=3)
        self.assertAlmostEqual(ev[1], 32.75, places=3)
        self.assertAlmostEqual(ev[2], 28.8571, places=3)

    def test_conserves_points_and_is_monotonic(self):
        ev = icm_equities([5000, 3000, 1500, 500], TOP[:4])
        self.assertAlmostEqual(sum(ev), sum(TOP[:4]), places=6)
        self.assertEqual(ev, sorted(ev, reverse=True))

    def test_winner_takes_first_when_heads_up_dominant(self):
        ev = icm_equities([9999, 1], [100, 50])
        self.assertGreater(ev[0], 99.9)

    def test_even_money_needs_more_than_half_with_ladder(self):
        # A 4-way even-stack all-in with a paid ladder must require more than 50%.
        table = icm.build_table(TOP)
        self.assertGreater(icm.table_premium(table, 4, 1.0, 1.0), 0)
        # Heads-up: a chip is worth the same throughout, close to no premium... in points it is linear.
        self.assertAlmostEqual(icm.table_premium(table, 2, 1.0, 1.0), 0, places=6)

    def test_premium_larger_when_covered_than_when_covering(self):
        table = icm.build_table(TOP)
        covered = icm.table_premium(table, 6, 1.0, 2.0)
        covering = icm.table_premium(table, 6, 1.0, 0.5)
        self.assertGreater(covered, covering - 0.01)


class TestOpponents(unittest.TestCase):
    def model(self, kinds, hands=30):
        """Feed `hands` hands where seat 0 does `kinds` preflop."""
        m = OpponentModel()
        for h in range(1, hands + 1):
            hist = [(0, 1, "sb", 10, False), (0, 2, "bb", 20, False), (0, 0, *kinds, False)]
            s = parse_state(state(hand_number=h, seat=2, history=hist))
            m.observe(s)
        return m

    def test_shrinkage_starts_at_prior(self):
        m = OpponentModel()
        self.assertAlmostEqual(m.vpip_rate(0), C.PRIOR_VPIP)
        self.assertEqual(m.player_type(0), C.UNKNOWN)

    def test_types(self):
        self.assertEqual(self.model(("fold", 0)).player_type(0), C.NIT)
        self.assertEqual(self.model(("call", 20)).player_type(0), C.STATION)
        self.assertEqual(self.model(("raise", 60)).player_type(0), C.MANIAC)

    def test_history_only_counted_once(self):
        m = OpponentModel()
        hist = [(0, 1, "sb", 10, False), (0, 2, "bb", 20, False), (0, 0, "call", 20, False)]
        for _ in range(5):
            m.observe(parse_state(state(hand_number=1, seat=2, history=hist)))
        self.assertEqual(m.vpip[0], 1)
        self.assertEqual(m.hands[0], 1)

    def test_shove_range_learns(self):
        m = OpponentModel()
        for h in range(1, 41):
            hist = [(0, 1, "sb", 10, False), (0, 2, "bb", 20, False), (0, 0, "raise", 2000, True)]
            m.observe(parse_state(state(hand_number=h, seat=2, history=hist)))
        self.assertGreater(m.shove_range(0, 0.1), 0.6)
        self.assertLess(OpponentModel().shove_range(0, 0.1), 0.11)

    def test_new_table_resets_the_model(self):
        a = Agent(seed=1)
        hist = [(0, 1, "sb", 10, False), (0, 2, "bb", 20, False), (0, 0, "call", 20, False)]
        a.act(state(hand_number=50, seat=2, history=hist))
        self.assertEqual(a.opp.vpip[0], 1)
        a.act(state(hand_number=1, seat=2, history=hist[:2]))
        self.assertEqual(a.opp.vpip[0], 0)

    def test_garbage_seats_do_not_crash(self):
        a = Agent(seed=1)
        s = state(history=[(0, 1, "sb", 10, False), (0, 200, "raise", 60, False)])
        r = a.act(s)
        self.assertIsNotNone(validate(r, s["to_call"], s["stack"], s["can_raise"], s["min_raise_to"], s["max_raise_to"]))


class TestCalls(unittest.TestCase):
    def facing_shove(self, pay, hole=("Ah", "Td")):
        hist = [(0, 1, "sb", 100, False), (0, 2, "bb", 200, False), (0, 3, "raise", 4000, True)]
        return state(hole_cards=list(hole), seat=0, button=0, stack=4000, my_bet=0,
                     stacks=[4000, 3900, 3800, 0], bets=[0, 100, 200, 4000], folded=[False] * 4,
                     dealt_in=[True] * 4, to_call=4000, current_bet=4000, min_raise_to=4000,
                     max_raise_to=4000, can_raise=False, pot=4300, small_blind=100, big_blind=200,
                     history=hist, hand_number=100)

    def premium(self, pay):
        s = parse_state(self.facing_shove(pay))
        s.payouts = pay
        return icm._exact_premium(s, 3, 4000, 8300)

    def test_calling_for_stacks_with_a_ladder_needs_a_premium(self):
        self.assertGreater(self.premium(TOP), 0.0)

    def test_busting_earns_the_next_place_not_zero(self):
        self.assertEqual(icm._my_ev([0, 500, 500], 0, FLAT), FLAT[2])

    def test_top_heavy_rewards_gambling_more_than_flat(self):
        # Flat points pay mostly for outlasting; top-heavy pays mostly for winning.
        self.assertGreater(self.premium(FLAT), self.premium(TOP))


if __name__ == "__main__":
    unittest.main()
