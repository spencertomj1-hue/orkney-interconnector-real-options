# falling_behind_trace.py — notes

Background and rationale pulled out of `Debugging/falling_behind_trace.py` to keep the script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, changes nothing.

Traces why the permanent-nameplate-subtraction fix moved Do Nothing's NPV DOWN under Falling Behind while moving it UP under the three growth scenarios. Duplicates `Run_Strategy`'s loop twice per scenario (old life-gated `existing_alive_mw(Year)` subtraction vs new permanent `EXISTING_FLEET_NAMEPLATE` subtraction), tracking per-year background wind entering dispatch, the raw subtraction inputs, and the resulting generation/delivered/curtailment/cost.

## run_traced: subtraction parameter

`subtraction`: `'old'` (life-gated `existing_alive_mw(Year)`) or `'new'` (permanent `EXISTING_FLEET_NAMEPLATE`). Everything else identical to the real, current `Run_Strategy`.
