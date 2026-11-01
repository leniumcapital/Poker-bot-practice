"""Preflop strategy. Choose a regime by effective stack, then apply ranges.

Short (< SHORT_MAX_BB):  pure push/fold, never min-raise and fold.
Medium (<= MEDIUM_MAX_BB): small opens, reshoves over opens.
Deep: open ranges by position, 3-bet for value plus a few bluffs, fold to 4-bets.
"""
from . import config as C
from . import icm
from . import tables as T
from .actions import legalize, FOLD, CHECK, CALL, RAISE, SHOVE


class Facing:
    """What happened before me this hand, preflop."""
    __slots__ = ("raises", "limpers", "callers", "raiser", "raise_to", "allin", "allin_seats", "i_raised")


def read_action(gs):
    f = Facing()
    raises = limpers = callers = 0
    raiser = -1
    raise_to = 0
    allin = False
    allin_seats = 0
    i_raised = False
    for street, seat, kind, amount, is_allin in gs.history:
        if street != 0:
            break
        if kind == "raise":
            raises += 1
            raiser = seat
            raise_to = amount
            allin = is_allin
            callers = 0
            if is_allin:
                allin_seats += 1
            if seat == gs.seat:
                i_raised = True
        elif kind == "call":
            if raises == 0:
                limpers += 1
            else:
                callers += 1
            if is_allin:
                allin_seats += 1
    f.raises, f.limpers, f.callers, f.raiser, f.raise_to = raises, limpers, callers, raiser, raise_to
    f.allin, f.allin_seats, f.i_raised = allin, allin_seats, i_raised
    return f


def decide(gs, ctx, opp, rng, t0=None):
    cls = T.class_of(gs.hole)
    pct = T.PCT[cls]
    f = read_action(gs)
    if f.raises == 0:
        return _unopened(gs, ctx, f, pct, opp)
    # A raise costing much of my stack is a commit-or-fold decision whatever my depth.
    if (f.allin or ctx.eff_bb < C.SHORT_MAX_BB or gs.to_call >= C.COMMIT_FRACTION * gs.stack):
        return _commit_or_fold(gs, ctx, f, cls, pct, opp, fold_equity=not f.allin)
    if ctx.eff_bb <= C.MEDIUM_MAX_BB:
        return _medium_vs_raise(gs, ctx, f, cls, pct, opp)
    if f.raises == 1:
        return _deep_vs_raise(gs, ctx, f, cls, pct, opp, rng)
    return _deep_vs_reraise(gs, ctx, f, cls, pct, opp)


# ------------------------------------------------------------- unopened pot ---

def _unopened(gs, ctx, f, pct, opp):
    behind = gs.behind
    eff = ctx.eff_bb
    if eff < C.SHORT_MAX_BB or (eff <= C.MED_SHOVE_MAX_BB and eff <= C.CHART_MAX_BB):
        return _push_fold(gs, ctx, f, pct, opp)
    if gs.to_call == 0:
        # Big blind with a free option: isolate limpers with strong hands, else check.
        if f.limpers and pct <= C.BB_ISO_PCT:
            return _raise_bb(gs, 3.0 + C.LIMPER_EXTRA_BB * f.limpers)
        return legalize(CHECK, gs)
    b = behind if behind in C.OPEN_PCT else 7
    limit = C.OPEN_PCT[b] * opp.blinds_fold_factor(gs)
    if f.limpers:
        limit *= C.ISO_FACTOR         # fewer hands raise well into dead limp money
    if eff <= C.MEDIUM_MAX_BB:
        limit *= C.MED_OPEN_FACTOR
        size = C.MED_OPEN_SIZE_BB
    else:
        size = C.OPEN_SIZE_BB[b]
    if pct <= limit:
        return _raise_bb(gs, size + C.LIMPER_EXTRA_BB * f.limpers)
    return legalize(FOLD, gs)


def _push_fold(gs, ctx, f, pct, opp):
    """Shove or fold from the chart. Works from any seat, including a free BB option."""
    behind = gs.behind
    if gs.to_call == 0:
        # BB with a free look: shove only with real strength, otherwise see the flop free.
        if pct <= T.push_pct(1, ctx.eff_bb) * C.BB_SHOVE_VS_LIMP_FACTOR:
            return legalize(SHOVE, gs)
        return legalize(CHECK, gs)
    limit = T.push_pct(behind if behind > 0 else 1, ctx.eff_bb) * opp.blinds_fold_factor(gs)
    limit *= icm.shove_factor(gs, ctx, opp)
    if f.limpers:
        limit *= C.LIMP_SHOVE_FACTOR  # a limper is one more possible caller
    return legalize(SHOVE if pct <= limit else FOLD, gs)


def _raise_bb(gs, size_bb):
    """Raise to size_bb, or shove when that raise would be most of my stack anyway."""
    target = int(size_bb * gs.bb)
    if target >= C.SHOVE_INSTEAD_FRACTION * (gs.stack + gs.my_bet):
        return legalize(SHOVE, gs)
    return legalize(RAISE, gs, target)


# ------------------------------------------------------------ facing a raise ---

def estimate_raiser_range(gs, f, opp):
    """Top-X% range we credit the last raiser with."""
    seat = f.raiser
    behind = _behind_of(gs, seat)
    raiser_bb = (gs.stacks[seat] + gs.bets[seat]) / gs.bb if seat >= 0 else 20.0
    if f.allin:
        if raiser_bb <= C.CHART_MAX_BB:
            base = T.push_pct(max(behind, 1), raiser_bb)
        else:
            base = C.DEFAULT_SHOVE_PCT_DEEP
        r = opp.shove_range(seat, base)
    else:
        if f.raises == 1:
            base = C.OPEN_PCT.get(max(1, min(7, behind)), 0.15)
        elif f.raises == 2:
            base = C.DEFAULT_3BET_PCT
        else:
            base = C.DEFAULT_4BET_PCT
        r = opp.raise_range(seat, base, f.raises)
    if r < C.MIN_RANGE_PCT:
        return C.MIN_RANGE_PCT
    return r if r < C.MAX_RANGE_PCT else C.MAX_RANGE_PCT


