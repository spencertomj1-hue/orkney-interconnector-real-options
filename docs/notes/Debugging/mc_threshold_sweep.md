# mc_threshold_sweep.py — notes

Background pulled out of `Debugging/mc_threshold_sweep.py` to keep the
script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, modifies no
model file (thresholds are rebound on the live `Decision_Rules` module at
runtime and restored after each sweep).

UPDATED to match current call signatures -- this script originally predated
two changes: (a) `Results.py`'s `run_marginalised` now draws a 4th per-draw
quantity (`capex_estimate_seq`, for the cost-aware rule) which shifts the
rng stream for every draw after the first, and (b) `Run_Strategy`'s
signature grew `capex_mult`/`capex_estimate_seq` parameters.
`run_flexible_mc` below now draws and passes all 4 quantities, matching
`Results.py` exactly.

SWEEPS 2 and 3 (Extra Link, Stage 2 Wind) are gated behind a check that the
target strategy's `rule_log` actually contains those rule names -- headline
"Flexible 1-Stage" was reconfigured (Extra Link removed entirely, Stage 2
Wind demoted from a Rule to a fixed Decision) and no longer has either, so
those rules' entries in `Run_Strategy`'s `rule_log` simply don't exist for
"Flexible 1-Stage" any more. Before this gate, `run_flexible_mc`'s
`rule_log` dict pre-seeded empty lists for both names regardless, so
`summarize()` silently reported 100% never-fired for rules that were never
being evaluated at all. The gate below gives a clear message instead of a
misleading number.

See MAIN LINK RE-SWEEP section at the bottom for the current calibration
(`Decision_Rules.MAIN_LINK_HEADROOM_THRESHOLD`, re-tuned to 115 and
validated across three seeds after the reconfiguration silently invalidated
the original 100).

## Sweep 2: Extra Link gating

Gated: `TARGET_STRATEGY` ("Flexible 1-Stage") no longer has an Extra Link
rule at all (removed in the headline reconfiguration). Point this at a
strategy that still does (e.g. "Flexible - Mandated Link") to get a real
sweep; skipped here with an explicit message rather than silently reporting
a meaningless 100% never-fired.

## Sweep 3: Stage 2 Wind gating

Gated the same way: `TARGET_STRATEGY` has Stage 2 Wind as a fixed Decision,
not a Rule, so it has no entry in `rule_log` either.

## Sweep 4: Main Link threshold vs ENPV

115 was tuned to maximise decision-year sd/never-fire discrimination
(SWEEP 1 / MAIN LINK RE-SWEEP above), not ENPV -- those are different
objectives, and a threshold chosen for the first isn't necessarily good for
the second. This targets `TARGET_STRATEGY` ("Flexible 1-Stage"), which is
now the gated strategy (Stage1/Stage2 wind contingent on Main Link via
`prereq="NewLink"` -- see `System_Model._flexible`), so firing "late" no
longer stranps wind behind a link that isn't there; it just delays both
together. NOT applied to `Decision_Rules.py` -- print only, per
instruction.

## Supplementary sweep: lower and negative threshold range

Lower/negative range, where gating actually moved the transition to. Not
requested, but reporting only the 60-140 result above would misrepresent
the sweep as complete when it isn't -- flagging the real range rather than
silently only answering the literal ask.
