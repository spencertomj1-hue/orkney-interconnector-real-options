# Results.py — notes

Background, citations, and design rationale pulled out of `Reporting/Results.py`
to keep the module itself short. Short inline comments and one-line citation
tags stay in the code; this file holds the longer explanations, in source
order.

## References

[3] Salinas, D., Flunkert, V., Gasthaus, J. (2019). DeepAR: Probabilistic Forecasting with Autoregressive Recurrent Networks. arXiv:1704.04110.

[4] Graça Gomes, J., Cardin, M.-A., Wu, B. (2025). Strategic real options and flexibility analysis for solar PV power plants. IET Powering Net Zero (PNZ 2025), Glasgow, UK.

## Shared chart style

One consistent look for every figure this file produces: a validated
colorblind-safe categorical palette (fixed hue order — see dataviz palette
reference, adjacent-pairlist CVD gate), muted chrome (hairline
gridlines/spines, secondary-ink labels) instead of matplotlib's default
heavy black frame, and a couple of helpers so each chart block below states
its title/subtitle and gets the same treatment rather than hand-rolling
`ax.set_title`/`ax.grid`/spine calls per figure.

## CATEGORICAL palette: fixed hue order rationale

Fixed hue order — never re-cycled per chart, so a strategy's colour stays
the same across every figure it appears in (charts zip this positionally
against a strategy list, so append-only — see `TARGET_STRATEGIES` below).

Slots 1–2 (blue/orange) are the dataviz skill's own reference hues,
unchanged — already bold against this chart's light surface (contrast
4.30/3.12). Slots 3–5 (aqua/yellow/magenta) read as washed-out pastel at
the documented reference lightness AND sat too close together once
darkened uniformly (a first attempt at just darkening each in place pushed
contrast past 3:1 but left normal-vision separation between the darkened
yellow and magenta below the 15.0 floor — lightness alone can't carry 5
slots), so these three were rebuilt from scratch: a greedy farthest-colour
search at a fixed, bold lightness/chroma (L~0.53, near-max in-gamut
chroma) picked 3 hues maximising worst-case OKLab separation from
blue/orange AND from each other, both under protan/deutan simulation and
unsimulated.

Re-validated in this exact slot order (blue, orange, green, magenta,
gold): every pair clears 3:1 contrast, adjacent CVD dE 7.0–26.5 (one
adjacent pair — green/orange — sits in the 6–8 "floor" band, legal with
the direct labelling target-curve charts already use), normal-vision
floor 28.5 (comfortably clear of the 15.0 gate).

## _titled: headline and subtitle styling

Bold left-aligned headline + a smaller, secondary-ink subtitle line above
the axes, replacing the default centred two-line `ax.set_title` (which
renders the whole thing the same weight/colour).

## MC_CACHE_PATH: purpose and scope

Results.py owns the ONE real Monte Carlo run (the headline marginalised
MC, Section 2 below) and pickles it here. `Sensitivities.py` loads this
file instead of redrawing — so this needs to exist (run `Results.py` with
`RUN_MC=True` at least once) before that file is run. See the
`MC_CACHE_PATH` persistence block below Section 2. `Scenario_Discovery.py`
(PRIM-based scenario discovery, RDM sense) does NOT use this pickle — it
reads its own flat CSV capture instead, written by the
`SCENARIO_DISCOVERY`-gated block further down this file (see
`System_Model.SCENARIO_DISCOVERY`).

## _do_nothing: role as zero-build reference case

Local-only zero-build reference case (a `Decision` with `BuildYear=None`
never fires — see `Model_Components.Decision.IsBuilt`) — NOT part of
`System_Model.Strategies_2` (pruned to Baseline/Staged only), kept here
purely as the "build nothing" baseline every dNPV/dEnergy/incremental-LCOE
figure below is measured against, the same role `System_Model`'s old "Do
Nothing" strategy played before the prune.

## initial_year_capex: definition and scope

Undiscounted capex of the fixed-year asset(s) built in the earliest build
year, £, at `capex_mult=1.0` — a reference figure, not draw-dependent.
Rule entries are skipped: their build year isn't known until firing.

