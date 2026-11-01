"""Check the table evaluator against an independent brute-force reference."""
import random
import unittest
from itertools import combinations

from bot import evaluator as E


def ref_five(cards):
    """Slow textbook 5-card ranking: returns a comparable tuple. Standard hold'em order."""
    ranks = sorted((c // E.NS for c in cards), reverse=True)
    suits = {c % E.NS for c in cards}
    flush = len(suits) == 1
    counts = {r: ranks.count(r) for r in set(ranks)}
    groups = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    shape = [g[1] for g in groups]
    order = [g[0] for g in groups]
    straight = -1
    distinct = sorted(set(ranks))
    if len(distinct) == 5:
        if distinct[4] - distinct[0] == 4:
            straight = distinct[4]
        elif distinct == [0, 1, 2, 3, E.NR - 1]:
            straight = 3
    if straight >= 0 and flush:
        return (8, straight)
    if shape == [4, 1]:
        return (7, *order)
    if shape == [3, 2]:
        return (6, *order)
    if flush:
        return (5, *ranks)
    if straight >= 0:
        return (4, straight)
    if shape == [3, 1, 1]:
        return (3, *order)
    if shape == [2, 2, 1]:
        return (2, *order)
    if shape == [2, 1, 1, 1]:
        return (1, *order)
    return (0, *ranks)


def ref_best(cards):
    return max(ref_five(list(c)) for c in combinations(cards, 5))


class TestEvaluator(unittest.TestCase):
    def test_matches_bruteforce_ordering_7_cards(self):
        rng = random.Random(7)
        seen = {}
        for _ in range(4000):
            hand = rng.sample(E.DECK, 7)
            v = E.eval_cards(hand)
            r = ref_best(hand)
            self.assertEqual(seen.setdefault(v, r), r, "same value must mean the same hand")
            self.assertEqual(E.category(v), r[0])
        # Values must order hands the same way the reference does.
        items = sorted(seen.items())
        for (_, a), (_, b) in zip(items, items[1:]):
            self.assertLess(a, b)

    def test_5_and_6_cards(self):
        rng = random.Random(8)
        for n in (5, 6):
            pairs = [rng.sample(E.DECK, n) for _ in range(1500)]
            vals = sorted((E.eval_cards(h), ref_best(h)) for h in pairs)
            for (va, ra), (vb, rb) in zip(vals, vals[1:]):
                self.assertEqual(va < vb, ra < rb)

    def test_specific_hands(self):
        c = lambda s: [E.CARD_INT[x] for x in s.split()]
        wheel = E.eval_cards(c("Ah 2d 3c 4s 5h 9d Kc"))
        six_high = E.eval_cards(c("2h 3d 4c 5s 6h 9d Kc"))
        self.assertEqual(E.category(wheel), E.STRAIGHT)
        self.assertGreater(six_high, wheel)
        self.assertEqual(E.category(E.eval_cards(c("Ah Kh Qh Jh Th 2c 3c"))), E.STRAIGHT_FLUSH)
        self.assertEqual(E.category(E.eval_cards(c("Ah Ad Ac As 2h 2c 3c"))), E.QUADS)
        self.assertEqual(E.category(E.eval_cards(c("Ah Ad Ac Kh Kc 2c 3d"))), E.FULL_HOUSE)
        # Two trips make a full house, three pairs keep the best kicker.
        self.assertEqual(E.category(E.eval_cards(c("Ah Ad Ac Kh Kc Kd 3d"))), E.FULL_HOUSE)
        self.assertGreater(E.eval_cards(c("Ah Ad Kh Kd Qc Qd Jc")), E.eval_cards(c("Ah Ad Kh Kd Tc Td 9c")))


if __name__ == "__main__":
    unittest.main()
