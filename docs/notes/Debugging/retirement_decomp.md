# retirement_decomp.py — notes

Background pulled out of `Debugging/retirement_decomp.py` to keep the
script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase.

Decomposes the Baseline strategy's NPV change (Base scenario) into
revenue / capex / opex / residual-value components, before vs after
generation retirement. Does not modify `System_Model.py` or
`Model_Components.py`.

`Run_Strategy` already returns `total_cost_t` (= capex + opex - residual)
and `npv` (= pv_revenue - total_cost_t) as a single bundle, not split out.
Rather than duplicating `Run_Strategy`'s ~100-line loop to instrument it,
this script recovers the split algebraically:

- capex and residual are recomputed directly from the strategy's Decision
  list using the exact same closed-form `Run_Strategy` uses internally
  (discounted `Capex()` at `BuildYear()` for capex; the same
  remaining-life formula at `END_YEAR` for residual) -- valid because
  Baseline is a rigid strategy (Decision-only, no Rule instances), so
  `fixed_decisions == Options` and there are no `fired_decisions` to
  account for.
- opex is then recovered as `total_cost_t - capex + residual` (an
  identity, not an approximation: `total_cost_t` is exactly
  `capex + opex - residual` by construction inside `Run_Strategy`).
- `pv_revenue` is recovered as `npv + total_cost_t` (again exact, from the
  definition `npv = pv_revenue - total_cost_t`).

"Before" = generation retirement disabled, by temporarily rebinding
`Model_Components.LIFETIMES["Generation"]` to 999 for that one run and
restoring it immediately after -- a diagnostic toggle in this process only,
not a change to the real modules. Note this toggle feeds BOTH the mid-life
capacity dropout (`Generation_Capacity._alive` / `existing_alive_mw`) AND
the residual-value formula (which also keys off
`LIFETIMES["Generation"]`), so the residual component below reflects "as if
generation had a 999-year life", not "25-year life but no dropout". That is
a real difference from the original pre-retirement codebase (which always
used the true 25-year life for residual) -- flagged in the printed output,
not silently smoothed over.
