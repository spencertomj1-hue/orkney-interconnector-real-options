# Nested_MC_By_Scenario_BACKUP.py — notes

Background and rationale pulled out of `Reporting/ScenarioDiscovery/Extra/Nested_MC_By_Scenario_BACKUP.py` to
keep the script itself short.

## Overview

DFES-scenario-dimension diagnostic, split out of `Results.py`.

Note: this file does NOT do "scenario discovery" in the Robust Decision Making / Bryant-Lempert sense
(running PRIM or similar over an ensemble to find which combinations of uncertain inputs predict a bad
outcome). It's the nested-Monte-Carlo-by-scenario diagnostic that answers a narrower question: does capex
uncertainty or DFES scenario choice dominate the ENPV spread? The weighting-sensitivity comparison (Equal vs
`NetZero_Tilt`) that used to live here moved to `Sensitivities.py`, since it's a sensitivity sweep like every
other section there, not a scenario-dimension diagnostic.

## STRATEGY_COLOR: consistency across figures

Same strategy colors as `Results.py`'s absolute-ENPV bar chart and `Sensitivities.py`'s target-strategy
palette — keep strategy = color consistent across every figure in the report, not just within this file.

## Nested Monte Carlo: design rationale

Same capex machinery, kept disaggregated by scenario (not averaged) to show whether capex or scenario choice
dominates the spread. Uses the deterministic per-scenario demand path (`Scenarios[scen]`, not a GBM-noised
draw) and only capex is randomised — a different, smaller experiment from the headline marginalised MC, so it
draws its own fresh capex-only sample rather than reading anything from `Results.py`'s MC cache.

## Chart: interpreting bar height vs error bars

Magnitude across two categorical dimensions (strategy x scenario) -> grouped bars, one group per scenario,
error bars = capex-only StdDev. Whether capex or scenario choice dominates the spread reads directly off
this: bars moving MORE between groups (scenarios) than their own error bars are tall means scenario choice
dominates; the reverse means capex uncertainty dominates.
