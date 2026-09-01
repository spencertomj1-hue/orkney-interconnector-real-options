"""See docs/notes/Debugging/mc_scenario_breakdown.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
import Model.System_Model as M
from Model.System_Model import Strategies_2, Strategies_Flex, Scenarios, Run_Strategy

ALL_STRATEGIES = {**Strategies_2, **Strategies_Flex}
weights = M.SCENARIO_WEIGHTS["Equal"]
scen_names = list(weights.keys())
scen_probs = list(weights.values())
n = 2000

rng = np.random.default_rng(42)
store = {sname: np.empty(n) for sname in ALL_STRATEGIES}
rule_log_store = {sname: {} for sname in Strategies_Flex}
draw_scenario = np.empty(n, dtype=object)

for i in range(n):
    capex_mult = rng.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA)
    scenario = rng.choice(scen_names, p=scen_probs)
    wx_seq = rng.choice(M.WEATHER_YEARS, size=len(M.YEARS))
    draw_scenario[i] = scenario
    demand = Scenarios[scenario]

    for sname, factory in ALL_STRATEGIES.items():
        opts = factory(capex_mult)
        result = Run_Strategy((sname, opts), demand, scenario, wx_seq)
        store[sname][i] = result[3]
        if sname in rule_log_store:
            for rname, info in result[5].items():
                rule_log_store[sname].setdefault(rname, []).append(info)

    if (i + 1) % 500 == 0:
        print(f"  {i + 1}/{n}")

print(f"\n=== Extra Link (Flexible 1-Stage strategy): never-fired %, overall and by DFES scenario ===")
extra_link_log = rule_log_store["Flexible 1-Stage"]["Extra Link"]
overall_never = 1 - sum(info["fired"] for info in extra_link_log) / n
print(f"Overall: {overall_never:.1%} never-fired ({n - sum(info['fired'] for info in extra_link_log)}/{n} draws)")
print(f"{'Scenario':<24}{'n_draws':>9}{'fired':>8}{'never-fired %':>15}")
for scen in scen_names:
    idx = [i for i in range(n) if draw_scenario[i] == scen]
    fired_count = sum(extra_link_log[i]["fired"] for i in idx)
    never_pct = 1 - fired_count / len(idx) if idx else float("nan")
    print(f"{scen:<24}{len(idx):>9}{fired_count:>8}{never_pct:>15.1%}")

# see docs/notes/Debugging/mc_scenario_breakdown.md#enpv-when-extra-link-fires-vs-when-it-doesnt
flex_npv = store["Flexible 1-Stage"]
fired_idx = [i for i in range(n) if extra_link_log[i]["fired"]]
never_idx = [i for i in range(n) if not extra_link_log[i]["fired"]]
if fired_idx and never_idx:
    print(f"\nFlexible 1-Stage NPV when Extra Link fires (N={len(fired_idx)}): "
          f"mean £{flex_npv[fired_idx].mean()/1e6:.2f}m")
    print(f"Flexible 1-Stage NPV when Extra Link never fires (N={len(never_idx)}): "
          f"mean £{flex_npv[never_idx].mean()/1e6:.2f}m")
else:
    print(f"\nCannot compare -- fired_idx={len(fired_idx)}, never_idx={len(never_idx)} "
          f"(one group is empty)")

print(f"\n=== Main Link (Flexible 1-Stage strategy): decision-year distribution ===")
main_link_log = rule_log_store["Flexible 1-Stage"]["Main Link"]
fired_years = [info["decision_year"] for info in main_link_log if info["fired"]]
never_frac = 1 - len(fired_years) / n
print(f"Never-fired: {never_frac:.1%} ({n - len(fired_years)}/{n} draws)")
if fired_years:
    print(f"Decision year: mean={np.mean(fired_years):.2f}, sd={np.std(fired_years):.2f}, "
          f"min={min(fired_years)}, max={max(fired_years)}")
    lo, hi = min(fired_years), max(fired_years)
    print(f"\nHistogram (decision year: count):")
    for yr in range(lo, hi + 1):
        c = fired_years.count(yr)
        if c:
            print(f"  {yr}: {'#' * (c // 10 or (1 if c else 0))} ({c})")
else:
    print("Main Link never fired in any draw.")

print(f"\n=== Headline Flexible 1-Stage ENPV vs best rigid (paired), Equal weighting ===")
rigid_enpv = {s: store[s].mean() for s in Strategies_2}
best_rigid_name = max(rigid_enpv, key=rigid_enpv.get)
best_rigid_draws = store[best_rigid_name]
d_enpv = flex_npv - best_rigid_draws
print(f"Best rigid strategy: {best_rigid_name} (ENPV £{rigid_enpv[best_rigid_name]/1e6:.2f}m)")
print(f"Flexible 1-Stage ENPV: £{flex_npv.mean()/1e6:.2f}m")
print(f"Paired dNPV (Flexible 1-Stage - best rigid): mean £{d_enpv.mean()/1e6:.2f}m, "
      f"sd £{d_enpv.std()/1e6:.2f}m, P5 £{np.percentile(d_enpv, 5)/1e6:.2f}m, "
      f"P95 £{np.percentile(d_enpv, 95)/1e6:.2f}m")

print(f"\n=== Collapse-flag check (fires 100% at same year) ===")
for sname in Strategies_Flex:
    for rname, infos in rule_log_store[sname].items():
        fy = [info["decision_year"] for info in infos if info["fired"]]
        never = 1 - len(fy) / n
        sd_y = float(np.std(fy)) if fy else float("nan")
        flag = never == 0.0 and sd_y == 0.0
        print(f"{sname:<24}{rname:<14} never-fired={never:>6.1%}  sd={sd_y:>6.2f}  "
              f"{'FLAG: collapsed to fixed schedule' if flag else ''}")
