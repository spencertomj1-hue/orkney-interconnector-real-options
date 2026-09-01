# Sensitivities.py — notes

Background, citations, and design rationale pulled out of
`Reporting/Sensitivities.py` to keep the module itself short. Short inline
comments and one-line citation tags stay in the code; this file holds the
longer explanations, in source order.

## Overview

Sensitivity sweeps, split out of `Results.py`. Run `Results.py` first (with `RUN_MC=True`) so `MC_CACHE_PATH` exists — every Monte Carlo sweep below loads that cache's draws instead of redrawing them.

## References

[1] Henao, A., Sauma, E., Reyes, T., Gonzalez, A. (2017). What is the value of the option to defer an investment in Transmission Expansion Planning? An estimation using Real Options. Energy Economics 65, 194-207.

[2] Nur, G.N., MacKenzie, C.A., Min, K.J. (2026). Valuation of a sequential compound option considering electricity generation and transmission expansions. Journal of Economy and Technology 4, 57-76.

[4] Graça Gomes, J., Cardin, M.-A., Wu, B. (2025). Strategic real options and flexibility analysis for solar PV power plants. IET Powering Net Zero (PNZ 2025), Glasgow, UK.

## _check_cache_provenance: rationale

Loud-fail provenance guard: a cache built under different model-defining
flags than THIS run's current ones (`M.INCLUDE_WIND_BUILDOUT`/
`WIND_AS_OPTION`) silently produces wrong-world numbers — exactly what
happened when `INCLUDE_WIND_BUILDOUT`'s default flipped mid-session and
this cache got regenerated under it with nothing on the pickle saying so.
A pre-guard cache (no "metadata" key) fails loud too, not a silent pass —
an un-stamped cache's provenance is unknown, not assumed-fine.

## _paths_from_stored_z: copy-paste note

Turns a stored correlated shock block `z` (`n_years, 3`) + scenario name
into `(demand, price_seq, background_seq)` with no rng involved —
copy-pasted from `Results.py`'s `_paths_from_stored_z`.
`sample_demand_seq`/`sample_price_seq`/`sample_background_seq` never
touch their rng argument when `z_seq` is supplied, so passing `None` is
safe.

## _do_nothing: copy-paste note

Local-only zero-build reference case (a `Decision` with `BuildYear=None`
never fires — see `Model_Components.Decision.IsBuilt`). Copy-pasted from
`Results.py`, needed here for the cost-aware `cost_cap` sweep's "Do
Nothing" arm.

## PLOT_STRATEGIES: scope

`PLOT_STRATEGIES`: `TARGET_STRATEGIES` minus "Flexible 1-Stage
(Cost-Aware)" — the standard 4-strategy set every headline chart shows
(Baseline, Fixed 4-Stage, Flexible 4-Stage, Flexible 1-Stage), matching
`Results.py`'s own target curves. Prints (below) still use the full
`TARGET_STRATEGIES`.

## Discount rate table section: scope

All three (the table, the flat-vs-Green-Book comparison, and the
crossover curves) are deterministic (no Monte Carlo), so they don't touch
the MC cache at all — they call `Run_Strategy` directly, same as they did
in `Results.py` before the move.

## Flat vs Green Book declining schedule: rationale

The table above sweeps a single FLAT rate throughout the horizon — but
Green Book's real long-term schedule (`M.GREEN_BOOK_SCHEDULE`) is
declining (3.5% years 1–30, 3.0% years 31–75, ...), not flat, and this
model's horizon is exactly 33 years (2019–2051), so 2 of those years
(2050, 2051) fall in the 3.0% band under the real schedule while the
flat-3.5% default discounts them at 3.5% too. Checked directly: only a
~2-year difference in banding for THIS model's horizon, so expect a
small effect — reported rather than assumed, since "small" was a guess
until measured.

## Crossover curves: literature parallel

