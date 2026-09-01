# do_nothing_check.py — notes

Background and rationale pulled out of `Debugging/do_nothing_check.py` to keep the script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, changes nothing.

Why does Do Nothing (£306m ENPV) beat every active strategy in the Monte Carlo? Specifically: does curtailed/spilled energy carry any cost in the NPV objective, or is it just un-earned revenue with no explicit penalty?

Traced directly from `System_Model.py` (grep confirms every place `total_curtail` appears): it is incremented at line ~262 (`total_curtail += (surplus - export).sum() / 1000`) and returned as `Run_Strategy`'s 3rd value, but never appears on the right-hand side of `total_cost_t` or `pv_revenue` anywhere in the function. `pv_revenue` only ever multiplies `delivered` (= local + export) by price -- curtailed energy (surplus - export) contributes to neither term. `npv = pv_revenue - total_cost_t`, so curtailment has zero direct effect on npv; it is diagnostic-only (also feeds the "curtail_frac" rule observable, which does not feed back into npv either, per the code's own comment at line ~281).

## Baseline vs Do Nothing: why check every scenario

The Holistic Transition decomposition above shows Baseline beating Do Nothing (£492m vs £322m) at nominal `capex_mult=1.0` -- the opposite of the £306m vs £248m Do-Nothing-wins result from the full Monte Carlo. Before writing a causal verdict, check whether that's scenario-specific: same comparison, `capex_mult=1.0`, across every scenario in `Scenarios`.
