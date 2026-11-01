"""Engine rules: blinds, min-raise, short all-ins, side pots, ties, conservation."""
import random
import unittest

from bot import evaluator as E
from baselines.random_legal import RandomLegal
from sim.engine import play_hand, SeatStats, validate
from sim.tournament import play_table, award_busted


class Script:
    """Plays a fixed list of actions, then checks or folds. Records the states it saw."""
    def __init__(self, actions=()):
        self.actions = list(actions)
        self.states = []

    def act(self, state):
        self.states.append(state)
        if self.actions:
            return self.actions.pop(0)
        return {"action": "check"} if state["to_call"] == 0 else {"action": "fold"}


def cards(s):
    return [E.CARD_INT[x] for x in s.split()]


def run(agents, stacks, button, deck, sb=10, bb=20):
    stats = [SeatStats() for _ in agents]
    r = play_hand(agents, stats, stacks, button, sb, bb, 0, deck, 1)
    return r, stats


# Seat 0 Aces, seat 1 Kings, seat 2 Queens; low dry board.
DECK3 = cards("Ah Ad Kh Kd Qh Qd 2c 3c 7d 9s 4h")


class TestEngine(unittest.TestCase):
    def test_all_fold_to_bb(self):
        ag = [Script(), Script(), Script()]
        st = [1000, 1000, 1000]
        run(ag, st, 0, DECK3)           # button 0, SB seat 1, BB seat 2, seat 0 first
        self.assertEqual(st, [1000, 990, 1010])

    def test_heads_up_button_is_sb_and_acts_first_preflop(self):
        a, b = Script([{"action": "call"}]), Script()
        st = [1000, 1000]
        deck = cards("Ah Ad Kh Kd 2c 3c 7d 9s 4h")
        run([a, b], st, 0, deck)
        self.assertEqual(a.states[0]["bets"], [10, 20])
        self.assertEqual(a.states[0]["to_call"], 10)
        self.assertEqual(len(b.states) >= 1, True)
        # Postflop the big blind (non-button) acts first.
        flop = [s for s in b.states + a.states if s["street"] == "flop"]
        self.assertEqual(flop[0]["seat"], 1)

    def test_bb_option(self):
        a = Script([{"action": "call"}])
        sb = Script([{"action": "call"}])
        bb = Script([{"action": "raise", "amount": 60}, {"action": "check"}])
        st = [1000, 1000, 1000]
        run([a, sb, bb], st, 0, DECK3)
        self.assertEqual(bb.states[0]["to_call"], 0)
        self.assertTrue(bb.states[0]["can_raise"])
        self.assertEqual(bb.states[0]["min_raise_to"], 40)

    def test_short_blind_all_in(self):
        # SB has 5 chips, BB has 12. Others still owe the full 20.
        a = Script([{"action": "call"}])
        st = [1000, 5, 12]
        r, _ = run([a, Script(), Script()], st, 0, DECK3)
        self.assertEqual(a.states[0]["to_call"], 20)
        self.assertEqual(sum(st), 1017)
        # Aces take everything they contested; only 20 of seat 0 was at risk.
        self.assertEqual(st, [1000 - 20 + 20 + 12 + 5, 0, 0])

    def test_side_pots(self):
        ag = [Script([{"action": "raise", "amount": 1000}]),
              Script([{"action": "call"}]), Script([{"action": "call"}])]
        # Seat 0 (AA) has 100, seat 1 (KK) 300, seat 2 (QQ) 1000.
        ag[0].actions = [{"action": "raise", "amount": 100}]
        st = [100, 300, 1000]
        # Seat 1 raises all-in, seat 2 calls: main 300 to seat 0, side 400 to seat 1, 700 back to seat 2.
        ag[1].actions = [{"action": "raise", "amount": 300}]
        ag[2].actions = [{"action": "call"}]
        run(ag, st, 0, DECK3)
        self.assertEqual(st, [300, 400, 700])

    def test_split_pot_odd_chip(self):
        # Both play the board straight; 41 chips cannot split evenly.
        deck = cards("2h 2d 2c 2s 5h 6h 7d 8s 9c")
        a, b = Script([{"action": "call"}]), Script()
        st = [1000, 1000]
        # Sb 11, bb 20: pot 40 after call. Force odd with an uneven all-in below.
        stats = [SeatStats(), SeatStats()]
        play_hand([a, b], stats, st, 0, 10, 20, 0, deck, 1)
        self.assertEqual(st, [1000, 1000])
        st3 = [1000, 1000, 1000]
        # Three-way chop of a 40-chip pot gives one extra chip to the first left of the button.
        x, y, z = Script(), Script([{"action": "call"}]), Script()
        deck3 = cards("2h 2d 2c 2s 3h 3d 5h 6h 7d 8s 9c")
        stats = [SeatStats() for _ in range(3)]
        play_hand([x, y, z], stats, st3, 0, 10, 20, 0, deck3, 1)
        self.assertEqual(sum(st3), 3000)
        self.assertEqual(st3, [1000, 1000, 1000])

    def test_short_all_in_does_not_reopen(self):
        # A raises to 100; B all-in to 130 (a 30 raise, under the 80 minimum). C calls.
        a = Script([{"action": "raise", "amount": 100}, {"action": "call"}])
        b = Script([{"action": "raise", "amount": 130}])
        c = Script([{"action": "call"}, {"action": "check"}])
        st = [1000, 130 + 0, 1000]
        run([a, b, c], st, 0, DECK3)
        second = a.states[1]
        self.assertEqual(second["to_call"], 30)
        self.assertFalse(second["can_raise"], "a short all-in must not reopen betting")

    def test_min_raise_tracks_last_full_raise(self):
        a = Script([{"action": "raise", "amount": 100}])
        b = Script()
        run([a, b, Script()], [1000, 1000, 1000], 0, DECK3)
        self.assertEqual(b.states[0]["min_raise_to"], 180)  # 100 + the 80 raise

    def test_illegal_actions_count_and_fold(self):
        a = Script([{"action": "raise", "amount": 25}])     # below the min raise
        st = [1000, 1000, 1000]
        _, stats = run([a, Script(), Script()], st, 0, DECK3)
        self.assertEqual(stats[0].illegal, 1)
        self.assertEqual(st[0], 1000)

    def test_exception_counts_and_checks_when_free(self):
        class Boom:
            def act(self, state):
                raise RuntimeError("boom")
        st = [1000, 1000]
        stats = [SeatStats(), SeatStats()]
        deck = cards("Ah Ad Kh Kd 2c 3c 7d 9s 4h")
        play_hand([Boom(), Boom()], stats, st, 0, 10, 20, 0, deck, 1)
        self.assertEqual(stats[0].exceptions, 1)    # SB folds to the bet
        self.assertEqual(st, [990, 1010])

    def test_validate(self):
        self.assertIsNone(validate({"action": "check"}, 10, 100, True, 20, 100))
        self.assertIsNone(validate({"action": "dance"}, 0, 100, True, 20, 100))
        self.assertIsNone(validate("fold", 0, 100, True, 20, 100))
        self.assertIsNone(validate({"action": "raise", "amount": 10.5}, 0, 100, True, 20, 100))
        self.assertEqual(validate({"action": "raise", "amount": 100}, 0, 100, True, 20, 100), ("raise", 100))

    def test_chip_conservation_random_tables(self):
        for seed in range(30):
            agents = [RandomLegal(seed=seed * 10 + i) for i in range(8)]
            r = play_table(agents, [100, 50, 25, 10, 5, 0, 0, 0], seed, time_limit_ns=None)
            self.assertEqual(sum(r["stacks"]), 16000)
            self.assertAlmostEqual(sum(r["points"]), 190, places=6)

    def test_bust_order_bigger_stack_finishes_higher_ties_split(self):
        pay = [100, 50, 25, 10, 5, 0, 0, 0]
        points = [0.0] * 8
        places = [0.0] * 8
        start = [500, 300, 300, 100, 0, 0, 0, 0]
        award_busted([1, 2, 3], start, 1, pay, points, places)
        self.assertEqual(points[1], (50 + 25) / 2)
        self.assertEqual(points[2], (50 + 25) / 2)
        self.assertEqual(points[3], 10)
        self.assertEqual(places[3], 3)

    def test_same_seed_is_reproducible(self):
        def once():
            ag = [RandomLegal(seed=i) for i in range(8)]
            return play_table(ag, [8, 7, 6, 5, 4, 3, 2, 1], 99, time_limit_ns=None)["stacks"]
        self.assertEqual(once(), once())


if __name__ == "__main__":
    unittest.main()