Discount-rate sensitivity of build-now-vs-defer value, and the crossing
rate where the ranking flips, is the same real-options question [1]
resolves with a binomial tree (its Table 6 demand-growth/discount-rate
sweep) and [2] resolves with a binomial lattice (its Fig. 20, option
value vs risk-free discount rate).

## Weighting sensitivity: Equal vs NetZero_Tilt rationale

The NetZero_Tilt ranking comes straight from the cache (`Results.py`'s
headline run, no need to recompute). The Equal-weighted run is a
genuinely different experiment (different scenario draw probabilities,
so NOT reconstructable from the cache's stored draws) — it needs its own
fresh run, same reasoning as every other "this specific thing can't be a
cache read" case flagged elsewhere in this file.

## Weighting sensitivity chart: colour-encoding choice

Magnitude across two categorical dimensions (strategy x weighting) →
grouped bars, same form as every other magnitude-by-category chart in
this report. Colour here encodes WEIGHTING, not strategy (that's the
dimension being compared), so it deliberately does NOT reuse `palette`
(which codes strategy identity everywhere else in this file), to avoid
implying the wrong thing is being colour-coded.

## RESIDUAL_ON_OVERRUN and CONSTRAINT_COST sensitivity: draw sourcing

Both sweeps share `weights=NetZero_Tilt`, `n=500`, drawn once per
iteration — every `Strategies_2` strategy runs under all 5 settings (2
residual flags + 3 constraint costs) on the same shared draw. Draws now
come from the cache's first `N_SENS` rows (verified bit-identical to
what this section's own `rng_sens=default_rng(42)`, `n=500` loop used to
draw independently, before the move — same seed, same per-iteration draw
order, so the first 500 of the cache's 2000 rows are the same 500 draws
either way).

## STAGED_LINK_FIXED_PER_STAGE sensitivity: rationale

No real-world figure exists to calibrate this against (see `Options.py`)
— swept instead of guessed harder. Same cache-draw pattern as section
9/10: "Flexible 4-Stage" re-run at every `fixed_per_stage` value,
"Flexible 1-Stage" (unaffected) once, all on the SAME cached draws.
Testing how a phased design's own per-stage cost assumption moves its
value relative to a non-staged alternative is the same question [4] asks
of phased PV deployment against a fixed design — there via LCOE, here via
ENPV.

## STAGED_LINK_THETA sensitivity: rationale

theta multiplies the Ofgem-scaled `background_gen_mw` threshold each
stage 2+ triggers on (see `Decision_Rules.make_staged_link_strategy`) —
no real basis for a specific value, swept instead of guessed harder.
Same cache-draw pattern as section 11.

## LINK_OPEX_RATE sensitivity: mechanism

Link assets read `LINK_OPEX_RATE` as a plain module global AT
CONSTRUCTION TIME, so mutating `Options.LINK_OPEX_RATE` before each
`factory()` call takes effect — same mechanism as the sensitivities
above.

## AVAIL sensitivity: mechanism

Unlike `LINK_OPEX_RATE`, `AVAIL` is baked into `WIND_CF_BY_YEAR` ONCE at
import time, not read fresh per year — `M.compute_wind_cf_by_year(avail)`
recomputes that dict, swapped in before each draw and restored after.

## GBM_SHOCK_CORR sensitivity: method

