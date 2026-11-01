"""Rule-based postflop play: classify the hand, estimate equity, compare to the price."""
from . import config as C
from . import evaluator as E
from . import icm
from .actions import legalize, FOLD, CHECK, CALL, RAISE, SHOVE
from .evaluator import RANK_OF, SUIT_OF, NR, NS, STRAIGHTS

_RANK = RANK_OF
_SUIT = SUIT_OF
_MUST = E.MUST_USE
_STRAIGHT_MASKS = [m for m, _ in STRAIGHTS]
_HIGH_KICKER = NR - 4                # Jack or better in a standard deck


class Read:
    """The hand and the board, reduced to what the rules need."""
    __slots__ = ("tier", "top_pair_plus", "draw_eq", "outs", "flush_draw", "wet", "dry",
                 "monotone", "paired")


def _popcount(x):
    n = 0
    while x:
        x &= x - 1
        n += 1
    return n


def straight_out_ranks(mask):
    """Bitmask of ranks that would complete a straight."""
    outs = 0
    for w in _STRAIGHT_MASKS:
        miss = w & ~mask
        if miss and miss & (miss - 1) == 0:
            outs |= miss
    return outs


def classify(gs):
    r = Read()
    hole, board = gs.hole, gs.board
    b_ranks = sorted((_RANK[c] for c in board), reverse=True)
    top = b_ranks[0]
    n_board = len(b_ranks)
    b_mask = 0
    for x in b_ranks:
        b_mask |= 1 << x
    distinct = _popcount(b_mask)
    paired = distinct < n_board
    b_suits = [0] * NS
    for c in board:
        b_suits[_SUIT[c]] += 1
    h_suits = [0] * NS
    h_mask = 0
    for c in hole:
        h_suits[_SUIT[c]] += 1
        h_mask |= 1 << _RANK[c]
    max_suit = max(b_suits)
    # Wet: flush draws or straights are live. Dry: rainbow and disconnected.
    b_conn = 0
    for w in _STRAIGHT_MASKS:
        k = _popcount(w & b_mask)
        if k > b_conn:
            b_conn = k
    r.monotone = max_suit >= 3
    r.paired = paired
    r.wet = max_suit >= 2 and n_board <= 4 or max_suit >= 3 or b_conn >= 3
    r.dry = not r.wet
    four_straight = b_conn >= 4

    value = E.evaluate(hole, board)
    cat = E.category(value)
    tier, tpp = _tier(gs, cat, value, b_ranks, top, paired, b_suits, h_suits, max_suit,
                      four_straight, b_conn, h_mask, b_mask, n_board)
    r.tier = tier
    r.top_pair_plus = tpp

    # Draws: only outs that use my hole cards count, and only before the river.
    outs = 0.0
    r.flush_draw = False
    if gs.street < len(E.STREET_CARDS) and n_board < E.BOARD_CARDS:
        all_mask = b_mask | h_mask
        flush_made = cat == E.FLUSH or cat == E.STRAIGHT_FLUSH
        if not flush_made:
            need_hole = _MUST if _MUST else 1
            for s in range(NS):
                if h_suits[s] >= need_hole and h_suits[s] + b_suits[s] == 4 and b_suits[s] >= 2:
                    r.flush_draw = True
                    outs += NR - 4             # cards left in the suit
                    break
        if cat != E.STRAIGHT and cat != E.STRAIGHT_FLUSH:
            s_outs = straight_out_ranks(all_mask) & ~straight_out_ranks(b_mask)
            n_s = _popcount(s_outs)
            if n_s:
                outs += n_s * (NS - (1 if r.flush_draw else 0))
        if tier == 0 and n_board == 3:
            low_hole = min(_RANK[c] for c in hole)
            if low_hole > top:
                outs += C.OVERCARD_OUTS
        if paired:
            outs *= C.PAIRED_BOARD_OUT_DISCOUNT
    r.outs = outs
    r.draw_eq = min(C.MAX_DRAW_EQUITY, outs * C.OUT_EQUITY.get(gs.street, 0.0))
    return r


