# threshold_sweep.py — notes

Background pulled out of `Debugging/threshold_sweep.py` to keep the script
itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, modifies no
existing file (thresholds are rebound on the live `Decision_Rules` module
at runtime and restored at the end, not edited on disk).

Two questions, headline "Flexible 1-Stage" strategy, Base scenario:

1. Does any Extra Link threshold make that rule fire only when it ADDS
   value (or correctly never fire), or is it value-destroying everywhere?
2. Is the Main Link 2030 fire year robust across a band of thresholds, or
   knife-edge (in which case the deterministic Base result isn't
   trustworthy and the real answer is in the Monte Carlo)?

Rule factories in `Decision_Rules.py` read the threshold module constants
(`EXTRA_LINK_HOURS_THRESHOLD` etc.) as globals at Rule-construction time,
so rebinding `DR.EXTRA_LINK_HOURS_THRESHOLD` before calling the
`Strategies_Flex` factory (which builds fresh Rule instances every call)
is enough to sweep -- no need to touch `Decision_Rules.py` itself.
