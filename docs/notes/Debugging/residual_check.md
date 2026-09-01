# residual_check.py — notes

Background pulled out of `Debugging/residual_check.py` to keep the script
itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase.

Confirms the LIVE residual-value accounting in `System_Model.Run_Strategy`
is correct for a generation asset, directly (no `LIFETIMES` toggle involved
-- this checks the real 25-year Generation life, not a diagnostic
override).

Residual loop being checked (`System_Model.py`, end of `Run_Strategy`):

```
life = LIFETIMES[Classification]        # 25 for Generation
used = END_YEAR - BuildYear + 1         # END_YEAR = 2051
remaining = max(0.0, (life - used) / life)
total_cost_t -= Capex * remaining / df_end
```

Asset under test: `Stage1_Wind_Buildout`, built 2029 under the real
`Strategies_2["Baseline"]` factory (not hardcoded -- pulled from the actual
Decision object `System_Model` builds, so a change to Baseline's build year
would be caught here rather than silently checked against a stale
assumption).

By hand: `life=25`, `used=2051-2029+1=23`, `remaining=(25-23)/25=0.08`, so
the residual credit should be exactly `0.08 x Capex()`, discounted to 2019
by `df_end = (1+RATE)**(2051-2019)`.

Rather than re-deriving life/used/remaining/RATE/END_YEAR as separate
hardcoded numbers, every value below is read from the real, unmodified
`Model_Components` / `System_Model` modules -- so this checks that today's
actual constants produce 0.08, not that a copied-down formula does.

## Replicating the residual loop's arithmetic

Replicating the residual loop's arithmetic, reading every constant from the
real modules (`Model_Components.LIFETIMES`, `System_Model.RATE`/`END_YEAR`)
-- not re-typed literals.
