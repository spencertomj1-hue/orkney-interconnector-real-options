"""See docs/notes/Debugging/residual_check.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import Model.Model_Components as MC
import Model.System_Model as M
from Model.System_Model import Strategies_2
from Model.Model_Components import Decision

opts = Strategies_2["Baseline"](1.0)
stage1_decision = next(
    d for d in opts
    if isinstance(d, Decision) and type(d.Asset()).__name__ == "Stage1_Wind_Buildout")

asset = stage1_decision.Asset()
build_year = stage1_decision.BuildYear()
capex = asset.Capex()
classification = asset.Classification()

print(f"Asset: {type(asset).__name__}, BuildYear={build_year}, "
      f"Capex=£{capex:,.0f}, Classification={classification}")

# see docs/notes/Debugging/residual_check.md#replicating-the-residual-loops-arithmetic
life = MC.LIFETIMES[classification]
used = M.END_YEAR - build_year + 1
remaining = max(0.0, (life - used) / life)
df_end = (1 + M.RATE) ** (M.END_YEAR - 2019)
actual_credit_pv = capex * remaining / df_end

expected_remaining = 0.08
expected_credit_pv = expected_remaining * capex / (1 + M.RATE) ** 32

print(f"\n{'':<20}{'life':>8}{'used':>8}{'remaining':>12}{'credit_pv, £':>16}")
print(f"{'live code':<20}{life:>8}{used:>8}{remaining:>12.4f}{actual_credit_pv:>16,.2f}")
print(f"{'hand-derived':<20}{25:>8}{23:>8}{expected_remaining:>12.4f}{expected_credit_pv:>16,.2f}")

assert abs(remaining - expected_remaining) < 1e-9, \
    f"remaining={remaining} != expected {expected_remaining}"
assert abs(actual_credit_pv - expected_credit_pv) < 1e-6, \
    f"credit_pv={actual_credit_pv} != expected {expected_credit_pv}"
assert M.END_YEAR == 2051 and build_year == 2029 and life == 25, \
    "underlying constants have drifted from the assumptions this check hand-derived against"

print(f"\nVERDICT: live residual accounting credits "
      f"{remaining:.2f} x Capex (= £{actual_credit_pv:,.0f} at 2019 present value) "
      f"for a 2029-built generation asset, matching the hand-derived 0.08 x Capex exactly.")
