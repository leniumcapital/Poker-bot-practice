# Tournament Pokerbot

An 8-seat sit-and-go bot plus the tools to test it. Python standard library only, and every
decision is well inside the 1 ms limit. Practice build: `sim/` and the placeholder blinds and
payouts stand in until the organizers publish theirs.

See also: [`VARIANT_SWITCH.md`](VARIANT_SWITCH.md), [`ASSUMPTIONS.md`](ASSUMPTIONS.md).

## Commands

| Task | Command | Time |
|---|---|---|
| Tests | `python3 -m unittest discover -s tests -t .` | 5 s |
| Benchmark (100k `act()` calls) | `python3 tools/benchmark.py` | 20 s |
| Quick sim, all fields and payouts | `python3 tools/run_sim.py --quick` | 40 s |
| One cell of the sim | `python3 tools/run_sim.py --quick --fields tough --payouts flat` | 5 s |
| A/B a config change | `python3 tools/ab_test.py --quick --b-set CBET_FREQ=0.5` | 80 s |
| A/B an old tree | `python3 tools/ab_test.py --quick --a-path /path/to/old/bot` | 80 s |
| Try a named candidate | `python3 tools/tune.py --only open_140 --seed 12` | 50 s |
| Regenerate tables | `python3 tools/precompute.py` (`--quick` for a first pass) | 30 s |

Times are from this 8-core laptop. Full mode (`--tables 5000`) costs about 10x the quick
time, so at the event use it once at most.

## The 60-minute event

Sims are the slow part, so budget them. Most of the hour should go to the adapter and to
anything specific to the variant.

| Minutes | Do | Sim use |
|---|---|---|
| 0-10 | Read the kit. Write the adapter in `bot/agent.py`, set `PAYOUTS`, tag it, submit | none: tests only |
| 10-20 | Variant switch, if needed (`VARIANT_SWITCH.md`) | 1 quick |
| 20-40 | Use tournaments 1-3 as tests: real results beat our guessed fields | at most 2-3 quick A/Bs |
| 40-55 | Only changes with a clear reason. Benchmark before every submit | 1 quick per change |
| 55-60 | Lock the best stable version before tournament 6 | none |

## Event-round strategy

- Tournaments 4-6 are worth 71% of the score. Use 1-3 to test versions; lock in the most stable,
  best-performing bot before tournament 6.
- Never submit a version that hasn't passed the benchmark and a zero-fault sim.
- Keep a known-good version tagged so you can resubmit instantly: `git tag good-1`.
- A 500-table A/B only detects big effects (about +/-3% of even share overall). Don't chase
  smaller differences mid-event.

## Reading the results

`run_sim.py` prints points with a 95% CI next to `even` (the score of an average bot).
- `crash`, `t/out`, `illeg`: rule violations in the simulator. Must be 0.
- `fallbk`: exceptions caught **inside** `act()`. Must be 0. `act()` hides its own errors, so
  this is the only place a broken strategy shows up. The error text prints under the row.
- `jitter`: wall-clock overruns that didn't use the CPU time, meaning the OS preempted us. Not
  a bot fault, but see "Known risks".
- `maxCPU`: slowest decision in CPU microseconds.

Run benchmarks with nothing else running: under heavy load, wall p99 rose from 67 us to 221 us
with no code change.

## Strategy summary

**Preflop** (`preflop.py`), the highest-leverage part, picks a regime by effective stack:
- **Short, under 12 BB:** push/fold from the charts. Never min-raise and fold.
- **Medium, 12-25 BB:** shove from the chart up to 15 BB; above that, small opens. Reshove over
  raises, wider against late openers.
- **Deep, over 25 BB:** position-based opens, value 3-bets plus a few bluffs, fold to 4-bets
  except premiums. Isolate limpers.
- **All-in calls:** equity against the shover's estimated range must beat the price plus the
  ICM premium.

**Postflop** (`postflop.py`) sorts the hand into a tier from 0 (air) to 5 (monster), adds draw
equity by the 2/4 rule, and compares that to the price. It value-bets 55-75% of the pot, c-bets
heads-up as the raiser, doesn't bluff multiway, and stacks off with top pair or better when SPR
is 2 or less.

**ICM** (`icm.py`) turns chips into points. Exact with 5 or fewer players, a precomputed table
with 6-8, or whenever `act()` is running long.

**Opponents** (`opponents.py`) tracks per-seat VPIP, PFR, aggression, fold-to-steal and
fold-to-shove, shrunk toward priors. Seats become nit, TAG, LAG, station or maniac, which adjusts
bluffs, call-downs and estimated ranges.

## Config knobs (`bot/config.py`)

Any knob can be tested without editing: `--b-set NAME=VALUE`, dotted for dicts (`OPEN_PCT.2=0.6`).

