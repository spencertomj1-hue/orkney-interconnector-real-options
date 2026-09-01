# dfes_background_check.py — notes

Background and rationale pulled out of `Debugging/dfes_background_check.py` to keep the script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase, changes nothing.

STEP 0 of the stochastic-background-buildout design: is `Inputs.Data_Processing.Generation.DFES_Background.BACKGROUND` net installed capacity (retirements already netted out -- series can flatten or decrease) or cumulative gross additions (monotonically non-decreasing, retirements not removed)? This determines whether a random walk on year-on-year increments can assume retirement is already embedded (net) or needs separate handling (cumulative).
