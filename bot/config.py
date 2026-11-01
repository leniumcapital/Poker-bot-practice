"""Every tunable number lives here. Retune between rounds without touching logic."""
import os

# ---------------------------------------------------------------- variant ---
_STD_ORDER = ["high_card", "pair", "two_pair", "trips", "straight", "flush",
              "full_house", "quads", "straight_flush"]

VARIANTS = {
    "holdem": {"ranks": "23456789TJQKA", "suits": "cdhs", "hole_cards": 2,
               "street_cards": [3, 1, 1], "hand_order": _STD_ORDER, "must_use_hole": 0},
    # Short deck: flush beats full house, A-6-7-8-9 is the low straight.
    "shortdeck": {"ranks": "6789TJQKA", "suits": "cdhs", "hole_cards": 2,
                  "street_cards": [3, 1, 1], "must_use_hole": 0,
                  "hand_order": ["high_card", "pair", "two_pair", "trips", "straight",
                                 "full_house", "flush", "quads", "straight_flush"]},
    # Omaha: four hole cards, exactly two must play.
    "omaha": {"ranks": "23456789TJQKA", "suits": "cdhs", "hole_cards": 4,
              "street_cards": [3, 1, 1], "hand_order": _STD_ORDER, "must_use_hole": 2},
    # Three-card hold'em: best five of any cards.
    "holdem3": {"ranks": "23456789TJQKA", "suits": "cdhs", "hole_cards": 3,
                "street_cards": [3, 1, 1], "hand_order": _STD_ORDER, "must_use_hole": 0},
}
# The POKERBOT_VARIANT env var is for tooling only; at the event just edit ACTIVE_VARIANT.
ACTIVE_VARIANT = os.environ.get("POKERBOT_VARIANT", "holdem")
VARIANT = VARIANTS[ACTIVE_VARIANT]

# -------------------------------------------------------------- tournament ---
STARTING_STACK = 2000
SEATS = 8
HANDS_PER_LEVEL = 25
MAX_HANDS = 200
PAYOUTS_TOP_HEAVY = [100, 50, 25, 10, 5, 0, 0, 0]
PAYOUTS = PAYOUTS_TOP_HEAVY          # replace with the announced distribution

# ------------------------------------------------------------------ safety ---
TIME_BUDGET_S = 0.0004               # skip optional steps once act() has used this much
# Default GC runs paused act() for 170-263 us, and those pauses set our max time. A high
# threshold moves them out of decisions without disabling GC (max fell to about 114-136 us).
GC_THRESHOLDS = (100000, 50, 100)


# ---------------------------------------------------------------- preflop ---
# Regime cutoffs, in effective big blinds.
SHORT_MAX_BB = 12                    # below this: pure push/fold
MEDIUM_MAX_BB = 25                   # below this: small opens and reshoves
CHART_MAX_BB = 15                    # push/fold charts stop here
MED_SHOVE_MAX_BB = 15                # medium stacks shove from the chart up to here

# Open ranges (top X% of hands) keyed by players still to act behind me (1 = SB, 2 = BTN, ...).
OPEN_PCT = {1: 0.48, 2: 0.50, 3: 0.34, 4: 0.24, 5: 0.19, 6: 0.16, 7: 0.13}
MED_OPEN_FACTOR = 0.80               # medium stacks open tighter
OPEN_SIZE_BB = {1: 2.5, 2: 2.2, 3: 2.3, 4: 2.3, 5: 2.5, 6: 2.5, 7: 2.5}
MED_OPEN_SIZE_BB = 2.1
LIMPER_EXTRA_BB = 1.0                # add 1 BB per limper when isolating
ISO_FACTOR = 0.65                    # iso-raise range relative to the open range
BB_ISO_PCT = 0.10                    # raise from the BB over limpers

