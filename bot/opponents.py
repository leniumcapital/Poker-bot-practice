"""Per-seat stats within this table, shrunk toward priors. O(1) per observed action."""
from . import config as C
from . import tables as T

MAX_SEATS = 16


class OpponentModel:
    def __init__(self):
        self.reset()

    def reset(self):
        z = [0] * MAX_SEATS
        self.hands = list(z)
        self.vpip = list(z)
        self.pfr = list(z)
        self.raises = list(z)
        self.calls = list(z)
        self.steal_opps = list(z)
        self.steal_folds = list(z)
        self.shove_opps = list(z)
        self.shove_folds = list(z)
        self.shoves = list(z)
        self.shown_shove_pct = [0.0] * MAX_SEATS   # widest hand actually shown after a shove
        self.cur_hand = -1
        self.cursor = 0
        self.order = []
        self.n_dealt = 0
        self._new_hand_flags()

    def _new_hand_flags(self):
        self.vp_flag = [False] * MAX_SEATS
        self.pf_flag = [False] * MAX_SEATS
        self.shover_flag = [False] * MAX_SEATS
        self.raised_pre = False
        self.limped = False
        self.steal_live = False
        self.shove_live = False
        self.finished = False

    # ------------------------------------------------------------- updating ---

    def observe(self, gs):
        if gs.hand_no != self.cur_hand:
            self.cur_hand = gs.hand_no
            self.cursor = 0
            self._new_hand_flags()
            self.order = gs.order
            self.n_dealt = gs.n_dealt
            d = gs.dealt_in
            for i in range(len(d)):
                if d[i]:
                    self.hands[i] += 1
        self._consume(gs.history)

    def _consume(self, history):
        i = self.cursor
        n = len(history)
        while i < n:
            self._event(history[i])
            i += 1
        self.cursor = n

    def _event(self, e):
        street, seat, kind, _amount, allin = e
        if street != 0:
            if kind == "raise":
                self.raises[seat] += 1
            elif kind == "call":
                self.calls[seat] += 1
            return
        if kind == "raise":
            self.raises[seat] += 1
            if not self.vp_flag[seat]:
                self.vp_flag[seat] = True
                self.vpip[seat] += 1
            if not self.pf_flag[seat]:
                self.pf_flag[seat] = True
                self.pfr[seat] += 1
            if self.steal_live and self._is_blind(seat):
                self.steal_opps[seat] += 1
            if self.shove_live:
                self.shove_opps[seat] += 1
            if not self.raised_pre and not self.limped and self._is_late(seat):
                self.steal_live = True
            else:
                self.steal_live = False
            self.raised_pre = True
            if allin:
                self.shoves[seat] += 1
                self.shover_flag[seat] = True
                self.shove_live = True
        elif kind == "call":
            self.calls[seat] += 1
            if not self.vp_flag[seat]:
                self.vp_flag[seat] = True
                self.vpip[seat] += 1
            if not self.raised_pre:
                self.limped = True
            if self.steal_live and self._is_blind(seat):
                self.steal_opps[seat] += 1
            if self.shove_live:
                self.shove_opps[seat] += 1
        elif kind == "fold":
            if self.steal_live and self._is_blind(seat):
                self.steal_opps[seat] += 1
                self.steal_folds[seat] += 1
            if self.shove_live:
                self.shove_opps[seat] += 1
                self.shove_folds[seat] += 1

    def _behind_of(self, seat):
        order = self.order
        for i in range(len(order)):
            if order[i] == seat:
                return self.n_dealt - 1 - i
        return 9

    def _is_blind(self, seat):
        return self._behind_of(seat) <= 1

    def _is_late(self, seat):
        return self._behind_of(seat) <= 3

    def on_hand_end(self, result):
        """Sees what happened after we folded, plus any hands shown at showdown."""
        if self.finished:
            return
        self._consume(result["history"])
        self.finished = True
        holes = result.get("holes") or []
        for seat in result.get("values") or {}:
            if self.shover_flag[seat] and seat < len(holes):
                p = T.PCT[T.class_of(holes[seat])]
                if p > self.shown_shove_pct[seat]:
                    self.shown_shove_pct[seat] = p

    # ------------------------------------------------------------ estimates ---

    def vpip_rate(self, s):
        return (self.vpip[s] + C.PRIOR_VPIP * C.PRIOR_K) / (self.hands[s] + C.PRIOR_K)

    def pfr_rate(self, s):
        return (self.pfr[s] + C.PRIOR_PFR * C.PRIOR_K) / (self.hands[s] + C.PRIOR_K)

    def agg_rate(self, s):
        n = self.raises[s] + self.calls[s]
        return (self.raises[s] + C.PRIOR_AGG * C.PRIOR_K) / (n + C.PRIOR_K)

    def fold_to_steal(self, s):
        return ((self.steal_folds[s] + C.PRIOR_FOLD_STEAL * C.PRIOR_K_RARE)
                / (self.steal_opps[s] + C.PRIOR_K_RARE))

    def fold_to_shove(self, s):
        return ((self.shove_folds[s] + C.PRIOR_FOLD_SHOVE * C.PRIOR_K_RARE)
                / (self.shove_opps[s] + C.PRIOR_K_RARE))

    def player_type(self, s):
        if not 0 <= s < MAX_SEATS or self.hands[s] < C.MIN_HANDS_TO_TYPE:
            return C.UNKNOWN
        v = self.vpip_rate(s)
        p = self.pfr_rate(s)
        if p >= C.MANIAC_PFR:
            return C.MANIAC
        if v <= C.NIT_VPIP:
            return C.NIT
        if v >= C.STATION_VPIP and p / v <= C.STATION_MAX_PFR_RATIO:
            return C.STATION
        if v >= C.LAG_VPIP and p >= C.LAG_PFR:
            return C.LAG
        return C.TAG

    # --------------------------------------------- what the strategy consumes ---

    def shove_range(self, seat, base):
        """Blend the default shove range with how often this seat actually shoves."""
        if not 0 <= seat < MAX_SEATS:
            return base
        h = self.hands[seat]
        w = h / (h + C.RANGE_LEARN_K)
        rate = self.shoves[seat] / h if h else 0.0
        r = w * rate * C.SHOVE_RATE_TO_RANGE + (1 - w) * base
        shown = self.shown_shove_pct[seat]
        return r if r > shown else shown

    def raise_range(self, seat, base, raises_so_far):
        if not 0 <= seat < MAX_SEATS:
            return base
        h = self.hands[seat]
        w = h / (h + C.RANGE_LEARN_K)
        pfr = self.pfr[seat] / h if h else C.RANGE_PRIOR_PFR
        if raises_so_far <= 1:
            observed = pfr * C.PFR_TO_RANGE     # opens: raise rate is close to the range
        else:
            observed = base * (pfr / C.RANGE_PRIOR_PFR)  # re-raises scale with general aggression
        return w * observed + (1 - w) * base

    def _villain(self, gs):
        """The single live opponent, or -1 when there is more than one."""
        v = -1
        for i in range(len(gs.stacks)):
            if i != gs.seat and gs.dealt_in[i] and not gs.folded[i]:
                if v >= 0:
                    return -1
                v = i
        return v

    def blinds_fold_factor(self, gs):
        """Widen shoves and steals when players behind me fold too much; tighten otherwise."""
        idx = gs.n_dealt - gs.behind
        order = gs.order
        total = 0.0
        n = 0
        short = gs.bb * 15 >= gs.stack
        for i in range(idx, gs.n_dealt):
            s = order[i]
            if gs.folded[s]:
                continue
            total += (self.fold_to_shove(s) - C.PRIOR_FOLD_SHOVE if short
                      else self.fold_to_steal(s) - C.PRIOR_FOLD_STEAL)
            n += 1
        if n == 0:
            return 1.0
        f = 1.0 + C.STEAL_ADJUST_GAIN * total / n
        if f < C.STEAL_ADJUST_MIN:
            return C.STEAL_ADJUST_MIN
        return f if f < C.STEAL_ADJUST_MAX else C.STEAL_ADJUST_MAX

    def call_tighten_factor(self, gs):
        v = self._villain(gs)
        return C.CALL_TIGHTEN[self.player_type(v)] if v >= 0 else 1.0

    def is_station_like(self, gs):
        v = self._villain(gs)
        return v >= 0 and self.player_type(v) == C.STATION

    def bluff_factor(self, gs):
        v = self._villain(gs)
        return C.BLUFF_FACTOR[self.player_type(v)] if v >= 0 else 1.0

    def calldown_adjust(self, seat):
        return C.CALLDOWN_ADJUST[self.player_type(seat)]
