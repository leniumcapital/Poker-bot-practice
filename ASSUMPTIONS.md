# Assumptions

Decisions made without asking, so they can be challenged quickly. Anything marked
**check at event** should be re-read as soon as the organizers publish details.

## Mode
- No starter kit in the repo, so this is practice mode: our own simulator in `sim/`.

## Interface (check at event)
- `Agent(seed=None, payouts=None).act(state_dict) -> {"action", "amount"}`.
- `amount` on a raise is the **raise-to total for the street**, not the increment.
- Cards are strings such as `"Ah"`. `state.py` also accepts ints in our own encoding.
- `history` is this hand's actions as `(street, seat, kind, amount, is_all_in)`.
- `on_hand_end(result)` is an optional hook. It shows the action after we fold and shown
  hands. Without it the opponent model still works but sees less.
- A new `Agent` per table, plus a reset if hand numbers go backwards.

## Simulator rules
- **Timeouts are judged on CPU time by default, not wall clock. This departs from the
  spec's wording.** Measured on this machine (4P + 4E cores), a section doing nothing
  exceeds 1 ms of wall clock about 4 times per million alone and about 200 times per
  million with all cores busy, and none of those overruns used 1 ms of CPU. Penalizing
  them would be noise that breaks identical-seed A/B pairing. Wall-only overruns are
  counted in the `jitter` column. `--wall-clock` restores strict enforcement.
  **We cannot control how the real sandbox measures this.** If it is wall clock on a
  busy host, the same preemption will occasionally cost a fold no matter how fast the
  bot is.
- `benchmark.py` gates on wall p99 and **CPU max**, for the same reason, and prints a
  no-op control beside the numbers. Wall max is reported but cannot be a stable gate here.
- The button moves to the next live seat (no dead-button rule).
- Blinds stay at the last level if hands run past the schedule.
- Short all-ins don't reopen betting; several short all-ins are not added together to
  count as a full raise (a TDA nuance, rare at these depths).
- At the cap, finishing place in the distribution table is by stack; points are ICM.
- Each opponent seat is drawn independently from the field mix weights. One hero per table.
- Field mixes are guesses at what hour-old AI bots look like. Tuning can overfit them.

## Strategy data
- Push/fold charts key on **players still to act**, not players remaining: with no antes,
  players who already folded don't affect the shove, so this covers every 2-8 player
  case with one table. **With antes**, set `ante_dead` in `iterated_best_response`
  (`tools/precompute.py`) and regenerate.
- Charts assume equal stacks and model only the first caller. They use one strength
  ordering, so they are an approximation: SB at 10 BB shoves 46% against about 58% in
  published Nash charts. Thresholds, not exact hand lists.
- Equity vs "top X%" uses one representative hand per class for card removal.
- Variants with 3+ hole cards use 81 coarse feature buckets rather than exact classes.
  Good enough to play; expect those charts to be much rougher than hold'em's.
- The bot's postflop outs in Omaha-style games are approximate (straight outs ignore the
  must-use rule).

## ICM
- Exact ICM runs only at 5 or fewer players (about 100 us for three evaluations). With 6-8,
  and whenever `act()` is already over `TIME_BUDGET_S`, a precomputed table is used.
- The table assumes an even-money all-in with equal stacks elsewhere.

## Packages
- Standard library only everywhere, including tooling. Tests use `unittest`. numpy and
  pytest weren't installed here, and this way nothing has to be installed at the event.
- `dataclass` is used without `slots=True`, to keep working on older Python versions.

## Repository
- None of this work has been committed: commits were not requested. Milestone snapshots used
  for A/B tests were temporary copies. See "Event-round strategy" in the README for tagging.
