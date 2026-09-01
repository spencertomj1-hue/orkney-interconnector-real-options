# background_retirement_scale.py — notes

Background and rationale pulled out of `Debugging/background_retirement_scale.py` to keep the script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, changes nothing.

Quantifies whether background-generation retirement matters materially, before deciding how (or whether) to model it. STEP 0 (`dfes_background_check.py`) established DFES's `BACKGROUND` is cumulative gross additions, not net -- so background generation is currently immortal in every draw. Before adding retirement logic ahead of the stochastic-buildout walk, measure whether it would change anything given the 2019-2051 horizon and a 25-year generation life.

Key structural fact checked below: DFES background data runs 2026-2051 (26 years). A cohort commissioned in year Y retires (per the model's own `Model_Components._alive` convention, `cy <= Year < cy+life`) once `Year >= Y+25`. For that retirement to land inside the horizon (<=2051), `Y+25 <= 2051`, i.e. `Y <= 2026`. So ONLY the pre-2026 base level (or a 2026 cohort) can possibly retire in-horizon -- every incremental cohort added 2027 onward retires after 2051 and is never seen by the simulation regardless of whether retirement logic exists. This is exactly why the task calls the pre-2026 base level "the only cohort old enough to retire well within horizon" -- confirmed structurally, not assumed.

Pre-2026 base-level commission-year assumption: no per-technology vintage source exists for this background figure (unlike `Existing_Wind`, which now has real REPD vintages in `Model_Components.py` -- a different, separately-tracked quantity, not this background base level). Assumed commissioned in a single representative year, `BASE_COMMISSION_YEAR = 2010`, for ALL technologies and scenarios -- a simplification for this screening exercise, not a vintage model. Sensitivity to this choice is discussed in the verdict.

## net_background: return semantics

`df`: DataFrame indexed by year (2026-2051), columns = tech, MW, cumulative immortal background (as currently used). Returns a matching DataFrame where each year's increment above the previous year is a cohort retiring at commission+life, and the pre-2026 base level is a cohort commissioned at `base_commission_year`.