`GBM_SHOCK_CORR` is now measured from data (see `System_Model.py`), not
the original hand-picked guess — this quantifies that swap's ENPV effect
against `PLACEHOLDER_CORR_MATRIX` (kept in `GBM_Correlation.py` purely as
this comparison's reference point).

Unlike every sweep above, this one changes how the correlated
demand/price/background PATHS are drawn, not just how `Run_Strategy`
scores a fixed set of paths — but that's still fully reconstructable from
the cache, no fresh rng needed: `draw_z = z_indep @ L_measured.T` (see
`Results.py`'s `run_marginalised`), and `L_measured =
cholesky(GBM_SHOCK_CORR)` is known, so `z_indep = solve(L_measured,
draw_z.T).T` recovers the INDEPENDENT shock block exactly (verified: max
reconstruction error 2e-16, float64 machine epsilon) — then
re-correlating that same `z_indep` under either candidate matrix isolates
the correlation structure's effect from draw noise, same logic as the
pre-cache version, just without redrawing.

## CAPEX_P90 breakeven: method and caveats

`CAPEX_P90` is anchored to a single data point (SSEN's Sept 2024
Orkney-Caithness contract announcement — a floor, not a realised
outturn; see `System_Model.py`'s own caveat on `CAPEX_P90`). Do Nothing
came out competitive with, and often ahead of, the rigid strategies in
the headline MC — this asks how sensitive that is to `CAPEX_P90`
specifically, holding `CAPEX_MEDIAN` (1.4x, itself unsourced) fixed.

FLAGGED BEHAVIOUR CHANGE: before this file existed, this section drew
scenario/`wx_seq`/`z` BEFORE any capex concept (no `capex_mult` call
first), then drew `z_capex` directly — a different draw order from every
other section in the old `Results.py`, so its scenario/`wx_seq`/demand
values were NEVER the same as sections 9–16/18's at the same index `i`.
Here it instead reuses the cache's scenario/`wx_seq`/`z` (index-paired
with every other sweep in this file) and reconstructs `z_capex` by
INVERTING the stored `capex_mult`: `capex_mult = exp(mu + sigma*z)`
(numpy's `lognormal(mean, sigma)` is exactly `exp(Normal(mean, sigma))`,
so `z = (ln(capex_mult) - mu) / sigma` recovers the same shock exactly,
verified by round-trip to 0.0 max error). This makes `CAPEX_P90`
internally consistent with the rest of this file (paired draws
throughout), but its printed numbers will differ from the pre-refactor
`Results.py` version, which used a different, out-of-step draw order — a
deliberate change, not a bug.

`capex_estimate_seq` (the noisy early cost signal) also needs no fresh
rng: `sample_capex_estimate_seq` computes `seq[t] = capex_mult *
noise[t]` where `noise[t]` does NOT depend on `capex_mult`, so `noise[t]
= cached_seq[t] / cached_capex_mult` is recoverable from the cache, and
the swept `capex_mult`'s own estimate sequence is just `new_capex_mult *
noise[t]` — verified: in the tail years (`t >=
CAPEX_ESTIMATE_SHARPEN_YEARS`, `sigma_t=0`) `noise[t]` is exactly 1.0, so
`cached_seq[t]` there equals `cached_capex_mult` exactly, as the algebra
predicts.

## Cost-aware Main Link sweep: motivation

`Baseline_vs_DoNothing_Breakeven_Analysis.md`'s noise decomposition (Step
4) found demand/price/background GBM volatility, not capex overrun, is
the dominant driver of Baseline's headline underperformance vs Do
Nothing — capex+scenario noise ALONE actually favours Baseline slightly
at the current calibration. This asks the natural follow-up for
"Flexible 1-Stage" (which is already demand-aware, via Main Link's
trend-projected `background_gen_mw` trigger): does ALSO gating the build
decision on the noisy early `capex_mult` estimate (`make_main_link_rule`'s
`cost_cap` param, AND-ed onto the SAME trigger — see
`System_Model._flexible_cost_aware`) capture further incremental value,
or is demand-awareness already doing the useful work? `cost_cap` has no
real-world anchor (like `STAGED_LINK_THETA`/`FIXED_PER_STAGE` above) —
swept rather than guessed; 10.0 is a de facto "unconstrained" control
(above virtually every realisable `capex_estimate` draw, so the AND-gate
never blocks — should reproduce plain "Flexible 1-Stage" almost exactly).
Same cache-draw pattern as sections 11/12: "Flexible 1-Stage"
(demand-only) and "Do Nothing" run once per draw, "Flexible Cost-Aware"
re-run at every `cost_cap` value, all on the SAME draws.