## _paths_from_stored_z: purpose and design

Draws demand, price and background-generation GBM paths from a SHARED
correlated shock block (`M.sample_correlated_gbm_shocks`) instead of
three independent draws — the single source of truth for the
year-alignment slicing (`background_gen_mw`'s own series starts 2026,
shorter than demand/price's full 2019–2051 span), used by every MC loop
below so the correlation structure applies everywhere.

Turns an already-drawn correlated shock block `z` (`n_years, 3`) plus a
scenario name into `(demand, price_seq, background_seq)`, with NO rng
involved — `sample_demand_seq`/`sample_price_seq`/`sample_background_seq`
never touch their rng argument when `z_seq` is supplied (see
`System_Model._ou_mult_seq`: `z_seq[t] if z_seq is not None else
rng.normal()`), so passing `None` here is safe and makes that explicit.

This is the reconstruction step `Sensitivities.py` copy-pastes, and the
`SCENARIO_DISCOVERY`-gated capture block further down this file calls
directly, to replay a stored draw's demand/price/background exactly,
without needing `System_Model.sample_correlated_gbm_shocks` or an rng at
all. `Scenario_Discovery.py` (PRIM) itself never calls this — it only
reads the scalar summaries that capture block already derived from it.

## run_marginalised: design and rationale

Marginalised Monte Carlo (the headline MC). Each draw samples ONE capex
multiplier, ONE DFES scenario, a weather sequence, a noisy early
`capex_mult` estimate, and CORRELATED demand/price/background-generation
GBM paths (draws `z` directly, then `_paths_from_stored_z` — see
`System_Model.GBM_SHOCK_CORR`) from a single rng, in that order — then
every strategy runs on that same draw, so comparisons stay paired
index-by-index. Weather/capex shocks remain independent of these three
and of each other. `strategies` defaults to `Strategies_2`; include
`Strategies_Flex` to keep flexible strategies on the same paired draws,
with their rule firing history returned as a 4th value.

Combining Monte Carlo simulation with the `Decision_Rules.py` managerial
decision rules, rather than solving the flexible strategies as a
backward-induction lattice, follows [4]'s own decision-rule + Monte Carlo
framework (default N below, 2000, matches [4]'s own MC sample size).

Also captures the raw per-draw inputs (`wx_seq`, `capex_estimate_seq`,
and the correlated GBM shock block `z`) that `Sensitivities.py` (and this
file's own `SCENARIO_DISCOVERY`-gated capture block, on
`Scenario_Discovery.py`'s behalf) need to reconstruct
demand/price/background WITHOUT redrawing — `System_Model`'s
`sample_demand_seq`/`sample_price_seq`/`sample_background_seq` all accept
a pre-computed `z_seq=` in place of rng, so storing `z` (not
demand/price/background themselves, which are just a deterministic
function of scenario+`z`) is the minimal sufficient state.
`capex_mult`/`scenario`/`wx_seq`/`capex_estimate_seq` are stored directly
because, unlike the GBM paths, they have no such `z_seq` bypass in
`System_Model` (`sample_wx_seq` and `sample_capex_estimate_seq` always
consume rng directly) — ASSUMPTION: nothing downstream needs to
regenerate a *different* `wx_seq`/`capex_estimate_seq` realisation for
the same draw index, only reuse the one already drawn here.

## run_marginalised: curtailment and LCOT store rationale

Absolute-LCOE/LCOT/curtailment plots (sections 2b–2e below) need these
alongside `cost_store`/`energy_store` — captured in the SAME loop as
everything else so they stay paired to the same draws, not recomputed
separately. `curtail_store`/`gen_total_store`: undiscounted GWh
(curtailment %'s numerator/denominator don't want a discount factor
baked in). `link_cost_store`/`link_export_store`: discounted, Link-only
(see `System_Model.Run_Strategy`'s `link_cost_t`/`pv_link_export`,
stashed in `state["link_cost_total"]`/`state["pv_link_export_gwh"]`) —
LCOT's numerator/denominator.

## sixsigma_xlim: robust bounds rationale

xlim bounds: median ± 6 robust-sigma of `pooled_vals`, intersected with
the actual data range. Robust-sigma = 1.4826*MAD rather than plain std —
plain std wasn't robust enough (one extreme outlier inflated it enough to
barely crop anything); MAD barely moves for one outlier in ~2000 draws,
so this crops to the readable bulk instead.

## lcoe_from_stores: dominance exclusion rationale

Incremental LCOE per draw vs `ref`, same definition as the deterministic
headline table, applied draw-by-draw. NaN where dE ~ 0.

dC<0 & dE>0 (strategy costs LESS than `ref` AND delivers MORE energy) is
excluded from the ratio, not just guarded like the dE~0 case — confirmed
against a real draw (see the marginalised-LCOE investigation, `Baseline`
vs `Do Nothing`, Electric Engagement, `capex_mult=1.10`: `Do Nothing`'s
curtailment bill alone, £1417m discounted, from zero-link-capacity
spilling ALL surplus background generation for 33 years, exceeds
`Baseline`'s entire net capex+opex) — this is genuine first-order
dominance on that draw, not a bug, but £/MWh "cost of energy" isn't a
meaningful description of it: a saving divided by a gain isn't a cost per
unit, it's dominance, and reporting it as a negative LCOE reads as an
arithmetic error even though it isn't one. Reported as its own
"dominates" rate instead (see the print loop below) — doesn't happen at
all in the deterministic (no-noise) headline table, confirmed by direct
check across all 4 DFES scenarios at `capex_mult=1.0` — purely a
GBM-noise-driven phenomenon on particular unlucky-for-`ref` draws, not a
deterministic-case bug either.

## Section 2: marginalised MC setup rationale

Rigid + flexible run together in one pass (used to be two separate,
identical-draw-stream calls — duplicate compute, removed). "Do Nothing"
is included here (not just in the deterministic section above) so
`lcoe_from_stores`' `ref="Do Nothing"` default has a real
`cost_store`/`energy_store` entry to read during the marginalised MC too.
`NetZero_Tilt` (not `Equal`) is the standard weighting for every
plot/table below — see `M.SCENARIO_WEIGHTS` for the tilt itself; `Equal`
is still run as the comparison case in section 7.

## TARGET_STRATEGIES and TARGET_LABELS: purpose

Target curves only (all other sections below — the headline metrics
table, dominance check, `ALL_STRATEGIES`-keyed sweeps — still show every
strategy under its real name, unchanged): every strategy except "Do
Nothing" itself (it's the reference every dNPV/curtailment-reduction
figure elsewhere is measured against, not a target-curve entry here) —
`TARGET_STRATEGIES` stays the real `ALL_STRATEGIES`/`marg_store` data
keys (so every existing `marg_store[sname]`-style lookup keeps working
unmodified), `TARGET_LABELS` is the display name used wherever a
target-curve plot/print shows a strategy's name — the identity map (every
strategy's real name IS its display name, now that names encode
fixed-vs-flexible and stage count directly; `TARGET_LABELS` is kept, not
inlined, only so every existing `TARGET_LABELS[...]`/`.get(...)` call
site below keeps working unmodified).

"Flexible 1-Stage (Cost-Aware)" AND-gates Main Link's build decision on
the noisy early capex estimate on top of the demand trigger
(`M.MAIN_LINK_COST_CAP`) — see
`Cost_Aware_Flexible_Strategy_Investigation.md` for why it's here: a
Results.py N=500 `cost_cap` sweep found it adds ~£35m ENPV over plain
Flexible 1-Stage, enough to flip it from losing to Do Nothing to beating
it.

New strategies are appended at the END (not inserted between existing
entries) so each gets the next unused palette colour and every other
strategy's existing colour (zip-assigned positionally) stays exactly as
it was — adding a strategy shouldn't silently repaint the others.

## PLOT_STRATEGIES: scope and colour lookup

`PLOT_STRATEGIES`: `TARGET_STRATEGIES` minus "Flexible 1-Stage
(Cost-Aware)" — charts only, by request. Every printed table/console
output below still uses `TARGET_STRATEGIES` (unchanged, still shows
Cost-Aware); only the actual `ax.plot`/`ax.bar` loops switch to this.
Colours are looked up BY NAME from a dict (not by re-zipping a shortened
parallel list), so removing one strategy can't silently shift another's
colour.

## Persisting the headline MC cache

This is the ONE real Monte Carlo run (seed=42, N=2000, NetZero_Tilt
weighting, `ALL_STRATEGIES`). The two sibling files load this pickle
instead of redrawing — see `MC_CACHE_PATH` at the top of this file.
ASSUMPTION flagged explicitly: only `ALL_STRATEGIES`' NPV/cost/energy/
rule_log are saved, not every strategy dict that might ever be swept
(e.g. a strategy built with a non-default `STAGED_LINK_FIXED_PER_STAGE`)
— those still need `Run_Strategy` re-run on the loaded raw draws, which
is exactly what `Sensitivities.py`'s sweeps do.

## MC cache: provenance stamp rationale

Provenance stamp: which model-defining flags were live when this cache's
`marg_store`/`marg_cost`/`marg_energy` were actually computed. A cache is
only valid to read under the SAME flags — pulled LIVE off the `M` module
here, not hardcoded, so this can't drift out of sync with what this run
actually used. Checked on every load site (`Sensitivities.py`,
`FixAB_Comparison.py`, `NoWindBuildout_Comparison.py`) — see their
`_check_cache_provenance`. Added after a real incident:
`INCLUDE_WIND_BUILDOUT`'s default flipped mid-session, this cache got
silently regenerated under the new default, and a fresh with-wind rerun
later disagreed by ~£1bn/strategy with no way to tell from the pickle
alone.

## Scenario discovery capture layer: gating and scope

Default OFF (`System_Model.SCENARIO_DISCOVERY`). When True: builds a flat
experiments table, one row per headline MC draw above (same draws as
`marg_store`/`marg_raw_draws` — NOT a fresh draw), and writes it to
`Extra/ScenarioDiscovery/mc_draws.csv` for `Scenario_Discovery.py` (a
separate, standalone file this model never imports) to read. When False:
this whole block is skipped — no file, no import (`pandas` is imported
only inside this branch, even though it is already a transitive
dependency via `DFES_Background.py`, so the off-switch stays
self-contained rather than relying on that transitive fact).

## Scenario discovery: path-to-scalar summary approach

PRIM needs continuous scalars, not paths, so every path-valued input gets
exactly one scalar summary below. ASSUMPTION (flagged once, applies to
all of them): these are illustrative choices, not the only sensible ones
— a different summary (e.g. wind CF in one specific late year, instead
of a path mean) could surface different PRIM boxes from the same draws.

## Scenario discovery: wind_cf_proxy_mean derivation

`wx_seq`: a sequence of weather-YEAR LABELS (categorical, e.g. 2012,
2013...), not CF values directly. Map each label to that year's mean
wind CF (`M._year_means`) and average across the 33-year path — a single
"was this draw generally windy or calm" number. ASSUMPTION: a path-mean
discards WHEN in the horizon windy years fell, which could itself matter
(e.g. windy early vs late).

## Scenario discovery: capex_estimate_year0 derivation

`capex_estimate_seq`: noisy early estimate of `capex_mult`, sharpens
LINEARLY to the true value by `CAPEX_ESTIMATE_SHARPEN_YEARS` (=5 years)
— see `System_Model.sample_capex_estimate_seq`. Only the early part of
the path carries information `capex_mult` itself doesn't already give, so
use year-0 (2019), the noisiest and earliest estimate — the one furthest
from the eventual true value, and the one the cost-aware rule's first few
evaluations see. ASSUMPTION: year-0 is a reasonable single-point summary
of "how wrong did the early signal look"; a mean over the sharpening
window would smooth out exactly the noise that's most decision-relevant
to the cost-aware strategy.

## Scenario discovery: terminal-year path summaries

`z` (the correlated GBM shock path, demand/price/background): not stored
directly — reconstructed into economically meaningful terminal-year
quantities via the SAME `_paths_from_stored_z` helper the MC loop above
already uses (a pure function of `z` + scenario, no rng involved, so this
is an exact replay of what `run_marginalised` did for each draw, not a
re-draw). Terminal year (2051) is chosen over a cumulative multiplier so
the summary is directly comparable in the model's own units (GWh / £ per
MWh / MW). ASSUMPTION: terminal-year level is the summary of interest
here — a path that spikes mid-horizon and reverts summarises identically
to a flat path under this choice.

