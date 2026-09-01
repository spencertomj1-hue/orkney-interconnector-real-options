# mc_scenario_breakdown.py — notes

Background pulled out of `Debugging/mc_scenario_breakdown.py` to keep the
script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, changes
nothing.

Reconstructs `Results.py` Section 8's exact draws (same `seed=42`, `n=2000`,
Equal weighting, `ALL_STRATEGIES = Strategies_2 + Strategies_Flex`) to get
the per-draw DFES scenario and rule-firing log together in one place --
`Results.py` itself prints aggregate never-fired % but not broken down by
scenario, and this needs both jointly. Same rng call order as
`run_marginalised` (`Results.py` ~lines 262-278), so this reproduces the
identical draw stream `Results.py`'s own Section 8 run uses.

## ENPV when Extra Link fires vs when it doesn't

ENPV when Extra Link fires vs when it doesn't, on THESE SAME draws (paired
by draw index) -- a direct within-Monte-Carlo check of whether firing
correlates with better or worse Flexible 1-Stage outcomes.
