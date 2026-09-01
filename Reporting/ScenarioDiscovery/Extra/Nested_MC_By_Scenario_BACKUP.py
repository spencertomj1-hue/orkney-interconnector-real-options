# DFES-scenario-dimension diagnostic overview: see docs/notes/Reporting/ScenarioDiscovery/Extra/Nested_MC_By_Scenario_BACKUP.md#overview

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import numpy as np
import matplotlib.pyplot as plt

import Model.System_Model as M
from Model.System_Model import Run_Strategy, Strategies_2, Scenarios, DFES_ONLY

# STRATEGY_COLOR consistency: see docs/notes/Reporting/ScenarioDiscovery/Extra/Nested_MC_By_Scenario_BACKUP.md#strategy_color-consistency-across-figures
STRATEGY_COLOR = {"Do Nothing": "#888888", "Baseline": "#1f4e79", "Staged": "#2e7d32",
                   "Flexible 1-Stage": "firebrick", "Flexible 4-Stage": "#b8860b",
                   "Flexible 1-Stage (Cost-Aware)": "#6a3d9a"}

# Nested Monte Carlo design rationale: see docs/notes/Reporting/ScenarioDiscovery/Extra/Nested_MC_By_Scenario_BACKUP.md#nested-monte-carlo-design-rationale
N_NESTED = 500
rng_nested = np.random.default_rng(42)
nested_capex_draws = rng_nested.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA, N_NESTED)

nested_store = {sname: {} for sname in Strategies_2}
for sname, factory in Strategies_2.items():
    for scen in DFES_ONLY:
        vals = np.empty(N_NESTED)
        demand = Scenarios[scen]
        for i, capex_mult in enumerate(nested_capex_draws):
            opts = factory(capex_mult)
            vals[i] = Run_Strategy((sname, opts), demand, scen)[3]
        nested_store[sname][scen] = vals

print(f"\n=== Nested Monte Carlo: capex-only spread, by scenario "
      f"(N={N_NESTED} per pair, £m) ===")
print(f"{'Strategy':<16}{'Scenario':<22}{'ENPV':>10}{'StdDev':>10}")
for sname in Strategies_2:
    for scen in DFES_ONLY:
        v = nested_store[sname][scen] / 1e6
        print(f"{sname:<16}{scen:<22}{v.mean():>10.0f}{v.std():>10.0f}")

# Chart interpretation: see docs/notes/Reporting/ScenarioDiscovery/Extra/Nested_MC_By_Scenario_BACKUP.md#chart-interpreting-bar-height-vs-error-bars
fig, ax = plt.subplots(figsize=(8, 4.5))
_scen_labels = DFES_ONLY
_x = np.arange(len(_scen_labels))
_width = 0.35
for _j, sname in enumerate(Strategies_2):
    _means = [nested_store[sname][scen].mean() / 1e6 for scen in _scen_labels]
    _stds = [nested_store[sname][scen].std() / 1e6 for scen in _scen_labels]
    ax.bar(_x + (_j - 0.5) * _width, _means, _width, yerr=_stds, capsize=3,
           color=STRATEGY_COLOR[sname], label=sname)
ax.axhline(0, color="grey", lw=0.8)
ax.set_xticks(_x)
ax.set_xticklabels(_scen_labels, rotation=15, ha="right")
ax.set_ylabel("ENPV, £m")
ax.set_title(f"Nested Monte Carlo — capex-only spread by scenario (N={N_NESTED} per pair)")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
            "Methodology_4/Images/nested_mc_by_scenario.png", dpi=200)
plt.show()
