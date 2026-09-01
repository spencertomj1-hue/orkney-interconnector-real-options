# spurness_2019_check.py — notes

Background pulled out of `Debugging/spurness_2019_check.py` to keep the
script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, changes
nothing.

Was Spurness Wind Farm (Orkney, 11.0 MW, Wind Onshore, operational since
2004, currently "Decommissioned" in REPD) still operational as of the 2019
base year? Reads REPD with `header=0` (the project's real convention --
confirmed in `authority_check.py` that `header=2` produces garbage columns
for this workbook), sheet `'REPD'`, same col-lookup convention as
`REPD_Wind.py`.

## Corroborating signal: the Repowering project

Corroborating signal: the "Repowering" project at the same site (different
REPD entry) went operational in Dec 2012 -- repowering projects normally
retire the old turbines at or shortly after the new ones commission, since
running both simultaneously at one small site is atypical.