# Facing a single raise, deep.
THREEBET_VALUE_PCT = 0.035
THREEBET_BLUFF_LOW = 0.10            # bluff band: hands too weak to flat with some blockers/playability
THREEBET_BLUFF_HIGH = 0.16
THREEBET_BLUFF_FREQ = 0.15
THREEBET_SIZE_IP = 3.0               # times the raise
THREEBET_SIZE_OOP = 3.7
FLAT_PCT_IP = 0.11
FLAT_PCT_OOP = 0.07
MAX_FLAT_PRICE_BB = 5.0              # do not flat opens bigger than this without a premium
IMPLIED_MIN_SPR = 8                  # flat speculative hands only when this deep vs the raise
BB_DEFEND_REALIZE = 0.82             # equity realized out of position when defending the BB

# Facing a 3-bet or more, deep.
FOURBET_PCT = 0.015                  # value 4-bet (usually a shove)
FLAT_3BET_PCT = 0.045                # call a 3-bet in position
MAX_FLAT_3BET_STACK_FRAC = 0.25      # never flat a 3-bet costing more than this share of the stack
PREMIUM_PCT = 0.02                   # never fold these to a 4-bet

# Reshoves over late opens at medium stacks.
RESHOVE_LATE_FACTOR = 1.25           # widen reshove when the opener is in late position
RESHOVE_FE_BONUS = 0.08              # equity credit for the chance the opener folds
COMMIT_FRACTION = 0.35               # a raise costing this share of my stack is an all-in decision
SHOVE_INSTEAD_FRACTION = 0.40        # an open this big relative to the stack is just a shove

# Estimated ranges for opponents' raises (top X%), before the opponent model adjusts them.
DEFAULT_SHOVE_PCT_DEEP = 0.08        # all-in with more than the chart's depth
DEFAULT_3BET_PCT = 0.07
DEFAULT_4BET_PCT = 0.025
MIN_RANGE_PCT = 0.015
MAX_RANGE_PCT = 1.0
MULTIWAY_EQUITY_FACTOR = 0.72        # equity multiplier for each extra all-in opponent
BEHIND_RISK_MARGIN = 0.008           # extra equity per player still to act behind me
CALL_ALLIN_MARGIN = 0.0              # flat margin added on all-in calls
LIMP_SHOVE_FACTOR = 0.85             # shove range over limpers relative to the chart
BB_SHOVE_VS_LIMP_FACTOR = 0.60       # BB shove range over a limp, heads-up or short

# --------------------------------------------------------------- postflop ---
# Estimated equity of each made-hand tier against one unknown hand:
#  0 air, 1 weak pair, 2 medium (second pair, weak top pair), 3 strong (top pair good
#  kicker, overpair), 4 very strong (two pair, set on a wet board), 5 monster.
TIER_EQUITY = [0.10, 0.30, 0.50, 0.68, 0.84, 0.96]
MULTIWAY_EQ_POWER = 0.45             # equity ** (1 + power * (opponents - 1))
BET_SIZE_PENALTY = 0.22              # equity lost per pot-sized bet faced (bets mean strength)
RAISED_PENALTY = 0.12                # further equity lost if the street was already raised
CALL_MARGIN = 0.02                   # required edge over the price on a made-hand call
OUT_EQUITY = {1: 0.04, 2: 0.02}      # the 2/4 rule by street (flop, turn); river has no outs
MAX_DRAW_EQUITY = 0.60
IMPLIED_ODDS_BONUS = 0.05            # extra credit for draws while stacks are still deep
IMPLIED_MIN_SPR_POST = 3.0           # implied odds only count with this SPR
OVERCARD_OUTS = 3                    # outs for two live overcards
PAIRED_BOARD_OUT_DISCOUNT = 0.75     # draws lose value when the board pairs

