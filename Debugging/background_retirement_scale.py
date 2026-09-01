"""See docs/notes/Debugging/background_retirement_scale.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
from Inputs.Data_Processing.Generation.DFES_Background import BACKGROUND
import Model.System_Model as M
from Model.System_Model import Strategies_2, Scenarios, Run_Strategy

BASE_COMMISSION_YEAR = 2010
LIFE = 25


def net_background(df, base_commission_year=BASE_COMMISSION_YEAR, life=LIFE):
    # see docs/notes/Debugging/background_retirement_scale.md#net_background-return-semantics
    years = df.index.to_list()
    net = df.copy() * 0.0
    for tech in df.columns:
        cohorts = [(base_commission_year, df.loc[years[0], tech])]
        prev = df.loc[years[0], tech]
        for y in years[1:]:
            level = df.loc[y, tech]
            incr = level - prev
            if incr > 1e-9:
                cohorts.append((y, incr))
            prev = level
        for y in years:
            net.loc[y, tech] = sum(mw for cy, mw in cohorts if cy <= y < cy + life)
    return net


print(f"=== Immortal vs net background capacity, per scenario/technology (base level assumed "
      f"commissioned {BASE_COMMISSION_YEAR}, life={LIFE}y) ===")
net_by_scen = {}
max_divergence_overall = 0.0
for scen, df in BACKGROUND.items():
    net = net_background(df)
    net_by_scen[scen] = net
    print(f"\n{scen}:")
    print(f"{'Tech':<8}{'max_div_MW':>12}{'max_div_%':>11}{'at_year':>9}{'immortal[2051]':>16}{'net[2051]':>11}")
    for tech in df.columns:
        diff = df[tech] - net[tech]
        max_div = diff.max()
        max_div_year = diff.idxmax()
        pct = (max_div / df.loc[max_div_year, tech] * 100) if df.loc[max_div_year, tech] > 0 else 0.0
        max_divergence_overall = max(max_divergence_overall, max_div)
        print(f"{tech:<8}{max_div:>12.2f}{pct:>10.1f}%{max_div_year:>9}"
              f"{df.loc[2051, tech]:>16.2f}{net.loc[2051, tech]:>11.2f}")

print(f"\nMax in-horizon divergence across all scenarios/technologies: {max_divergence_overall:.2f} MW")


def decompose_npv(strategy_name, scenario_name, background_dict):
    _orig = M.BACKGROUND
    M.BACKGROUND = background_dict
    opts = Strategies_2[strategy_name](1.0)
    _, _, _, npv, _, _ = Run_Strategy((strategy_name, opts), Scenarios[scenario_name], scenario_name)
    M.BACKGROUND = _orig
    return npv


print(f"\n=== NPV, Do Nothing & Staged, capex_mult=1.0, BASE_WEATHER_YEAR: immortal vs net background ===")
print(f"{'Scenario':<22}{'Strategy':<12}{'NPV immortal':>14}{'NPV net':>10}{'delta':>10}")
for scen in Scenarios:
    if scen not in BACKGROUND:
        print(f"{scen:<22}{'(no BACKGROUND entry for this scenario -- e.g. Base -- skipped)':<44}")
        continue
    net_dict = {scen: net_by_scen[scen]}
    for sname in ("Do Nothing", "Staged"):
        n_immortal = decompose_npv(sname, scen, BACKGROUND) / 1e6
        n_net = decompose_npv(sname, scen, net_dict) / 1e6
        print(f"{scen:<22}{sname:<12}{n_immortal:>14.2f}{n_net:>10.2f}{(n_net - n_immortal):>10.2f}")

print("\n=== VERDICT ===")
print(f"Max in-horizon divergence between immortal and net background across all scenarios: "
      f"{max_divergence_overall:.2f} MW. This comes entirely from the pre-2026 base-level "
      f"cohort (assumed commissioned {BASE_COMMISSION_YEAR}) -- every post-2026 pipeline "
      f"increment retires after 2051 (Y+25 > 2051 for any Y>2026) and is structurally "
      f"unaffected by whether retirement logic exists at all.")