def _tier(gs, cat, value, b_ranks, top, paired, b_suits, h_suits, max_suit, four_straight,
          b_conn, h_mask, b_mask, n_board):
    """Made-hand strength relative to the board."""
    hole = gs.hole
    flush_possible = max_suit >= 3
    # River: when the five board cards are already my best hand, I can only chop.
    if n_board == 5 and not _MUST and value == E.eval_cards(gs.board):
        return 1, False
    if cat == E.STRAIGHT_FLUSH or cat == E.QUADS:
        # Quads on the board with no help from me is not a monster.
        if cat == E.QUADS and n_board >= 4 and b_ranks.count(b_ranks[1]) == 4 and not (h_mask & (1 << b_ranks[1])):
            return 1, False
        return 5, True
    if cat == E.FULL_HOUSE:
        if h_mask & b_mask == 0 and _popcount(h_mask) > 1:
            return 1, False           # the full house is entirely on the board
        return 5, True
    if cat == E.FLUSH:
        s = b_suits.index(max_suit)
        if h_suits[s] == 0:
            return 1, False           # board flush I don't improve
        best = max(_RANK[c] for c in hole if _SUIT[c] == s)
        missing_above = sum(1 for x in range(best + 1, NR)
                            if not any(_RANK[c] == x and _SUIT[c] == s for c in gs.board))
        if missing_above <= 1:
            return 5, True            # nut or second-nut flush
        return (4 if max_suit == 3 else 3), True
    if cat == E.STRAIGHT:
        if flush_possible or four_straight:
            return 3, True
        return 5 if b_conn <= 3 and not paired else 4, True
    pocket = None
    h_ranks = sorted((_RANK[c] for c in hole), reverse=True)
    for i in range(len(h_ranks) - 1):
        if h_ranks[i] == h_ranks[i + 1]:
            pocket = h_ranks[i]
            break
    if cat == E.TRIPS:
        trip_rank = max(x for x in b_ranks + h_ranks if (b_ranks + h_ranks).count(x) >= 3)
        if not (h_mask & (1 << trip_rank)):
            return 0, False           # trips on board, I hold nothing
        if pocket == trip_rank:
            return (4 if flush_possible or four_straight else 5), True
        kicker = max([x for x in h_ranks if x != trip_rank] or [0])
        return (4 if kicker >= _HIGH_KICKER and not flush_possible else 3), True
    if cat == E.TWO_PAIR:
        hits = [x for x in set(h_ranks) if h_mask & b_mask & (1 << x)]
        if len(hits) >= 2 and not paired:
            return (3 if flush_possible or four_straight else 4), True
        if pocket is not None:
            # Pocket pair on a paired board: behaves like a one-pair hand.
            if pocket > top:
                return 3, True
            return 1, False
        if hits:
            # One card plus a board pair: that card's rank decides.
            x = hits[0]
            if x == top:
                return 3, True
            return 2 if x == b_ranks[1] else 1, False
        return 1, False               # both pairs on the board
    if cat == E.PAIR:
        if pocket is not None:
            if pocket > top:
                return (3 if not four_straight else 2), True
            second = next((x for x in b_ranks if x < top), -1)
            return (2 if pocket > second else 1), False
        hits = [x for x in h_ranks if h_mask & b_mask & (1 << x)]
        if not hits:
            return 0, False           # the pair is on the board
        x = hits[0]
        if x == top:
            kicker = max([y for y in h_ranks if y != x] or [0])
            strong = kicker >= _HIGH_KICKER and not (flush_possible and n_board >= 4)
            return (3 if strong else 2), True
        second = next((y for y in b_ranks if y < top), -1)
        if x == second:
            return (2 if n_board == 3 else 1), False
        return 1, False
    return 0, False


# -------------------------------------------------------------- street facts ---

def _street_facts(gs):
    """Return (preflop raiser seat, raises this street, last aggressor seat this street)."""
    pre_raiser = -1
    raises = 0
    aggressor = -1
    for street, seat, kind, _amount, _allin in gs.history:
        if kind == "raise":
            if street == 0:
                pre_raiser = seat
            if street == gs.street:
                raises += 1
                aggressor = seat
    return pre_raiser, raises, aggressor


def _in_position(gs):
    """Postflop order runs from the seat left of the button; last live seat has position."""
    n = len(gs.stacks)
    i = gs.button
    for _ in range(n):
        if gs.dealt_in[i] and not gs.folded[i] and gs.stacks[i] > 0:
            return i == gs.seat
        i = (i - 1) % n
    return False


def _bet(gs, frac):
    """Bet or raise a share of the pot, shoving when that's most of the stack anyway."""
    tc = gs.to_call
    target = gs.current_bet + int((gs.pot + tc) * frac)
    if target - gs.my_bet >= C.SHOVE_INSTEAD_POST * gs.stack:
        return legalize(SHOVE, gs)
    return legalize(RAISE, gs, target)


# ------------------------------------------------------------------ decision ---

def decide(gs, ctx, opp, rng, t0=None):
    r = classify(gs)
    pre_raiser, raises, aggressor = _street_facts(gs)
    if gs.to_call <= 0:
        return _no_bet(gs, ctx, opp, rng, r, pre_raiser)
    return _facing_bet(gs, ctx, opp, rng, r, raises, aggressor)


