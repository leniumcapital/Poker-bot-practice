"""Lookup-table hand evaluator, configured by config.VARIANT.

Cards are ints: rank_index * n_suits + suit_index. Higher value = better hand.
value = (category position in hand_order) << 20 | kickers (4 bits each).

How the lookup works: each card adds to one running integer that holds a rank
multiset (base-(n_suits+1) digits) in the low bits and per-suit counters in the
high bits. Non-flush hands are one dict lookup on the multiset; a flush needs
one extra pass to build its rank mask.
"""
from itertools import combinations
from . import config

V = config.VARIANT
RANKS = V["ranks"]
SUITS = V["suits"]
NR = len(RANKS)
NS = len(SUITS)
HOLE_CARDS = V["hole_cards"]
STREET_CARDS = V["street_cards"]
BOARD_CARDS = sum(STREET_CARDS)
MUST_USE = V["must_use_hole"]
HAND_ORDER = V["hand_order"]
DECK = list(range(NR * NS))

CARD_STR = [RANKS[c // NS] + SUITS[c % NS] for c in DECK]
CARD_INT = {s: i for i, s in enumerate(CARD_STR)}
RANK_OF = [c // NS for c in DECK]
SUIT_OF = [c % NS for c in DECK]
BIT_OF = [1 << (c // NS) for c in DECK]

CAT_SHIFT = 20
# Canonical category ids, independent of the variant's ordering.
HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)
_CANON = ["high_card", "pair", "two_pair", "trips", "straight", "flush",
          "full_house", "quads", "straight_flush"]
_POS = {name: i for i, name in enumerate(HAND_ORDER)}
# value >> CAT_SHIFT -> canonical category id
CAT_OF_POS = [_CANON.index(name) for name in HAND_ORDER]

_BASE = NS + 1
_SUIT_SHIFT = 48                     # suit counters live above the rank digits
_FLUSH_INIT = sum(3 << (_SUIT_SHIFT + 4 * s) for s in range(NS))
_FLUSH_MASK = sum(8 << (_SUIT_SHIFT + 4 * s) for s in range(NS))
CARD_KEY = [_BASE ** (c // NS) + (1 << (_SUIT_SHIFT + 4 * (c % NS))) for c in DECK]
_RANK_KEY_MASK = (1 << _SUIT_SHIFT) - 1

# All straights as (mask, high rank), best first. Ace plays low in the lowest one.
STRAIGHTS = [((0b11111 << low), low + 4) for low in range(NR - 5, -1, -1)]
STRAIGHTS.append((((1 << (NR - 1)) | 0b1111), 3))


def _value(cat, tiebreak):
    v = _POS[cat] << CAT_SHIFT
    shift = 16
    for r in tiebreak:
        v |= r << shift
        shift -= 4
    return v


def _straight_high(mask):
    for m, high in STRAIGHTS:
        if mask & m == m:
            return high
    return -1


def _nonflush_value(counts):
    """Best five-card hand from a rank multiset, ignoring suits."""
    ranks = [r for r in range(NR - 1, -1, -1) if counts[r]]
    quads = [r for r in ranks if counts[r] >= 4]
    trips = [r for r in ranks if counts[r] == 3]
    pairs = [r for r in ranks if counts[r] == 2]
    best = -1
    if len(ranks) >= 5:
        best = max(best, _value("high_card", ranks[:5]))
    if pairs or trips or quads:
        p = max(pairs + trips + quads)
        best = max(best, _value("pair", [p] + [r for r in ranks if r != p][:3]))
    if len(pairs) >= 2:
        a, b = pairs[0], pairs[1]
        best = max(best, _value("two_pair", [a, b] + [r for r in ranks if r != a and r != b][:1]))
    if trips:
        t = trips[0]
        best = max(best, _value("trips", [t] + [r for r in ranks if r != t][:2]))
    mask = sum(1 << r for r in ranks)
    high = _straight_high(mask)
    if high >= 0:
        best = max(best, _value("straight", [high]))
    if trips and (len(trips) >= 2 or pairs):
        t = trips[0]
        p = max([r for r in trips + pairs if r != t])
        best = max(best, _value("full_house", [t, p]))
    if quads:
        q = quads[0]
        best = max(best, _value("quads", [q] + [r for r in ranks if r != q][:1]))
    return best


def _build_tables():
    max_cards = 5 if MUST_USE else max(7, HOLE_CARDS + BOARD_CARDS)
    table = {}
    counts = [0] * NR

    def walk(r, left, key):
        if left == 0:
            if key not in table:
                table[key] = _nonflush_value(counts)
            return
        if r == NR:
            return
        for c in range(0, min(left, NS) + 1):
            counts[r] = c
            walk(r + 1, left - c, key + c * _BASE ** r)
        counts[r] = 0

    for size in range(5, max_cards + 1):
        walk(0, size, 0)

    flush = [0] * (1 << NR)
    for mask in range(1 << NR):
        ranks = [r for r in range(NR - 1, -1, -1) if mask >> r & 1]
        if len(ranks) < 5:
            continue
        high = _straight_high(mask)
        flush[mask] = (_value("straight_flush", [high]) if high >= 0
                       else _value("flush", ranks[:5]))
    return table, flush


NONFLUSH, FLUSH_TABLE = _build_tables()


def eval_cards(cards):
    """Best five-card value from 5+ cards (any cards may play)."""
    key = _FLUSH_INIT
    for c in cards:
        key += CARD_KEY[c]
    if key & _FLUSH_MASK:
        return _eval_flush(cards, key)
    return NONFLUSH[key & _RANK_KEY_MASK]


def _eval_flush(cards, key):
    # A suit counter hit 5+. Take the better of flush and non-flush: in short deck
    # or with 8+ cards the non-flush hand can win.
    bits = (key & _FLUSH_MASK) >> _SUIT_SHIFT
    suit = 0
    while not bits >> (4 * suit) & 8:
        suit += 1
    mask = 0
    for c in cards:
        if c % NS == suit:
            mask |= BIT_OF[c]
    v = FLUSH_TABLE[mask]
    other = NONFLUSH.get(key & _RANK_KEY_MASK, -1)
    return v if v > other else other


_COMBO_CACHE = {}


def _omaha_combos(n_hole, n_board):
    k = (n_hole, n_board)
    if k not in _COMBO_CACHE:
        board_need = 5 - MUST_USE
        _COMBO_CACHE[k] = (list(combinations(range(n_hole), MUST_USE)),
                           list(combinations(range(n_board), board_need)))
    return _COMBO_CACHE[k]


def _eval_must_use(hole, board):
    """Omaha-style: exactly MUST_USE hole cards plus the rest from the board."""
    hs, bs = _omaha_combos(len(hole), len(board))
    best = -1
    for h in hs:
        hk = _FLUSH_INIT
        for i in h:
            hk += CARD_KEY[hole[i]]
        for b in bs:
            key = hk
            for i in b:
                key += CARD_KEY[board[i]]
            if key & _FLUSH_MASK:
                v = _eval_flush([hole[i] for i in h] + [board[i] for i in b], key)
            else:
                v = NONFLUSH[key & _RANK_KEY_MASK]
            if v > best:
                best = v
    return best


if MUST_USE:
    evaluate = _eval_must_use
else:
    def evaluate(hole, board):
        """Best hand for hole + board. Needs at least 5 cards available."""
        return eval_cards(list(hole) + list(board))


def category(value):
    """Canonical category id (PAIR, FLUSH, ...) of an evaluator value."""
    return CAT_OF_POS[value >> CAT_SHIFT]
