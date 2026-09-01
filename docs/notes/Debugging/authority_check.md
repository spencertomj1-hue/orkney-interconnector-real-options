# authority_check.py — notes

Background and rationale pulled out of `Debugging/authority_check.py` to keep the script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, changes nothing.

Checks whether `REPD_Existing_Wind_Vintages.py`'s "Planning Authority contains Orkney" substring match drops any real Orkney sites -- i.e. whether the 39.2 MW REPD operational total is real or a match artefact.

NOTE ON `header=2`: verified directly below (see the printed check) that `header=2` is WRONG for this workbook -- it treats a data row as the header, producing garbage column names (`'AA110'`, `2`, a datetime, ...) and one fewer row. The rest of the project (`REPD_Wind.py`, `REPD_Existing_Wind_Vintages.py`) uses the default `header=0`, which is the real header row. This script uses `header=0` to match, and flags the `header=2` mismatch rather than silently using a value that would break every downstream column lookup.

## Geographic cross-check: Orkney bounding box rationale

OSGB36 National Grid bounding box for Orkney (HY/ND grid squares). First attempt used northing >= 950,000 and pulled in ~16 Caithness (Highland council) wind farms from across the Pentland Firth -- checked their actual coordinates directly (Causeymire, Forss, Halsary, etc. all sit at northing 950,000-973,000). The real Orkney name-matched sites all sit at northing >= 988,155, a clean ~15km gap (the Firth itself) with nothing in between -- so the box below uses 980,000 as the cut, safely inside that gap and independent of the exact name-matched min.
