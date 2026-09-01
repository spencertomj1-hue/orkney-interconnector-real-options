# mc_dimension_check.py — notes

Background pulled out of `Debugging/mc_dimension_check.py` to keep the
script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, changes
nothing.

Verifies `run_marginalised`'s draw dimensions (`Results.py` lines ~238-283)
BEFORE running the full Monte Carlo. Does not import `Results.py` itself
(it has no `__main__` guard -- importing it would execute the entire
multi-minute pipeline as a side effect). Instead replicates the exact
3-line sampling order from `run_marginalised`, empirically, against the
real `System_Model`/`Decision_Rules` modules.

## Confirm wx_seq actually changes Run_Strategy's output

Confirm `wx_seq` actually changes `Run_Strategy`'s output, holding
`capex_mult` and scenario fixed -- if it didn't matter, `gen_total` per year
(driven by `WIND_CF_BY_YEAR[wx_seq[t]]`) would be identical across the two
`wx_seq` draws.
