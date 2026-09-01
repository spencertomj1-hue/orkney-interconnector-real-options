# FixAB_Comparison.py — notes

Background, citations, and rationale pulled out of `Comparisons/FixAB_Comparison.py` to
keep the module itself short.

## Purpose and replay methodology

A/B comparison of Fix A (`min_decision_year`) and Fix B (`npv_proxy` gate) against the
cached headline MC run (`Results.py`, `RUN_MC=True`, `seed=42`, `N=2000`, `NetZero_Tilt`
weighting). Replays the SAME draws from `MC_CACHE_PATH` — no resampling — so every config
is directly comparable to `Results.py`'s own printed table.

Baseline/Staged/Do Nothing are strategy-invariant to both fixes (neither touches a
Decision-based fixed-year strategy), so their NPV/cost/energy are read straight from the
cache rather than rerun. Only Flexible and Flexible 1-Stage (Cost-Aware) are rerun, once
per config.

"Current" config also reads straight from the cache (Fix A/B kwargs all default to
`None`/`"capex_screen"`, which reproduce `make_main_link_rule()`'s unmodified call
exactly) — included as a config label for the table, not recomputed, so there's no risk
of float drift from a redundant rerun.

## sys path setup for Comparisons scripts

Lives in `Comparisons/` — put `Coding/` (1 level up) back on `sys.path` so the
package-qualified imports below (`Model.System_Model` etc.) still resolve regardless of
invocation cwd.

## Cache provenance guard rationale

Loud-fail provenance guard: a cache built under different model-defining flags than THIS
run's current ones (`M.INCLUDE_WIND_BUILDOUT`/`M.WIND_AS_OPTION`) silently produces
wrong-world numbers — exactly what happened when `INCLUDE_WIND_BUILDOUT`'s default
flipped mid-session and this cache got regenerated under it with nothing on the pickle
saying so. A pre-guard cache (no `"metadata"` key) fails loud too, not a silent pass — an
un-stamped cache's provenance is unknown, not assumed-fine.

## Replay helper _paths_from_stored_z

Copy-pasted from `Results.py`/`Sensitivities.py` — same pattern used throughout this
project to replay a stored draw's demand/price/background paths from its correlated
shock block `z`, with no rng involved.

## Fix A v3 DFES-only observable rationale

Fix A (v3): `observable="dfes_background_gen_mw"` — isolates the DFES-only component of
`background_gen_mw`, excluding the exogenous Stage1/2 wind background whose FIXED,
scenario-invariant 2029/2030 schedule was found to dominate the combined signal's early
trajectory (by 2030 it alone contributes ~131.5MW, more than the entire DFES pipeline in
any scenario at that point). Two earlier variants (`min_decision_year` floor,
`min_real_points`/`trend_window` widening) were tested first and found NOT to help — see
the conversation this script's results were reported into.

This variant DOES produce genuine cross-scenario timing spread (confirmed below), but a
spot check (Falling Behind) found it can also cost real NPV (~£235m in that one scenario
alone) by making the trigger blind to congestion the ALREADY-COMMITTED wind buildout
causes regardless of DFES growth — included here for a full-ensemble, quantified read of
that trade-off, not because it's been validated as a net improvement.
