# background_fix_report.py — notes

Background and rationale pulled out of `Debugging/background_fix_report.py` to keep the script itself short.

## Overview

Report script for the existing-fleet double-count fix in `System_Model.py`'s DFES block. Not a throwaway -- reports on the real implementation change.

"Before" behaviour (life-gated `existing_alive_mw(Year)` subtraction) no longer exists in `System_Model.py`'s source, so it's reproduced here as a duplicate of `Run_Strategy`'s loop with ONLY that one line reverted -- same approach used in `retirement_decomp.py` for isolating a single computation without touching the real module. Everything else (curtailment cost, CFD/price mechanics, discounting) is identical to the real, fixed `Run_Strategy` because it's built from the same `System_Model` constants/objects.

## run_strategy_before_fix: what's reverted

Duplicate of `System_Model.Run_Strategy`, DFES block reverted to the old life-gated `existing_alive_mw(Year)` subtraction. Everything else unchanged from the real (fixed) function.