## Scenario discovery: year_bg135_raw_crossed proxy

Background generation, net of the existing fleet, first exceeding
`MAIN_LINK_BG_GEN_THRESHOLD` (135MW) — the RAW (untrailed) year, not a
trailing-mean crossing. IMPORTANT ASSUMPTION, explicitly flagged: this is
a SIMPLIFIED proxy, not a replica of the live Main Link rule —
`make_main_link_rule` (`Decision_Rules.py`) actually uses
`TrendProjectedRule` with `TREND_WINDOW=4` and a linear-trend
extrapolation + lookahead, not a raw or trailing-mean threshold test, and
`state["background_gen_mw"]` itself is discarded per draw in
`run_marginalised` (never captured), so this recomputes the
net-of-existing-fleet arithmetic independently from `z` rather than
reading anything the rule engine actually evaluated. Useful as a rough
"when did background generation ramp up" PRIM input, but do not read it
as "the year the rule would have fired."

## Scenario discovery: scenario column encoding

`scenario`: categorical (4 DFES scenarios under NetZero_Tilt weighting),
left as a plain string column here rather than one-hot encoded —
`Scenario_Discovery.py` (the standalone PRIM module, never imported by
this model) is what actually needs continuous inputs, so encoding is its
job, not this capture layer's. See that file's own header comment for
which approach it takes.

