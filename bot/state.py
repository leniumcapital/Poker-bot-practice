"""Normalize the raw game state into a GameState. Missing fields get safe defaults."""
from dataclasses import dataclass, field
from . import config
from .evaluator import CARD_INT

STREET_INDEX = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}


@dataclass
class GameState:
    hole: list = field(default_factory=list)   # ints
    board: list = field(default_factory=list)  # ints
    street: int = 0                            # 0 preflop, 1 flop, 2 turn, 3 river
    pot: int = 0                               # everything in the middle, including live bets
    to_call: int = 0                           # capped at my stack
    current_bet: int = 0
    my_bet: int = 0
    min_raise_to: int = 0
    max_raise_to: int = 0
    can_raise: bool = False
    stack: int = 0                             # chips behind
    seat: int = 0
    button: int = 0
    stacks: list = field(default_factory=list)
    bets: list = field(default_factory=list)
    folded: list = field(default_factory=list)
    dealt_in: list = field(default_factory=list)
    sb: int = 1
    bb: int = 2
    ante: int = 0
    hand_no: int = 1
    history: list = field(default_factory=list)
    # Derived seat order: preflop action order (BB last), `behind` = players after me.
    order: list = field(default_factory=list)
    n_dealt: int = 2
    behind: int = 0
    # Set by the agent: the point distribution, its premium table, and the decision start time.
    payouts: list = field(default_factory=list)
    icm_table: dict = field(default_factory=dict)
    t0: float = 0.0


def parse_card(c):
    """Accept 'Ah' strings or ints already in our encoding."""
    if isinstance(c, str):
        return CARD_INT[c]
    return int(c)


def preflop_order(button, dealt_in):
    """Seats in preflop action order: UTG ... button, SB, BB (heads-up: button, BB)."""
    n = len(dealt_in)
    seats = [(button + i) % n for i in range(1, n + 1) if dealt_in[(button + i) % n]]
    # seats now runs SB, BB, UTG, ..., button
    if len(seats) == 2:
        return [seats[1], seats[0]]          # button (SB) first, then BB
    return seats[2:] + seats[:2]


def parse_state(raw):
    g = raw.get
    gs = GameState()
    gs.hole = [parse_card(c) for c in g("hole_cards") or []]
    gs.board = [parse_card(c) for c in g("board") or []]
    street = g("street", None)
    if street in STREET_INDEX:
        gs.street = STREET_INDEX[street]
    elif isinstance(street, int):
        gs.street = street
    else:
        gs.street = _street_from_board(len(gs.board))
    gs.pot = int(g("pot", 0) or 0)
    gs.to_call = int(g("to_call", 0) or 0)
    gs.current_bet = int(g("current_bet", 0) or 0)
    gs.my_bet = int(g("my_bet", 0) or 0)
    gs.stack = int(g("stack", 0) or 0)
    gs.max_raise_to = int(g("max_raise_to", gs.stack + gs.my_bet) or 0)
    gs.min_raise_to = int(g("min_raise_to", gs.max_raise_to) or 0)
    gs.can_raise = bool(g("can_raise", gs.max_raise_to > gs.current_bet))
    gs.seat = int(g("seat", 0) or 0)
    gs.button = int(g("button", 0) or 0)
    gs.stacks = g("stacks") or [gs.stack]
    n = len(gs.stacks)
    gs.bets = g("bets") or [0] * n
    gs.folded = g("folded") or [False] * n
    gs.dealt_in = g("dealt_in") or [s > 0 for s in gs.stacks]
    gs.bb = int(g("big_blind", 2) or 2)
    gs.sb = int(g("small_blind", gs.bb // 2) or 1)
    gs.ante = int(g("ante", 0) or 0)
    gs.hand_no = int(g("hand_number", 1) or 1)
    gs.history = g("history") or []
    gs.order = preflop_order(gs.button, gs.dealt_in)
    gs.n_dealt = len(gs.order)
    if gs.seat in gs.order:
        gs.behind = gs.n_dealt - 1 - gs.order.index(gs.seat)
    return gs


def _street_from_board(n):
    total = 0
    for i, k in enumerate(config.VARIANT["street_cards"]):
        total += k
        if n < total:
            return i
    return len(config.VARIANT["street_cards"]) if n else 0
