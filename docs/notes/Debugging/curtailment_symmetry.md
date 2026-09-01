# curtailment_symmetry.py — notes

Background and rationale pulled out of `Debugging/curtailment_symmetry.py` to keep the script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, changes nothing.

Verifies the curtailment-cost term (`total_cost_t += spilled_GWh * 1000 * CONSTRAINT_COST / df`) is symmetric between strategies -- i.e. a link-builder is credited for relieved curtailment by exactly as much as Do Nothing is debited for the curtailment it incurs, with nothing charged to one strategy that isn't charged to the other on the same physical/pricing basis.

Duplicates `Run_Strategy`'s loop (same approach as `background_fix_report.py` / `retirement_decomp.py`) instrumented to separately track capex/opex/residual/curtailment-cost instead of only their net `total_cost_t`, plus per-year spilled GWh and per-year discounted curtailment £ for both strategies.