## Scenario discovery: incremental LCOE column

Incremental LCOE per draw, £/MWh vs Do Nothing — same definition
(`lcoe_from_stores`) as the marginalised LCOE target curves in section 2b
below, reused rather than recomputed so a "high LCOE" scenario-discovery
outcome (`Scenario_Discovery.py`'s `lcoe_above_threshold`) reads the
identical figure the LCOE target curve plots. NaN (dE~0, or dC<0&dE>0
"dominates" — see `lcoe_from_stores`'s own comment) is left as NaN, not
filled: PRIM's loss flag treats `NaN > threshold` as False, i.e. NOT a
high-LCOE failure — correct for both cases, since a dominates draw is
strictly better than Do Nothing and isn't a cost-per-unit figure at all.
No "lcoe_do_nothing" column — Do Nothing is the reference, same exclusion
`lcoe_from_stores` itself applies.

## Target curves: absolute NPV rationale

`marg_store` holds each strategy's ABSOLUTE NPV per draw (not vs a
reference) — an ECDF of it is a "target curve": P(NPV ≤ x), the same
cumulative-distribution reporting [4] uses for LCOE (its Figs. 4–5) in
place of a single point estimate — reporting the full outcome
distribution rather than a point forecast is also the philosophy behind
DeepAR's quantile/coverage-based evaluation [3] of a predictive
distribution, applied here to NPV rather than a time series. "Do Nothing"
is excluded from this plot (`TARGET_STRATEGIES`, not `ALL_STRATEGIES`).

## Target curves: x-axis cropping

x-axis: cropped to mean ± 6 std (pooled across plotted strategies) so a
handful of extreme draws don't stretch the axis and squash the readable
bulk of each curve.

## PNZ 2025 results-presentation methods: overview

PNZ 2025 results-presentation methods (Graça Gomes, Cardin & Wu 2025, IET
Powering Net Zero — see this file's own [4]/Options.py's [5] citation of
the same paper). Moved in from the standalone `Results_Presentation.py` —
same functions, now reading
`marg_store`/`draw_capex`/`draw_scenario`/`marg_raw_draws`/`_paths_from_stored_z`
directly from this section's own closure instead of round-tripping
through the `MC_CACHE_PATH` pickle (no behavioural change, just no
redundant pickle read since the data's already live here).

Representations already covered elsewhere in this file, NOT reimplemented
here: point-metric summary table + P5/P95 percentile columns
(`print_metrics_table`, above), CDF/target curves (the "Target curves —
absolute NPV" block, above).

## PNZ strategy name mapping

The task's 4 named strategies (Baseline / Staged / Flexible / Flexible
Cost-Aware) map onto this codebase's current strategy names as follows —
NOT the same 4 the target-curve chart above plots (that chart's
`PLOT_STRATEGIES` shows Baseline/Fixed 4-Stage/Flexible 4-Stage/Flexible
1-Stage, dropping Cost-Aware; the brief's list instead names Cost-Aware
and omits the 4-stage flexible variant) — used for every
PNZ-representation function below so they match the brief's own words,
not silently redefined to match the target-curve chart's convention.

## assert_paired_draws: purpose

Abort (do not proceed) if the requested strategies' MC draws are not
paired on a shared per-draw index. `marg_store`'s arrays are paired by
construction — `run_marginalised` (above) draws capex/scenario/weather/`z`
ONCE per index `i`, then scores every strategy on that SAME `i` — checked
here rather than assumed, since every ΔNPV/CDF-overlay representation
below is meaningless on unpaired arrays.

## plot_capex_distribution: choice of input

Histogram of a stochastic model INPUT across MC draws. Uses `draw_capex`
(the lognormal link-capex cost-overrun multiplier,
`M.CAPEX_MEDIAN`/`CAPEX_SIGMA`) — the model's per-draw stochastic input
most directly analogous to [5]'s cost-driver histogram.
`CONSTRAINT_COST` (the brief's other named example) is a fixed, swept
CONSTANT in this model (`M.CONSTRAINT_COST_SWEEP = [55, 70, 98]` £/MWh),
not a per-draw random variable — there is no distribution of it to
histogram, so capex is used instead (the brief names it as an acceptable
alternative).

## PNZ_N_SENS: sizing rationale

Matches `Sensitivities.py`'s own subsample size for parameter sweeps —
the cache's first N rows, not a fresh draw.

## _paired_value_of_flexibility: method

Paired per-draw ΔNPV(`flex_name` − `base_name`) at each swept value of
one model parameter, replaying the FIRST `PNZ_N_SENS` draws already in
memory (capex/scenario/weather/correlated-shock paths all read from
`marg_raw_draws`/`draw_capex`/`draw_scenario`, not redrawn) —
`Run_Strategy` is re-scored under each swept setting, the same mechanism
`Sensitivities.py`'s own sweeps already use, not a fresh Monte Carlo
simulation.

## print_headline_value_of_flexibility: definition

Single headline value-of-flexibility figure: best strategy (by ENPV, Do
Nothing excluded as the zero-build reference rather than a competing
strategy) vs Baseline, as a percentage. Paired per-draw
(`assert_paired_draws`), read straight from `marg_store` — not
recomputed.

## build_reference_input_table: scope

The model's cost/parameter assumptions as one formatted table, read
directly off `System_Model.py`/`Options.py`'s own module-level constants
and asset classes — nothing computed, nothing re-simulated, no model
file touched.

## Sections 9-18: moved to Sensitivities.py

Sections 9–18 (`RESIDUAL_ON_OVERRUN`, `CONSTRAINT_COST`,
`STAGED_LINK_FIXED_PER_STAGE`, `STAGED_LINK_THETA`, `LINK_OPEX_RATE`,
`AVAIL`, `GBM_SHOCK_CORR`, `CAPEX_P90` breakeven, cost-aware `cost_cap`
sweep) moved to `Sensitivities.py` — every one of them is a parameter
sweep against a fixed modelling assumption, not core headline reporting.
They now load this file's MC cache (`MC_CACHE_PATH`) for their shared
draws instead of redrawing — see `Sensitivities.py` for the
numerical-equivalence note on why that's safe for every sweep except
`CAPEX_P90` (flagged there).
