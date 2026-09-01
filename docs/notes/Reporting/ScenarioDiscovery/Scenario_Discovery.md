# Scenario_Discovery.py — notes

Design rationale, background, and assumptions pulled out of `Reporting/ScenarioDiscovery/Scenario_Discovery.py`
to keep the module itself short. Short inline comments stay in the code; this file holds the fuller
explanations, citations, and design history.

## Overview

Standalone PRIM (Patient Rule Induction Method) scenario discovery over the headline Monte Carlo draws. Run
this BY HAND, after `Results.py` has been run once with `System_Model.SCENARIO_DISCOVERY = True` (see that
file's capture block, right after `run_marginalised()`) so `Extra/ScenarioDiscovery/mc_draws.csv` exists.

This file is NEVER imported by `System_Model.py` or `Results.py` — the core model must never import
`ema_workbench` or any PRIM dependency, and it doesn't: grep the repo, nothing under `Coding/*.py` except this
file references PRIM. `ema_workbench` is a HARD dependency of this file only (`pip install ema_workbench` —
confirmed installed and working against this file, see the module below).

PRIM background: given an input matrix X (uncertain scenario parameters) and a binary outcome y (1 =
"loss"/bad case), PRIM iteratively shrinks ("peels") a box around the data, removing a small slice each step,
always choosing the slice that raises the resulting box's DENSITY (fraction of points inside the box that are
y=1) the most. As the box shrinks, its COVERAGE (fraction of all y=1 points captured) falls — that
coverage/density trade-off, traced out step by step, is the "peeling trajectory". The final box's bounds are
the scenario-discovery result: "loss is concentrated where capex_mult > 2.1 AND scenario == Falling Behind",
for example.

Reference: Friedman, J.H., Fisher, N.I. (1999). Bump hunting in high-dimensional data. Statistics and
Computing 9, 123-143 (the original PRIM algorithm). Bryant, B.P., Lempert, R.J. (2010) is the Robust Decision
Making application of PRIM to exploratory-modelling ensembles, which is the use case here — same idea
`ema_workbench.analysis.prim` implements.

## LCOE_FAIL_THRESHOLD: cutoff rationale

£/MWh cutoff for the `lcoe_above_threshold` OUTCOME — a cost-of-energy fail criterion rather than an NPV one,
so it can surface a different loss region (e.g. a strategy might stay NPV-positive on average while still
clearing a high per-MWh cost bar on the same draws). 80 is an illustrative cutoff, not fitted to anything —
change freely.

## STRATEGY_TO_COL: strategy selection and column-naming convention

The 4 headline strategies named in the brief, plus Flexible 1-Stage (Cost-Aware) as a 5th (Do Nothing is the
reference for the `worse_than_do_nothing`/`lcoe_above_threshold` OUTCOMEs, not looped here).

Column names must match `Results.py`'s own derivation exactly (its capture block builds each as
`"npv_" + sname.lower().replace(" ", "_").replace("-", "_")`, same for `"lcoe_"` — see `Results.py`'s
`SCENARIO_DISCOVERY`-gated block), not guessed here — confirmed directly against `mc_draws.csv`'s actual
header.

## STRATEGY_TO_LCOE_COL

Same strategies, pointed at `Results.py`'s per-draw incremental-LCOE columns instead of NPV — used only when
`OUTCOME="lcoe_above_threshold"` (see `strategy_col_map()` below).

## strategy_col_map: why a function, not a constant

Which column map applies to the active OUTCOME — NPV-valued outcomes read `STRATEGY_TO_COL`, the LCOE outcome
reads `STRATEGY_TO_LCOE_COL`. Kept as a function (not a module-level constant) so it re-reads `OUTCOME` if
that's changed after import, same as `OUTCOME_DISPLAY.get(OUTCOME, ...)` elsewhere.

## PEEL_ALPHA, PASTE_ALPHA, MASS_MIN: PRIM parameter defaults

Passed straight through to `ema_workbench.analysis.prim.Prim` — these are its own default values, named here
(not just left implicit) so they're visible and easy to tune without digging into the library.

- `PEEL_ALPHA`: fraction of in-box points considered for removal at each peeling step.
- `PASTE_ALPHA`: fraction considered for re-addition in PRIM's pasting phase (undoes an overly greedy peel).
- `MASS_MIN`: peeling stops once the box would hold less than this fraction of all draws.