def _no_bet(gs, ctx, opp, rng, r, pre_raiser):
    tier = r.tier
    n = ctx.n_live
    heads_up = n == 1
    is_river = gs.street == len(E.STREET_CARDS)
    size = C.VALUE_BET_WET if r.wet else C.VALUE_BET_DRY

    # Low SPR with top pair or better: get the chips in.
    if ctx.spr <= C.STACK_OFF_SPR and r.top_pair_plus and tier >= 2:
        return legalize(SHOVE, gs)

    # Value bets. Multiway needs a stronger hand: someone usually has something.
    min_tier = C.BIG_POT_MIN_TIER_MULTIWAY if not heads_up else 2
    if tier >= min_tier:
        # River: second-best-ish hands bet thin only vs players who call too much.
        if is_river and tier == 2 and not (heads_up and opp.is_station_like(gs)):
            return legalize(CHECK, gs)
        return _bet(gs, size)

    # Weak made hands: thin river value vs stations, otherwise check.
    if is_river and heads_up and tier == C.THIN_VALUE_MIN_TIER - 1 and opp.is_station_like(gs):
        return _bet(gs, C.THIN_VALUE_SIZE)

    # Semi-bluff draws heads-up; never bluff into 2+ opponents.
    bluff_scale = opp.bluff_factor(gs)
    if heads_up and r.draw_eq >= C.SEMIBLUFF_MIN_EQ and rng.random() < C.SEMIBLUFF_FREQ * bluff_scale:
        return _bet(gs, C.SEMIBLUFF_SIZE)

    # Continuation bet with air: heads-up as the preflop raiser.
    if heads_up and pre_raiser == gs.seat and gs.street == 1:
        freq = C.CBET_FREQ if r.dry else C.CBET_WET_FREQ
        if rng.random() < freq * bluff_scale:
            return _bet(gs, C.CBET_SIZE)

    # River bluff: rare, heads-up, as the aggressor, and never vs a station.
    if (is_river and heads_up and tier == 0 and pre_raiser == gs.seat
            and rng.random() < C.RIVER_BLUFF_FREQ * bluff_scale):
        return _bet(gs, C.RIVER_BLUFF_SIZE)
    return legalize(CHECK, gs)


def _facing_bet(gs, ctx, opp, rng, r, raises, aggressor):
    tier = r.tier
    n = ctx.n_live
    price = ctx.pot_odds

    # Monsters raise. Very strong hands raise once, then call the re-raise.
    if tier == 5 or (tier == 4 and raises <= 1):
        if ctx.spr <= C.STACK_OFF_SPR:
            return legalize(SHOVE, gs)
        return _bet(gs, C.RAISE_POT_FRAC)

    # Equity estimate from the tier, discounted for the bet size and for opponents.
    faced = gs.to_call / max(1, gs.pot - gs.to_call)     # bet as a share of the pot before it
    made = C.TIER_EQUITY[tier]
    made -= C.BET_SIZE_PENALTY * min(1.5, faced)
    if raises >= 2:
        made -= C.RAISED_PENALTY
    made += opp.calldown_adjust(aggressor)               # bluffers bet weaker, nits stronger
    if made < 0.02:
        made = 0.02
    if n > 1:
        made = made ** (1 + C.MULTIWAY_EQ_POWER * (n - 1))
    combined = 1 - (1 - made) * (1 - r.draw_eq)

    # Low SPR with top pair or better: committed.
    if ctx.spr <= C.STACK_OFF_SPR and r.top_pair_plus and tier >= 2 and n == 1:
        return legalize(SHOVE if tier >= 3 else CALL, gs)

    implied = C.IMPLIED_ODDS_BONUS if (r.draw_eq > 0 and ctx.spr >= C.IMPLIED_MIN_SPR_POST) else 0.0

    # Big draws sometimes raise as a semi-bluff (fold equity plus outs).
    if (n == 1 and r.draw_eq >= C.SEMIRAISE_MIN_EQ and raises <= 1
            and rng.random() < C.SEMIRAISE_FREQ * opp.bluff_factor(gs)):
        return _bet(gs, C.RAISE_POT_FRAC)

    need = price + C.CALL_MARGIN
    # Big calls risk elimination: ask for more equity by ICM.
    if gs.to_call >= C.ICM_CALL_STACK_FRAC * gs.stack:
        need += icm.risk_premium(gs, ctx, aggressor, gs.to_call, gs.pot + gs.to_call)
    if combined + implied >= need:
        return legalize(CALL, gs)
    return legalize(FOLD, gs)

