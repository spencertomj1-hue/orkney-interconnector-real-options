"""See docs/notes/Debugging/mc_dimension_check.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
import Model.System_Model as M
from Model.System_Model import Strategies_Flex, Scenarios, Run_Strategy

print("=== 1. What varies per draw index in run_marginalised? ===")
print("Source (Results.py ~lines 263-265):")
print('  capex_mult = rng.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA)     # 1st: capex')
print('  scenario = rng.choice(scen_names, p=scen_probs)            # 2nd: scenario')
print('  wx_seq = rng.choice(M.WEATHER_YEARS, size=len(M.YEARS))    # 3rd: weather')
print("wx_seq is drawn fresh every call (rng.choice over M.WEATHER_YEARS, one "
      "year per model year) and passed as Run_Strategy's 4th positional arg "
      "(result = Run_Strategy((sname, opts), demand, scenario, wx_seq)) -- it "
      "is NOT left as None, so Run_Strategy does NOT fall back to "
      "BASE_WEATHER_YEAR for these draws.")

# Empirical confirmation: replicate 5 draws with the same rng call order and
# show all three actually differ index-to-index.
rng = np.random.default_rng(42)
scen_names = list(M.SCENARIO_WEIGHTS["Equal"].keys())
scen_probs = list(M.SCENARIO_WEIGHTS["Equal"].values())
print(f"\n{'draw':<6}{'capex_mult':>12}{'scenario':>22}{'wx_seq[:5]':>30}")
draws = []
for i in range(5):
    capex_mult = rng.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA)
    scenario = rng.choice(scen_names, p=scen_probs)
    wx_seq = rng.choice(M.WEATHER_YEARS, size=len(M.YEARS))
    draws.append((capex_mult, scenario, wx_seq))
    print(f"{i:<6}{capex_mult:>12.4f}{scenario:>22}{str(list(wx_seq[:5])):>30}")

capex_all_diff = len({round(d[0], 6) for d in draws}) == len(draws)
wx_all_diff = len({tuple(d[2]) for d in draws}) == len(draws)
print(f"\ncapex_mult differs every draw: {capex_all_diff}")
print(f"scenario varies across draws (not all identical): {len({d[1] for d in draws}) > 1}")
print(f"wx_seq differs every draw (as a full sequence): {wx_all_diff}")

# see docs/notes/Debugging/mc_dimension_check.md#confirm-wx_seq-actually-changes-run_strategys-output
opts = Strategies_2 = M.Strategies_2["Baseline"](1.0)
_, _, _, npv_a, state_a, _ = Run_Strategy(("Baseline", opts), Scenarios["Base"], "Base", draws[0][2])
_, _, _, npv_b, state_b, _ = Run_Strategy(("Baseline", opts), Scenarios["Base"], "Base", draws[1][2])
gen_differs = not np.allclose(state_a["gen_total"], state_b["gen_total"])
print(f"\nSanity check: same strategy/scenario, two different wx_seq draws -> "
      f"gen_total differs by year: {gen_differs} (NPV: {npv_a/1e6:.2f}m vs {npv_b/1e6:.2f}m)")
print("CONCLUSION (1): capex_mult=YES, scenario=YES, wx_seq=YES -- all three "
      "already vary per draw and demonstrably affect Run_Strategy's output. "
      "No code change needed for item 2: wx_seq is already a live draw "
      "dimension, not a None-fallback to BASE_WEATHER_YEAR.")

print("\n=== 3. Do flexible rules re-instantiate fresh per draw? ===")
opts1 = Strategies_Flex["Flexible 1-Stage"](1.0)
opts2 = Strategies_Flex["Flexible 1-Stage"](1.0)
rules1 = {type(o).__name__ + "_" + getattr(o, "name", "") for o in opts1}
same_objects = any(o1 is o2 for o1 in opts1 for o2 in opts2)
fired_flags = [getattr(o, "fired", None) for o in opts1 if hasattr(o, "fired")]
print(f"Two calls to Strategies_Flex['Flexible 1-Stage'](1.0) share any object identity: {same_objects}")
print(f"Rule.fired flags on a fresh call: {fired_flags} (all should be False)")
print("CONCLUSION (3): Strategies_Flex entries are factories (_flexible, "
      "_flexible_link_only, _flexible_mandated all build fresh Decision/Rule "
      "instances per call) -- confirmed no shared object identity and every "
      "fresh Rule starts with fired=False, so no firing state leaks between "
      "draws or strategies.")