def _behind_of(gs, seat):
    try:
        return gs.n_dealt - 1 - gs.order.index(seat)
    except ValueError:
        return 2


def _commit_or_fold(gs, ctx, f, cls, pct, opp, fold_equity):
    """Compare equity vs the raiser's range to the price of getting all-in."""
    r = estimate_raiser_range(gs, f, opp)
    eq = T.eq_vs_top(cls, r)
    if f.allin_seats > 1 or f.callers:
        eq *= C.MULTIWAY_EQUITY_FACTOR ** max(f.allin_seats - 1, f.callers)
    seat = f.raiser
    raiser_total = gs.stacks[seat] + gs.bets[seat]
    my_total = gs.stack + gs.my_bet
    cover = my_total if my_total < raiser_total else raiser_total
    cost = cover - gs.my_bet
    if cost <= 0:
        cost = gs.to_call
    # Pot if we get it in: everything now, plus my cost, plus what the raiser still
    # adds up to the covered amount, minus anything of theirs above what I can match.
    overbet = gs.bets[seat] - cover
    raiser_add = cover - gs.bets[seat]
    pot_final = gs.pot + cost + (raiser_add if raiser_add > 0 else 0) - (overbet if overbet > 0 else 0)
    need = cost / pot_final if pot_final > 0 else 1.0
    need += C.CALL_ALLIN_MARGIN + C.BEHIND_RISK_MARGIN * gs.behind
    need += icm.risk_premium(gs, ctx, seat, cost, pot_final)
    if fold_equity:
        # The raiser sometimes folds to a shove, more so when they are in late position.
        eq += C.RESHOVE_FE_BONUS
    if eq >= need:
        return legalize(SHOVE if fold_equity else CALL, gs)
    return legalize(FOLD, gs)


def _medium_vs_raise(gs, ctx, f, cls, pct, opp):
    """12-25 BB: reshove or fold. Flatting here burns too much of the stack."""
    behind_raiser = _behind_of(gs, f.raiser)
    limit = estimate_raiser_range(gs, f, opp) * 0.5
    if behind_raiser <= 3:            # opener in late position: wide range, reshove wider
        limit *= C.RESHOVE_LATE_FACTOR
    limit *= opp.call_tighten_factor(gs)
    if pct <= limit:
        return legalize(SHOVE, gs)
    if gs.to_call == 0:
        return legalize(CHECK, gs)
    return _defend_by_odds(gs, ctx, f, cls, opp)


def _deep_vs_raise(gs, ctx, f, cls, pct, opp, rng):
    raise_bb = f.raise_to / gs.bb
    in_position = gs.behind >= 2 or gs.n_dealt == 2 and gs.seat == gs.button
    if pct <= C.THREEBET_VALUE_PCT:
        return _three_bet(gs, f, in_position)
    # Bluff 3-bets only heads-up, in position, against a raiser who can fold.
    if (C.THREEBET_BLUFF_LOW <= pct <= C.THREEBET_BLUFF_HIGH and in_position and f.callers == 0
            and rng.random() < C.THREEBET_BLUFF_FREQ * opp.call_tighten_factor(gs)):
        return _three_bet(gs, f, in_position)
    flat = C.FLAT_PCT_IP if in_position else C.FLAT_PCT_OOP
    deep_enough = ctx.eff_bb >= C.IMPLIED_MIN_SPR * raise_bb
    if pct <= flat and (raise_bb <= C.MAX_FLAT_PRICE_BB or deep_enough):
        return legalize(CALL, gs)
    return _defend_by_odds(gs, ctx, f, cls, opp)


def _three_bet(gs, f, in_position):
    mult = C.THREEBET_SIZE_IP if in_position else C.THREEBET_SIZE_OOP
    target = int(f.raise_to * mult + gs.bb * f.callers)
    if target >= C.SHOVE_INSTEAD_FRACTION * (gs.stack + gs.my_bet):
        return legalize(SHOVE, gs)
    return legalize(RAISE, gs, target)


def _deep_vs_reraise(gs, ctx, f, cls, pct, opp):
    """Fold to 3-bets and 4-bets except premiums; never bluff here."""
    if pct <= C.FOURBET_PCT:
        return legalize(SHOVE, gs)
    if f.raises >= 3 and pct <= C.PREMIUM_PCT:
        return legalize(CALL, gs)
    if (f.raises == 2 and pct <= C.FLAT_3BET_PCT
            and gs.to_call <= C.MAX_FLAT_3BET_STACK_FRAC * gs.stack):
        return legalize(CALL, gs)
    return legalize(FOLD, gs)


def _defend_by_odds(gs, ctx, f, cls, opp):
    """Call a cheap raise when equity vs the raiser's range beats the price (BB defense)."""
    r = estimate_raiser_range(gs, f, opp)
    eq = T.eq_vs_top(cls, r) * C.BB_DEFEND_REALIZE
    if f.callers:
        eq *= C.MULTIWAY_EQUITY_FACTOR ** f.callers
    if eq >= ctx.pot_odds + C.BEHIND_RISK_MARGIN * gs.behind:
        return legalize(CALL, gs)
    return legalize(FOLD, gs)
