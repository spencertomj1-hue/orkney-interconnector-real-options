# repd_vintages_report.py — notes

Background pulled out of `Debugging/repd_vintages_report.py` to keep the
script itself short.

## Overview

Report script for the REPD-derived existing-wind-vintage change.

Not a throwaway -- reports on the real implementation change made to
`Model_Components.py` (`EXISTING_FLEET` now built from REPD commission
years instead of a single 2010 placeholder). Prints the extracted fleet,
the REPD-vs-existing capacity cross-check, the resulting retirement
schedule, and reruns the five `Strategies_2` under Base comparing against
the old single-lump (2035/2040) commission-year baseline.

## Old single-lump fleet baseline

Old single-lump fleet: `Existing_Wind` at full 52.239 MW commissioned 2010
(retires 2035), `Existing_PV` commissioned 2015 (retires 2040) -- exactly
what `Model_Components.py` used before this REPD change.
