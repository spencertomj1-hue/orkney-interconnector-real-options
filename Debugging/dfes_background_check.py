"""See docs/notes/Debugging/dfes_background_check.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
from Inputs.Data_Processing.Generation.DFES_Background import BACKGROUND

print("=== DFES background: year-on-year behaviour, per scenario per technology ===")
print(f"{'Scenario':<22}{'Tech':<8}{'ever decreases?':>16}{'min_incr':>11}{'max_incr':>11}"
      f"{'level[2026]':>13}{'level[2051]':>13}")
any_decrease = False
for scen, df in BACKGROUND.items():
    for tech in df.columns:
        series = df[tech].values
        yoy = np.diff(series)
        n_decreases = int((yoy < -1e-9).sum())
        if n_decreases > 0:
            any_decrease = True
        print(f"{scen:<22}{tech:<8}{str(n_decreases > 0):>16}{yoy.min():>11.3f}{yoy.max():>11.3f}"
              f"{series[0]:>13.2f}{series[-1]:>13.2f}")

print(f"\nAny scenario/technology series ever decreases year-on-year: {any_decrease}")
print("\n=== VERDICT ===")
if not any_decrease:
    print("DFES background is CUMULATIVE (monotonically non-decreasing in every scenario and "
          "every technology -- zero decreases across 4 scenarios x 3 technologies x 25 "
          "year-on-year transitions). It is NOT net-of-retirement capacity.")
    print("This is not a wind-specific artefact of DFES_Gen.py's WIND_OPERATIONAL clipping: "
          "Marine and PV pass through unmodified from the raw DFES CSV and are equally "
          "monotonic, so the underlying published DFES figures themselves never decrease.")
    print("\nSTOP: the STEP 1 design (walk on the increment, no separate retirement logic, "
          "because retirement is assumed already embedded in DFES's net figure) assumes NET "
          "capacity. That assumption does not hold here -- proceeding with STEP 1 as designed "
          "would silently double-omit retirement (DFES doesn't remove it, and the walk design "
          "doesn't add it either).")
else:
    print("DFES background is NET capacity (retirement already embedded) -- STEP 1 as designed "
          "can proceed.")
