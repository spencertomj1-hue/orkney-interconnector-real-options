# headline_flexible_report.py — notes

Background and rationale pulled out of `Debugging/headline_flexible_report.py` to keep the script itself short.

## Overview

Report script for the reconfigured headline Flexible 1-Stage strategy (Main Link only, threshold=100; Stage 2 Wind fixed; Extra Link removed). Not a throwaway -- reports on the real implementation change in `System_Model.py` / `Decision_Rules.py`.

Runs the definitive flexible-vs-rigid Monte Carlo against the curtailment-costed objective (`CONSTRAINT_COST` default from `System_Model.py`), Equal weighting, n=2000, paired draws -- same draw machinery as `Results.py`'s `run_marginalised`. Then re-checks Main Link's firing stats under `NetZero_Tilt` weighting to see if the discriminating threshold is scenario-weighting dependent.
