"""See docs/notes/Debugging/headline_flexible_report.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
import Model.System_Model as M
from Model.System_Model import Strategies_2, Strategies_Flex, Scenarios, Run_Strategy

ALL_STRATEGIES = {**Strategies_2, "Flexible 1-Stage": Strategies_Flex["Flexible 1-Stage"]}


def run_marginalised(weights, n=2000, seed=42):
    rng = np.random.default_rng(seed)
    scen_names = list(weights.keys())
    scen_probs = list(weights.values())
    store = {sname: np.empty(n) for sname in ALL_STRATEGIES}
    rule_log = []
    for i in range(n):
        capex_mult = rng.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA)
        scenario = rng.choice(scen_names, p=scen_probs)
        wx_seq = rng.choice(M.WEATHER_YEARS, size=len(M.YEARS))
        demand = Scenarios[scenario]
        for sname, factory in ALL_STRATEGIES.items():
            opts = factory(capex_mult)
            result = Run_Strategy((sname, opts), demand, scenario, wx_seq)
            store[sname][i] = result[3]
            if sname == "Flexible 1-Stage":
                rule_log.append(result[5]["Main Link"])
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{n}")
    return store, rule_log


print("=== Full MC, Equal weighting, n=2000, curtailment-costed (£{}/MWh) ===".format(M.CONSTRAINT_COST))
store, rule_log = run_marginalised(M.SCENARIO_WEIGHTS["Equal"])

enpvs = {sname: vals.mean() for sname, vals in store.items()}
best_rigid_name = max((s for s in Strategies_2), key=lambda s: enpvs[s])
best_rigid_draws = store[best_rigid_name]
flex_npv = store["Flexible 1-Stage"]
d_enpv = flex_npv - best_rigid_draws

print(f"\n{'Strategy':<18}{'ENPV_£m':>10}{'P5':>9}{'P50':>9}{'P95':>9}")
for sname, vals in store.items():
    v = vals / 1e6
    print(f"{sname:<18}{v.mean():>10.0f}{np.percentile(v,5):>9.0f}{np.percentile(v,50):>9.0f}{np.percentile(v,95):>9.0f}")

print(f"\nBest rigid strategy: {best_rigid_name} (ENPV £{enpvs[best_rigid_name]/1e6:.1f}m)")
print(f"Headline Flexible ENPV: £{enpvs['Flexible 1-Stage']/1e6:.1f}m")
print(f"Paired dNPV (Flexible - best rigid): mean £{d_enpv.mean()/1e6:.2f}m, "
      f"sd £{d_enpv.std()/1e6:.2f}m, P5 £{np.percentile(d_enpv,5)/1e6:.2f}m, "
      f"P95 £{np.percentile(d_enpv,95)/1e6:.2f}m")
sign = "POSITIVE" if d_enpv.mean() > 0 else ("NEAR-ZERO" if abs(d_enpv.mean()/1e6) < 5 else "NEGATIVE")
print(f"Value of flexibility: {sign}")

print(f"\n=== Main Link firing stats in headline Flexible (Equal weighting, N=2000) ===")
fired_years = [info["decision_year"] for info in rule_log if info["fired"]]
never_pct = 1 - len(fired_years) / len(rule_log)
print(f"Never-fired: {never_pct:.1%} ({len(rule_log) - len(fired_years)}/{len(rule_log)})")
if fired_years:
    print(f"Decision year: mean={np.mean(fired_years):.2f}, sd={np.std(fired_years):.2f}, "
          f"min={min(fired_years)}, max={max(fired_years)}")
    lo, hi = min(fired_years), max(fired_years)
    print("Histogram (decision year: count):")
    for yr in range(lo, hi + 1):
        c = fired_years.count(yr)
        if c:
            print(f"  {yr}: {'#' * max(1, c // 10)} ({c})")

print(f"\n=== Main Link firing stats under NetZero_Tilt weighting (N=2000) ===")
store_tilt, rule_log_tilt = run_marginalised(M.SCENARIO_WEIGHTS["NetZero_Tilt"])
fired_years_tilt = [info["decision_year"] for info in rule_log_tilt if info["fired"]]
never_pct_tilt = 1 - len(fired_years_tilt) / len(rule_log_tilt)
print(f"Never-fired: {never_pct_tilt:.1%} ({len(rule_log_tilt) - len(fired_years_tilt)}/{len(rule_log_tilt)})")
if fired_years_tilt:
    print(f"Decision year: mean={np.mean(fired_years_tilt):.2f}, sd={np.std(fired_years_tilt):.2f}, "
          f"min={min(fired_years_tilt)}, max={max(fired_years_tilt)}")

print(f"\nEqual weighting never-fired: {never_pct:.1%}, sd={np.std(fired_years) if fired_years else float('nan'):.2f}")
print(f"NetZero_Tilt never-fired:    {never_pct_tilt:.1%}, sd={np.std(fired_years_tilt) if fired_years_tilt else float('nan'):.2f}")
shift = abs(never_pct - never_pct_tilt) > 0.05
print(f"Discriminating behaviour {'SHIFTS' if shift else 'IS STABLE'} with scenario weighting.")
