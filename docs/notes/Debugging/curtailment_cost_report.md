# curtailment_cost_report.py — notes

Background and rationale pulled out of `Debugging/curtailment_cost_report.py` to keep the script itself short.

## Overview

Report script for adding `CONSTRAINT_COST` to `System_Model.Run_Strategy`'s NPV objective. Not a throwaway -- reports on the real implementation change.

Resolves the open question from `do_nothing_check.py`: was Do Nothing's ENPV win in the full Monte Carlo driven by the missing curtailment-cost term, or by stochastic capex-overrun risk falling on Baseline (which pays for `NewLink`)? Reruns the marginalised MC with the new term in place, plus a `CONSTRAINT_COST=55/70` sensitivity band so the headline isn't hostage to the 62.5 midpoint.
