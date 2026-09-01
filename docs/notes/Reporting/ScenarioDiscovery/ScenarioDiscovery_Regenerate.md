# ScenarioDiscovery_Regenerate.py — notes

Background and rationale pulled out of `Reporting/ScenarioDiscovery/ScenarioDiscovery_Regenerate.py` to keep
the script itself short.

## Overview

Regenerates `Extra/ScenarioDiscovery/mc_draws.csv` for the CURRENT link-only, no-wind headline default
(`INCLUDE_WIND_BUILDOUT=False`), replaying the cached `seed=42` `N=2000` draws — no resampling. Mirrors
`Results.py`'s `SCENARIO_DISCOVERY`-gated capture block (see `System_Model.SCENARIO_DISCOVERY`) LINE FOR LINE,
just fed from the cache's stored draws instead of a fresh `run_marginalised()` call, same pattern as every
other `_Comparison.py` script this session. Run `Scenario_Discovery.py` after this to redo the actual PRIM
analysis against the fresh CSV.

The previous `mc_draws.csv` (Aug 20, pre-dating this session's `INCLUDE_WIND_BUILDOUT` flip AND the Flexible
1-Stage (Cost-Aware) `npv_proxy` fix) was backed up to `mc_draws_stale_withwind_aug20.csv.bak` before this
overwrites it.

## sys.path setup rationale

Lives in `Reporting/ScenarioDiscovery/` — put `Coding/` (2 levels up) back on `sys.path` so the
package-qualified imports below (`Model.System_Model` etc.) still resolve regardless of invocation cwd.

## Replay: recomputing marg_store, marg_cost, marg_energy under current defaults

Recompute `marg_store`/`marg_cost`/`marg_energy` fresh under the current defaults (Flexible 1-Stage
(Cost-Aware) now uses `npv_proxy` via `Strategies_Flex`, unlike the stale CSV).