VALUE_BET_DRY = 0.55                 # pot fraction on dry boards
VALUE_BET_WET = 0.75                 # bigger when draws need charging
CBET_SIZE = 0.40
CBET_FREQ = 0.70                     # air c-bet frequency: heads-up, dry board, preflop raiser
CBET_WET_FREQ = 0.25                 # air c-bet frequency on wet boards
SEMIBLUFF_MIN_EQ = 0.28              # draw equity worth betting
SEMIBLUFF_FREQ = 0.65
SEMIBLUFF_SIZE = 0.60
SEMIRAISE_MIN_EQ = 0.40              # draw strong enough to raise a bet
SEMIRAISE_FREQ = 0.35
RIVER_BLUFF_FREQ = 0.12              # missed draws as the aggressor, heads-up, non-station
RIVER_BLUFF_SIZE = 0.65
THIN_VALUE_SIZE = 0.50
THIN_VALUE_MIN_TIER = 2
RAISE_POT_FRAC = 0.80                # raise size: call + this share of the resulting pot
STACK_OFF_SPR = 2.0                  # at or below this SPR, top pair+ gets it in
SHOVE_INSTEAD_POST = 0.60            # a bet this big relative to the stack is just a shove
ICM_CALL_STACK_FRAC = 0.30           # calls above this share of the stack pay an ICM premium
BIG_POT_MIN_TIER_MULTIWAY = 3        # bet into 2+ opponents only with this tier or better

# -------------------------------------------------------------------- ICM ---
ICM_EXACT_MAX_PLAYERS = 5            # exact three-way ICM costs ~100 us at 5, 200+ at 6
ICM_WEIGHT = 1.0                     # scale the premium; 0 plays pure chip EV
ICM_MAX_PREMIUM = 0.25               # sanity clamp on required extra equity
ICM_MIN_PREMIUM = -0.05              # ICM can occasionally favor gambling (huge dead money)
ICM_CAP_WINDOW = 25                  # within this many hands of the cap, survival gets extra weight
ICM_CAP_BOOST = 0.25                 # the premium grows by up to this fraction at the cap
ICM_SHOVE_TIGHTEN = 0.75              # shrink shove ranges by (1 - this * premium)
# Grid for the premium table used when too many players remain for exact ICM.
ICM_GRID_MY_STACK = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]   # my stack / average stack
ICM_GRID_OPP_RATIO = [0.5, 1.0, 2.0]                         # opponent stack / my stack
CAP_SURVIVE_HANDS = 8                # this close to the cap, fold more if blinds can't bust me
CAP_SURVIVE_FACTOR = 0.60            # shove-range multiplier when survival alone is safe

# -------------------------------------------------------------- opponents ---
# Bayesian shrinkage: estimate = (count + prior * k) / (n + k)
PRIOR_VPIP = 0.28
PRIOR_PFR = 0.16
PRIOR_AGG = 0.40
PRIOR_FOLD_STEAL = 0.65
PRIOR_FOLD_SHOVE = 0.75
PRIOR_K = 12                         # weight of the prior, in observed hands
PRIOR_K_RARE = 5                     # same, for the rarer situations (steals, shoves)
RANGE_LEARN_K = 25                   # hands until observed frequencies outweigh default ranges
SHOVE_RATE_TO_RANGE = 1.3            # shoves-per-hand underestimates the range (hands not unopened)
PFR_TO_RANGE = 1.15
RANGE_PRIOR_PFR = 0.16               # re-raise ranges scale by observed PFR over this

# Player type cutoffs.
NIT_VPIP = 0.16
STATION_VPIP = 0.38
STATION_MAX_PFR_RATIO = 0.35         # share of VPIP hands raised
MANIAC_PFR = 0.38
LAG_VPIP = 0.30
LAG_PFR = 0.20
MIN_HANDS_TO_TYPE = 8                # below this everyone is treated as unknown

NIT, TAG, LAG, STATION, MANIAC, UNKNOWN = "nit", "tag", "lag", "station", "maniac", "unknown"
BLUFF_FACTOR = {NIT: 1.3, TAG: 1.0, LAG: 0.8, STATION: 0.15, MANIAC: 0.5, UNKNOWN: 1.0}
CALLDOWN_ADJUST = {NIT: -0.08, TAG: 0.0, LAG: 0.05, STATION: -0.03, MANIAC: 0.12, UNKNOWN: 0.0}
CALL_TIGHTEN = {NIT: 1.2, TAG: 1.0, LAG: 0.9, STATION: 0.5, MANIAC: 0.7, UNKNOWN: 1.0}
STEAL_ADJUST_GAIN = 0.8              # range change per unit of fold-frequency edge
STEAL_ADJUST_MIN = 0.70
STEAL_ADJUST_MAX = 1.35