| Group | Knobs | What they do |
|---|---|---|
| Variant | `VARIANTS`, `ACTIVE_VARIANT` | Game rules |
| Tournament | `PAYOUTS`, `HANDS_PER_LEVEL`, `MAX_HANDS`, `STARTING_STACK`, `SEATS` | **Set `PAYOUTS` at the event** |
| Safety | `TIME_BUDGET_S`, `GC_THRESHOLDS` | Skip optional work past this time; keep GC out of decisions |
| Regimes | `SHORT_MAX_BB`, `MEDIUM_MAX_BB`, `CHART_MAX_BB`, `MED_SHOVE_MAX_BB` | Stack cutoffs |
| Opens | `OPEN_PCT`, `OPEN_SIZE_BB`, `MED_OPEN_FACTOR`, `MED_OPEN_SIZE_BB`, `LIMPER_EXTRA_BB`, `ISO_FACTOR`, `BB_ISO_PCT` | Who opens and how big |
| vs a raise | `THREEBET_VALUE_PCT`, `THREEBET_BLUFF_LOW/HIGH/FREQ`, `THREEBET_SIZE_IP/OOP`, `FLAT_PCT_IP/OOP`, `MAX_FLAT_PRICE_BB`, `IMPLIED_MIN_SPR`, `BB_DEFEND_REALIZE` | 3-bet, flat, defend |
| vs a 3-bet+ | `FOURBET_PCT`, `FLAT_3BET_PCT`, `MAX_FLAT_3BET_STACK_FRAC`, `PREMIUM_PCT` | Continue only when strong |
| Shoves | `RESHOVE_LATE_FACTOR`, `RESHOVE_FE_BONUS`, `COMMIT_FRACTION`, `SHOVE_INSTEAD_FRACTION`, `LIMP_SHOVE_FACTOR`, `BB_SHOVE_VS_LIMP_FACTOR` | When a raise becomes all-in or fold |
| Ranges | `DEFAULT_SHOVE_PCT_DEEP`, `DEFAULT_3BET_PCT`, `DEFAULT_4BET_PCT`, `MIN_RANGE_PCT`, `MAX_RANGE_PCT` | What we credit opponents with |
| All-in calls | `MULTIWAY_EQUITY_FACTOR`, `BEHIND_RISK_MARGIN`, `CALL_ALLIN_MARGIN` | Extra caution on calls |
| Hand strength | `TIER_EQUITY`, `MULTIWAY_EQ_POWER`, `BET_SIZE_PENALTY`, `RAISED_PENALTY`, `CALL_MARGIN` | Postflop call-down tightness |
| Draws | `OUT_EQUITY`, `MAX_DRAW_EQUITY`, `IMPLIED_ODDS_BONUS`, `IMPLIED_MIN_SPR_POST`, `OVERCARD_OUTS`, `PAIRED_BOARD_OUT_DISCOUNT` | Outs to equity |
| Betting | `VALUE_BET_DRY/WET`, `CBET_SIZE`, `CBET_FREQ`, `CBET_WET_FREQ`, `RAISE_POT_FRAC`, `SHOVE_INSTEAD_POST` | Sizes and frequencies |
| Bluffs | `SEMIBLUFF_MIN_EQ/FREQ/SIZE`, `SEMIRAISE_MIN_EQ/FREQ`, `RIVER_BLUFF_FREQ/SIZE`, `THIN_VALUE_SIZE`, `THIN_VALUE_MIN_TIER`, `BIG_POT_MIN_TIER_MULTIWAY` | How often and into whom |
| Stack-off | `STACK_OFF_SPR`, `ICM_CALL_STACK_FRAC` | When to commit |
| ICM | `ICM_EXACT_MAX_PLAYERS`, `ICM_WEIGHT`, `ICM_MIN/MAX_PREMIUM`, `ICM_CAP_WINDOW`, `ICM_CAP_BOOST`, `ICM_SHOVE_TIGHTEN`, `ICM_GRID_*`, `CAP_SURVIVE_HANDS/FACTOR` | Survival vs chips. If the sandbox is slow, lower `ICM_EXACT_MAX_PLAYERS` to 4 |
| Opponents | `PRIOR_*`, `RANGE_LEARN_K`, `SHOVE_RATE_TO_RANGE`, `PFR_TO_RANGE`, `RANGE_PRIOR_PFR`, type cutoffs (`NIT_VPIP` and others), `BLUFF_FACTOR`, `CALLDOWN_ADJUST`, `CALL_TIGHTEN`, `STEAL_ADJUST_*` | Reads and how much they matter |

Simulator settings (blinds, field mixes, payouts) live in `sim/settings.py`.

## Tuning results

Adopted because each won on two separate seeds, then checked together:
`OPEN_PCT` x1.2, `TIER_EQUITY` lowered, `BET_SIZE_PENALTY` 0.22, `ICM_SHOVE_TIGHTEN` 0.75.

Not adopted, but worth one A/B if the real field looks loose: `open_140` (a further x1.4 vs the old
base scored +5.19% +/-1.32, but on one seed only, and our guessed fields may overstate it).

## Known risks

- **Wall-clock timeouts are possible through no fault of the bot.** If the sandbox measures wall
  time on a busy host, preemption can cost an occasional fold (about 1 call per 100k here over 1 ms).
- **Rare CPU overruns:** early tuning runs showed about 5 faults in 36M decisions that wouldn't
  reproduce, so most likely timing. The GC change should help, but this isn't proven at that scale.
- **The fields are our guesses.** Trust real tournament results over the simulator.