## PAIRED_DRAWS

Draws are PAIRED across strategies (see `System_Model`/`Results.py` recon: all strategies in one
`run_marginalised()` call share the same draw index `i` — same `capex_mult`/scenario/weather/GBM shocks). Set
here as a constant, not re-derived from the CSV, because the CSV alone can't prove pairing — it reflects a
fact about how `Results.py` produced it. If `Results.py`'s MC loop is ever changed to draw independently per
strategy, this must be flipped to `False` by hand; the cross-strategy box comparison below assumes it's
`True`.

## NEVER_CROSSED_YEAR_SENTINEL

`year_bg135_raw_crossed` is NaN for draws where background generation never raw-crosses 135MW within the
model horizon (`System_Model.YEARS` ends 2051). PRIM can't handle NaN, so NaN is filled with a fixed
after-horizon sentinel (treated as "later than every real crossing year"), rather than dropping the column or
the rows. ASSUMPTION, flagged: 2052 is hardcoded here (this file deliberately does not import
`System_Model`, to keep it fully standalone from the model's own environment) — if `System_Model.YEARS`'s
span ever changes, this sentinel needs updating by hand to stay "after every real year".

## prepare_inputs: categorical handling of the scenario dimension

Demand scenario (4 DFES categories under `NetZero_Tilt` weighting) is categorical. HANDLING CHOSEN:
`ema_workbench`'s Prim supports a categorical column NATIVELY — given dtype `"category"` it peels the column
by removing one category at a time (a set-membership restriction, e.g. `scen: {A}` instead of a numeric
range), rather than the continuous quantile peeling used on every other column.

Confirmed directly against this library (tested standalone before writing this file): a plain string/object
column is auto-detected as categorical too, but cast to `"category"` dtype explicitly here rather than
relying on that implicit inference.

This is simpler and more interpretable than one-hot dummies (no risk of PRIM fixing 3 of 4 collinear dummy
columns to contradictory values) and is genuinely what the library's own PRIM implementation is built to do —
NOT run-PRIM-once-per-scenario, which would fragment the ~2000 draws into 4 much smaller, noisier
sub-ensembles, one per category.

## compute_loss_flag: NaN handling under lcoe_above_threshold

NaN entries (`dE~0`, or `dC<0 & dE>0` "dominates" — see `Results.py`'s `lcoe_from_stores`) compare `False`
under `>`, i.e. NOT a high-LCOE failure — correct: a dominates draw is strictly better than Do Nothing, not a
cost-per-unit figure at all, so it can't fail a cost-per-unit threshold.

## save_trajectory: plot choices

Trajectory CSV + 2 plots, both `ema_workbench`'s own built-in visualisations (not hand-rolled — "only use the
EMA stuff" applies to plotting too):

1. `show_tradeoff()`: the standard PRIM coverage-vs-density curve, one point per peeling step, coloured by
   how many dimensions are restricted at that step — lets you see the whole trade-off, not just the final
   box's stats.
2. `inspect(..., style="graph")`: the box's own bounds drawn as bars against the full data range per
   dimension, for the FINAL box specifically. Given its own fig/ax (default figsize truncates the
   dimension-name labels on the left when there are 5+ restricted dimensions, as several boxes here have)
   rather than letting it create one internally.

## box_bounds_dict: box_lims structure and "restricted" definition

`box.box_lims[-1]` is a DataFrame, index `[min, max]`, one column per input dimension. Continuous columns:
two float bounds. The categorical `"scenario"` column: both rows hold the SAME set of allowed categories
(`box_lims` stores it that way rather than as a single value) — `.iloc[0]` alone is enough to read it.
"Restricted" (in the box summary / cross-strategy comparison below) means this dimension's bounds are
narrower than the FULL data range that dimension started at (`box_lims` of trajectory step 0).

## Cross-strategy comparison figure: design and colour choices

One combined figure, small multiples — one panel per dimension, each on ITS OWN real-unit LINEAR x-axis,
rather than the earlier design that squashed every dimension onto one shared 0-1 "position within range"
axis — that abstraction was confusing (a reader has no intuition for what "0.4" means on a shared axis mixing
capex multiples, £/MWh and years) and is gone entirely. Every bar's real bound is now readable directly off
its own panel's axis, reinforced with a printed value label. No log-scaled axes anywhere in this figure, by
explicit request — a dimension with a very wide full range (e.g. `price_terminal_gbp_mwh`) can still render a
tightly-restricted box as a thin sliver near the low end; that's a consequence of the choice, not an
oversight.

`ema_workbench` has no built-in "compare N separate Prim() runs" plot (its own multi-box tools, e.g.
`Prim.boxes_to_dataframe`, compare SEQUENTIAL boxes from ONE Prim run on ONE y, not separate runs on 4
different y's/strategies like here), so this figure IS hand-rolled — but it only lays out numbers
`ema_workbench` already computed (`box_lims`), it doesn't re-implement any PRIM peeling logic itself.

Colour: the 4 strategies use the first 4 slots of this project's validated categorical palette
(`references/palette.md` in the dataviz skill), in fixed order — documented there as passing every
CVD/contrast gate on the "bars" adjacent pairlist (which is what this is: up to 4 bars grouped together
within one panel). ASSUMPTION, flagged: the palette validator script (`scripts/validate_palette.js`) needs a
node runtime, not available in this environment, so this specific combination was not re-run through it here
— relying on the pre-validated result documented in `palette.md` instead of a fresh check. Identity is also
never colour-alone regardless: every bar carries a printed value label, and a legend is always shown.

## COMPARISON_PLOT_EXCLUDE_DIMS: why these dimensions are dropped

Dimensions never shown on this comparison figure, even if some strategy's box restricts them — still a
legitimate PRIM input everywhere else (`mc_draws.csv`, `prepare_inputs()`, each strategy's own
`box_graph_*.png`, `box_summary.csv`). Excluded here only because it clutters this particular combined view,
per explicit request — not a claim it's uninformative.

`price_terminal_gbp_mwh` specifically: its full range spans ~0.0006 to ~8000+ (four orders of magnitude), so
on this figure's now-strictly-linear axes (no log scale anywhere, also by explicit request) every strategy's
box collapses to an unreadable sliver at x=0 — dropped rather than shown broken. Log scale would fix it but
was explicitly ruled out.

`wind_cf_proxy_mean`: dropped per explicit request — still a legitimate PRIM input everywhere else, this
panel just isn't shown on this figure.

## plot_cross_strategy_comparison: dims parameter semantics

`dims=None` (default): auto-select every dimension restricted by at least one strategy's box, minus
`COMPARISON_PLOT_EXCLUDE_DIMS`, most-restricted-by first — the full "where does each strategy lose money"
survey. Pass an explicit dims list (e.g. `["demand_terminal_gwh", "year_bg135_raw_crossed"]`) to instead
render exactly those dimensions, in that order, regardless of whether every strategy's box actually restricts
them — a focused variant for a specific pair/subset a reader should compare directly, not a survey.
`out_name` sets the output filename (no `.png` suffix) so the focused variant doesn't overwrite the full
comparison.

## Categorical dimension rendering in plot_cross_strategy_comparison

Set-membership restriction, not a numeric range — printed as text per strategy rather than a bar (position
on an axis has no meaning for a category).

## Full-range reference band in plot_cross_strategy_comparison

Full-range reference band, neutral grey (not a per-strategy colour — it's context, not a 5th series), drawn
once behind every bar.

## Cross-strategy comparison: excluding Flexible 1-Stage (Cost-Aware) from the charts

Charts only drop Flexible 1-Stage (Cost-Aware) (prints/`box_summary.csv` above keep it, and its own
`box_graph_flexible_cost-aware.png` / `peeling_trajectory_flexible_cost-aware.*` are untouched — those are
single-strategy PRIM outputs, not a shared comparison chart).

## Focused comparison variant: demand and bg135-crossing year

Focused 2-panel variant of the same figure — demand and the background-135MW-crossing year only, dropped
side by side for a reader who wants to compare just those two rather than the full dimension survey above.
Same rendering/legend/colour logic, same boxes — just a restricted dims list and a distinct output name so it
doesn't overwrite `cross_strategy_comparison.png`.
