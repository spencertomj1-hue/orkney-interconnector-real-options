"""See docs/notes/Debugging/curtailment_cost_report.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
import Model.System_Model as M
from Model.System_Model import Strategies_2, Scenarios, Run_Strategy


def run_marginalised(weights, seed=42, n=2000):
    rng = np.random.default_rng(seed)
    scen_names = list(weights.keys())
    scen_probs = list(weights.values())
    store = {sname: np.empty(n) for sname in Strategies_2}
    for i in range(n):
        capex_mult = rng.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA)
        scenario = rng.choice(scen_names, p=scen_probs)
        wx_seq = rng.choice(M.WEATHER_YEARS, size=len(M.YEARS))
        demand = Scenarios[scenario]
        for sname, factory in Strategies_2.items():
            opts = factory(capex_mult)
            result = Run_Strategy((sname, opts), demand, scenario, wx_seq)
            store[sname][i] = result[3]
    return store


print("=== (a) Do Nothing vs Baseline, capex_mult=1.0, BASE_WEATHER_YEAR, WITH curtailment cost ===")
print(f"CONSTRAINT_COST = £{M.CONSTRAINT_COST}/MWh")
print(f"{'Scenario':<22}{'NPV DoNothing':>16}{'NPV Baseline':>15}{'Baseline wins?':>16}")
for scen in Scenarios:
    opts_dn = Strategies_2["Do Nothing"](1.0)
    opts_bl = Strategies_2["Baseline"](1.0)
    _, _, _, n_dn, _, _ = Run_Strategy(("Do Nothing", opts_dn), Scenarios[scen], scen)
    _, _, _, n_bl, _, _ = Run_Strategy(("Baseline", opts_bl), Scenarios[scen], scen)
    print(f"{scen:<22}{n_dn/1e6:>16.1f}{n_bl/1e6:>15.1f}{str(n_bl > n_dn):>16}")

print("\n=== (b) Full Monte Carlo, Equal weighting, n=2000, at CONSTRAINT_COST=55/62.5/70 ===")
_default_cc = M.CONSTRAINT_COST
for cc in (55, 62.5, 70):
    M.CONSTRAINT_COST = cc
    store = run_marginalised(M.SCENARIO_WEIGHTS["Equal"])
    print(f"\n--- CONSTRAINT_COST = £{cc}/MWh ---")
    print(f"{'Strategy':<18}{'ENPV_£m':>10}{'P5':>9}{'P50':>9}{'P95':>9}")
    enpvs = {}
    for sname, vals in store.items():
        v = vals / 1e6
        enpvs[sname] = v.mean()
        print(f"{sname:<18}{v.mean():>10.0f}{np.percentile(v,5):>9.0f}"
              f"{np.percentile(v,50):>9.0f}{np.percentile(v,95):>9.0f}")
    ranked = sorted(enpvs, key=lambda s: -enpvs[s])
    print(f"Ranking: {ranked}")
    print(f"Do Nothing {'STILL WINS' if enpvs['Do Nothing'] == max(enpvs.values()) else 'NO LONGER WINS'} "
          f"on ENPV at this constraint cost.")
M.CONSTRAINT_COST = _default_cc

print("\n=== VERDICT ===")
print("See printed ranking above at CONSTRAINT_COST=62.5 (the sourced midpoint) for the "
      "plain answer to which factor (missing curtailment term vs capex-overrun risk) drove "
      "the original Do-Nothing-wins result.")
