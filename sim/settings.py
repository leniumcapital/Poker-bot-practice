"""Simulator settings: placeholders until the organizers publish the real values."""
STARTING_STACK = 2000
SEATS = 8
HANDS_PER_LEVEL = 25
MAX_HANDS = 200
ANTE = 0
BLIND_SCHEDULE = [(10, 20), (15, 30), (25, 50), (40, 80), (60, 120), (100, 200), (150, 300), (250, 500)]
TIME_LIMIT_NS = 1_000_000            # 1 ms per decision

PAYOUTS = {
    "top_heavy": [100, 50, 25, 10, 5, 0, 0, 0],
    "flat": [8, 7, 6, 5, 4, 3, 2, 1],
}

# Relative weights per field mix. Each of the 7 opponent seats is drawn independently.
# "self" is a copy of the working-tree bot.
FIELDS = {
    "soft": {"random_legal": 1, "calling_station": 2, "nit": 1, "maniac": 1, "naive_equity": 2},
    "tough": {"simple_tag": 3, "naive_equity": 2, "self": 2},
    "all_tag": {"simple_tag": 1},
    "with_self": {"self": 3, "simple_tag": 1, "naive_equity": 2, "maniac": 1},
}
