"""See docs/notes/Debugging/retirement_decomp.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import Model.Model_Components as MC
import Model.System_Model as M
from Model.System_Model import Strategies_2, Scenarios, Run_Strategy


def discounted_capex(Options, rate):
    total = 0.0
    for d in Options:
        by = d.BuildYear()
        if by is None:
            continue
        total += d.Asset().Capex() / (1 + rate) ** (by - 2019)
    return total


def discounted_residual(Options, rate, end_year, lifetimes):
    df_end = (1 + rate) ** (end_year - 2019)
    total = 0.0
    for d in Options:
        by = d.BuildYear()
        if by is None:
            continue
        life = lifetimes[d.Asset().Classification()]
        used = end_year - by + 1
        remaining = max(0.0, (life - used) / life)
        total += d.Asset().Capex() * remaining / df_end
    return total


def decompose(strategy_name, scenario_name):
    opts = Strategies_2[strategy_name](1.0)
    total_cost_t, pv_energy, total_curtail, npv, _, _ = Run_Strategy(
        (strategy_name, opts), Scenarios[scenario_name], scenario_name)
    capex = discounted_capex(opts, M.RATE)
    residual = discounted_residual(opts, M.RATE, M.END_YEAR, MC.LIFETIMES)
    opex = total_cost_t - capex + residual
    pv_revenue = npv + total_cost_t
    return {
        "pv_revenue": pv_revenue,
        "capex": capex,
        "opex": opex,
        "residual_credit": residual,
        "total_cost": total_cost_t,
        "pv_energy": pv_energy,
        "total_curtail": total_curtail,
        "npv": npv,
    }


STRATEGY = "Baseline"
SCENARIO = "Base"

_orig_gen_life = MC.LIFETIMES["Generation"]
MC.LIFETIMES["Generation"] = 999   # diagnostic toggle: disable generation retirement for the "before" run only
before = decompose(STRATEGY, SCENARIO)
MC.LIFETIMES["Generation"] = _orig_gen_life   # restore immediately

after = decompose(STRATEGY, SCENARIO)

rows = [
    ("pv_revenue, £m",     before["pv_revenue"]     / 1e6, after["pv_revenue"]     / 1e6),
    ("capex, £m",          before["capex"]          / 1e6, after["capex"]          / 1e6),
    ("opex, £m",           before["opex"]           / 1e6, after["opex"]           / 1e6),
    ("residual credit, £m", before["residual_credit"] / 1e6, after["residual_credit"] / 1e6),
    ("total_cost, £m",     before["total_cost"]     / 1e6, after["total_cost"]     / 1e6),
    ("pv_energy, GWh",     before["pv_energy"],             after["pv_energy"]),
    ("total_curtail, GWh", before["total_curtail"],         after["total_curtail"]),
    ("npv, £m",            before["npv"]            / 1e6, after["npv"]            / 1e6),
]

print(f"=== {STRATEGY} under {SCENARIO}: retirement decomposition ===")
print(f"{'Component':<20}{'before':>12}{'after':>12}{'delta':>12}")
for label, b, a in rows:
    print(f"{label:<20}{b:>12.2f}{a:>12.2f}{(a - b):>12.2f}")

d_revenue = (after["pv_revenue"] - before["pv_revenue"]) / 1e6
d_capex = (after["capex"] - before["capex"]) / 1e6
d_opex = (after["opex"] - before["opex"]) / 1e6
d_residual = (after["residual_credit"] - before["residual_credit"]) / 1e6
d_npv = (after["npv"] - before["npv"]) / 1e6

print(f"\ncheck: d_revenue - d_capex - d_opex + d_residual = "
      f"{d_revenue - d_capex - d_opex + d_residual:.2f} (should equal d_npv = {d_npv:.2f})")

cost_side = -d_capex - d_opex + d_residual   # net effect of cost-side terms on NPV
if abs(d_revenue) > abs(cost_side) * 2:
    verdict = "revenue loss from retired generation dominates the NPV drop; cost-side terms are minor"
elif abs(cost_side) > abs(d_revenue) * 2:
    verdict = "cost-side terms (opex savings / residual shrinkage) dominate the NPV drop, not revenue loss"
else:
    verdict = "revenue loss and cost-side terms are both materially contributing, neither dominates cleanly"
print(f"\nVERDICT: {verdict}")
