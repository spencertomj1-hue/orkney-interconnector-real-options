# NoWindBuildout_Comparison.py — notes

Background, citations, and rationale pulled out of
`Comparisons/NoWindBuildout_Comparison.py` to keep the module itself short.

## Purpose and scope

Tests `System_Model.INCLUDE_WIND_BUILDOUT=False`: Stage1/2 wind removed from EVERY
strategy entirely (no capacity, no generation, no `background_gen_mw` contribution
anywhere) — the ONLY generation growth left is the DFES-sourced `BACKGROUND[scenario]`
pipeline. This is the economically-consistent version of the "isolate the DFES-only
signal" idea tried in `FixAB_Comparison.py`'s Fix A (v3): that earlier attempt only
changed what the TRIGGER could see (`observable="dfes_background_gen_mw"`) while leaving
Stage1/2 wind's capacity/congestion fully present in the actual dispatch — a mismatch
that made the trigger blind to real, already-happening congestion. Removing wind from
the model entirely instead keeps trigger and dispatch consistent, so if genuine option
value still doesn't show up here, that's a much stronger result than the earlier partial
test.

Every strategy is affected (not just the two rule-driven ones), so unlike
`FixAB_Comparison.py` this reruns ALL FIVE strategies — none of them can be read straight
from the cache. Still replays the cache's `seed=42` draws (`capex_mult`/`scenario`/
`wx_seq`/`capex_estimate_seq`/`z` are all independent of whether wind exists) — no
resampling.

## sys path setup for Comparisons scripts

Lives in `Comparisons/` — put `Coding/` (1 level up) back on `sys.path` so the
package-qualified imports below (`Model.System_Model` etc.) still resolve regardless of
invocation cwd.

## Cache provenance guard rationale

Loud-fail provenance guard, checked HERE (immediately after load, before either
`_run_all(True, ...)`/`_run_all(False, ...)` call below mutates
`M.INCLUDE_WIND_BUILDOUT`) — so this compares against the AMBIENT default (currently
`False`, no-wind), not whatever this script's own two arms temporarily set it to
internally. A cache built under a different default than the one this session actually
runs with silently produces wrong-world numbers — exactly what happened when
`INCLUDE_WIND_BUILDOUT`'s default flipped mid-session and this cache got regenerated
under it with nothing on the pickle saying so. A pre-guard cache (no `"metadata"` key)
fails loud too, not a silent pass.

## LCOT inputs captured per strategy

LCOT inputs — discounted Link-only cost / discounted energy exported THROUGH the link
(`System_Model.Run_Strategy`'s `state["link_cost_total"]`/`state["pv_link_export_gwh"]`),
captured alongside cost/energy so a never-built draw's LCOT can be told apart from a
genuinely-free one (see `lcot_from_stores` below — FIX 1).

## Sanity check against the cache

Sanity check: this rerun should reproduce the cache's own stored NPVs exactly (same
draws, same default kwargs, both under the standard without-wind default) — confirms
this script's replay machinery is correct before trusting anything derived from it
below.

## Flexible 1-Stage build year by scenario

Scenario breakdown for Flexible 1-Stage's build year, without wind — the thing actually
being tested: does DFES-only divergence now show up as scenario-differentiated TIMING?

## LCOT definition and never-built draws

LCOT = discounted Link-only cost / discounted energy exported through the link
(`System_Model.Run_Strategy`'s `link_cost_t` / `pv_link_export` — see `Results.py`'s own
LCOT section for the same construction on the headline cache). NEVER-BUILT DRAWS ARE NOT
EXCLUDED: `link_cost_t` already includes the pre-existing 40MW cable's own opex every
year, for every strategy (`link_cost_t += L.Opex(Year)/df`, and `L.Opex` sums over ALL
alive Link assets, `Existing_link` included — it's exempt from retirement, so it's
always in that sum). A never-built draw's LCOT is therefore a real, meaningful ratio —
the cost of relying on the existing cable alone — not an undefined 0/0. It computes to
exactly £0/MWh right now only because `Existing_link.OPEX()` is a hardcoded 0 placeholder
in `Model_Components.py` ("NEEDS VERIFICATION — legacy asset, opex recovery mechanism
unconfirmed"), predating this session — an honest reflection of that assumption, not a
fabricated "free transmission" reading. Once that placeholder gets a real sourced figure,
never-built LCOT moves off zero on its own; no exclusion logic needed either way.
`never_built_frac` is still reported below, as context for reading the curve, not a
reason to drop points.

## Re-plotting the LCOT target curve

Re-plot the LCOT target curve, without-wind — separate filename from `Results.py`'s
headline `target_curves_lcot.png`, so this doesn't touch or overwrite the headline
pipeline's own output.

Chart drops Flexible 1-Stage (Cost-Aware) (prints above keep it) — colour looked up BY
NAME so trimming the plotted list can't shift anyone else's colour.

## First-order stochastic dominance check

X FOSD Y iff `F_X(t) <= F_Y(t)` for every t (X's CDF never sits above Y's) — checked at
every unique NPV value across BOTH pooled samples (the only points either empirical CDF
can change), which is the exact, not approximate, condition, then a coarser grid is used
only for reporting WHERE the two curves cross to keep that readable.

## FOSD coarse grid for crossing report

Coarse (500-point) grid purely for reporting where the sign of `(Fx - Fy)` flips — the
dominance verdict above already used the exact (all-unique-values) grid, this is just for
a readable crossing report.

## Value of flexibility and regret tables

Both tables condition on DFES scenario (EE/FB/HT/HE) — the discrete "state of the
world" — and average OVER the within-scenario Monte Carlo noise (capex draw, weather,
price/demand/background GBM shocks) to get each strategy's scenario-conditional mean
NPV. That scenario-mean is the natural common basis for both: value-of-flexibility asks
"how much does Flexible 1-Stage beat the best rigid choice IN this scenario", regret asks
"how far below the best ANY strategy achieves IN this scenario" — both are per-scenario
comparisons, not per-draw ones.

## Plot trimming note

All three charts below drop Flexible 1-Stage (Cost-Aware) (prints/tables above keep it,
including the FOSD section and the VoF/regret tables themselves — only the actual bars
are trimmed). Bar offsets are computed generically from `len(...PLOT_STRATEGIES)` so
removing one series re-centers the remaining bars instead of leaving a gap or shifting
colours.

## Regret per scenario chart baseline

Regret per scenario, without Stage1/2 wind (standard). best-achievable (the regret
BASELINE) still uses the FULL `REGRET_STRATEGIES` set including Flexible 1-Stage
(Cost-Aware) (computed earlier, unchanged) — only the bars drawn here are trimmed, so
removing it from the chart can't silently change what "best-achievable" meant for the
strategies still shown.

## Max regret summary chart note

Max regret summary — the headline robustness number, without Stage1/2 wind. `maxregret`
(computed earlier) still holds Cost-Aware's own value — only the bars/xticks below are
trimmed.
