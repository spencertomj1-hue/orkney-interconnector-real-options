# wind_scope1_equality_check.py — notes

Background pulled out of `Debugging/wind_scope1_equality_check.py` to keep
the script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, changes
nothing.

Step 2 verification for the `WIND_AS_OPTION=False` (Scope 1) refactor:
confirms every strategy sees an EXACT SAME generation world
(`state["gen_total"]` and `state["background_gen_mw"]`) at a fixed draw,
since wind is no longer an exercisable option in any strategy and should
now be identical background capacity everywhere. Checked both
deterministically (several DFES scenarios) and under real Monte Carlo
draws (stochastic `wx_seq`/`background_seq`/`price_seq`/demand, same draw
index shared across strategies, matching `run_marginalised`'s own draw
order in `Results.py`).

## Stochastic Monte Carlo check: draw order

Same draw order `run_marginalised` (`Results.py`) uses: `capex_mult`,
scenario, `wx_seq`, `capex_estimate_seq`, then the correlated `z` block ->
demand/price/background paths. Reused here so this is a genuine MC draw,
not a hand-picked deterministic case.
