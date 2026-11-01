"""Tournament features, computed cheaply once per decision."""
from . import config


class Ctx:
    __slots__ = ("stack_total", "stack_bb", "eff_chips", "eff_bb", "m", "n_live", "n_alive",
                 "position", "hands_to_level", "hands_to_cap", "chip_rank", "stack_vs_avg",
                 "covers", "pot_odds", "spr", "total_chips")


EARLY, MIDDLE, LATE, BLINDS = "early", "middle", "late", "blinds"


def position_category(behind):
    if behind <= 1:
        return BLINDS
    if behind <= 3:
        return LATE
    if behind <= 5:
        return MIDDLE
    return EARLY


def build(gs):
    c = Ctx()
    bb = gs.bb if gs.bb > 0 else 1
    seat = gs.seat
    my_total = gs.stack + gs.my_bet       # chips I can still have in this street's betting
    stacks, bets, folded = gs.stacks, gs.bets, gs.folded
    best_opp = 0
    live = 0
    alive = 0
    rank = 1
    chips = 0
    for i in range(len(stacks)):
        t = stacks[i] + bets[i]
        if t > 0 or gs.dealt_in[i]:
            alive += 1
        chips += t
        if i == seat:
            continue
        if t > my_total:
            rank += 1
        if not folded[i] and gs.dealt_in[i]:
            live += 1
            if t > best_opp:
                best_opp = t
    eff = my_total if my_total < best_opp else best_opp
    c.stack_total = my_total
    c.stack_bb = my_total / bb
    c.eff_chips = eff
    c.eff_bb = eff / bb
    orbit = gs.sb + gs.bb + gs.ante * alive
    c.m = my_total / orbit if orbit > 0 else 99.0
    c.n_live = live
    c.n_alive = alive
    c.position = position_category(gs.behind)
    c.hands_to_level = config.HANDS_PER_LEVEL - (gs.hand_no - 1) % config.HANDS_PER_LEVEL
    c.hands_to_cap = max(0, config.MAX_HANDS - gs.hand_no + 1)
    c.chip_rank = rank
    avg = chips / alive if alive else 1
    c.stack_vs_avg = my_total / avg if avg > 0 else 1.0
    c.total_chips = chips
    c.covers = my_total >= best_opp
    tc = gs.to_call
    c.pot_odds = tc / (gs.pot + tc) if tc > 0 else 0.0
    behind_chips = eff - gs.my_bet
    c.spr = behind_chips / gs.pot if gs.pot > 0 else 99.0
    return c
