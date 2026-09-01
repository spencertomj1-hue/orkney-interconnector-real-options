# spurness_fix_report.py — notes

Background pulled out of `Debugging/spurness_fix_report.py` to keep the
script itself short.

## Overview

Report script for removing the 52.239/39.2 rescale from the existing-wind
vintages (`spurness_2019_check.py` established Spurness was not
operational in 2019, so the gap is real decommissioning, not a
rescale-worthy disagreement).

Not a throwaway -- reports on the real `Model_Components.py` change.
Prints the final vintage schedule, new fleet total, retirement schedule,
and reruns `Strategies_2` under Base comparing against the previous
even-rescaled (to 52.239 MW) version.

## Previous even-rescaled version

Previous version: same 8 REPD vintages, but each rescaled by 52.239/39.2
so they summed back to the regional-stats total -- reconstructed here from
the same CSV rows, not re-derived by hand.
