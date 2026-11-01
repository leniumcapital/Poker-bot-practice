# Variant switch checklist (goal: 15 minutes or less)

The bot keeps working through every step: with no data file, `tables.py` falls back to a
formula, and a table regeneration replaces the file atomically.

| # | Step | Command / file | Time |
|---|------|----------------|------|
| 1 | **Add the variant** to `VARIANTS` and set `ACTIVE_VARIANT` | `bot/config.py` | 1 min |
| 2 | **Check evaluator rules** with a new case in `tests/test_variants.py` | see below | 2 min |
| 3 | **Run tests** | `python3 -m unittest discover -s tests -t .` | 10 s |
| 4 | **Regenerate tables** | `python3 tools/precompute.py` | 5-35 s |
| 5 | **Recheck push/fold charts** | snippet below | 1 min |
| 6 | **Benchmark** | `python3 tools/benchmark.py` | 30 s |
| 7 | **Sim** | `python3 tools/run_sim.py --quick` | 30 s |
| 8 | **Tag it** as known-good if crash, timeout and illegal are all zero | `git tag` | 10 s |

Measured regeneration: hold'em 30 s, short deck 11 s, Omaha 32 s, three-card hold'em 4 s.

## Step 1: what each field means

```python
"myvariant": {
    "ranks": "23456789TJQKA",  # low to high. The lowest straight is ace plus the lowest four.
    "suits": "cdhs",
    "hole_cards": 2,
    "street_cards": [3, 1, 1], # cards dealt per postflop street
    "hand_order": [...],       # weakest to strongest; changes what beats what
    "must_use_hole": 0,        # 0 = any five play; 2 = Omaha, exactly two from the hand
}
```

Ready to use: `holdem`, `shortdeck`, `omaha`, `holdem3`.

Things the config doesn't cover, which need code:
- **Hi-lo or lowball:** `evaluator.py` only ranks high hands.
- **Draw or stud games:** the engine and the state assume community cards.
- **Pot-limit or fixed-limit:** only the legal raise window changes. The organizers' state
  should provide it, and `actions.py` already clamps to it. Add it to `sim/engine.py` to test.
- **Other hole-card counts:** classes become 81 feature buckets automatically; check that
  `class_of` in `tables.py` still separates strong from weak hands.
- **Too few cards:** `seats * hole_cards + board` must fit the deck (for example, four-card
  short deck needs 37 cards from 36), or the simulator fails on the deal.

## Step 2: test the rule that changed

```python
def test_myvariant(self):
    self.check("myvariant", """
        assert E.eval_cards(c("...")) > E.eval_cards(c("..."))
    """)
```

## Step 5: read the charts

```bash
python3 - <<'PY'
from bot import tables as T
S = (3, 5, 8, 10, 12, 15)
print("source", T.SOURCE)           # must say "file"
for name, b in (("SB", 1), ("BTN", 2), ("UTG", 7)):
    print("push", name, [round(T.push_pct(b, s), 2) for s in S])
print("BB call vs SB", [round(T.call_pct(1, 0, s), 2) for s in S])
print("top 5 classes", T.ORDER[:5])
PY
```

Expect: ranges widen as stacks shrink, SB wider than BTN wider than UTG, and the strongest
classes first.

## Afterwards: retune if there is time

Equities change between variants, so these guesses shift most:
`TIER_EQUITY` (Omaha needs stronger hands to continue: raise the bar on one-pair hands),
`OUT_EQUITY`, `OPEN_PCT`, and `THREEBET_VALUE_PCT`. Run `tools/tune.py` on the candidates
most likely to matter.

For tools only, `POKERBOT_VARIANT=omaha python3 tools/...` overrides the active variant
without editing the config. Always ship with `ACTIVE_VARIANT` set in the file.
