"""See docs/notes/Debugging/wind_scope1_equality_check.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
import Model.System_Model as M
from Model.System_Model import Run_Strategy, Strategies_2, Strategies_Flex, Scenarios, DFES_ONLY
from Model.Model_Components import Decision
from Model.Options import NewLink, Stage1_Wind_Buildout, Stage2_Wind_Buildout

def do_nothing(capex_mult=1.0):
    return [Decision(NewLink(capex_mult), None), Decision(Stage1_Wind_Buildout(), None), Decision(Stage2_Wind_Buildout(), None)]

ALL = {"Do Nothing": do_nothing, **Strategies_2, **Strategies_Flex}

assert M.WIND_AS_OPTION is False, "run this with WIND_AS_OPTION=False to check the Scope 1 refactor"

all_pass = True

# ---- 1. deterministic check, every DFES scenario -------------------------
print("=== Deterministic check: state['gen_total'] and state['background_gen_mw'], all DFES scenarios ===")
for scenario in DFES_ONLY:
    demand = Scenarios[scenario]
    gen_series = {}
    bg_series = {}
    for sname, factory in ALL.items():
        opts = factory(1.0)
        result = Run_Strategy((sname, opts), demand, scenario)
        gen_series[sname] = result[4]["gen_total"]
        bg_series[sname] = result[4]["background_gen_mw"]

    ref_name = "Do Nothing"
    gen_ok = all(np.array_equal(gen_series[ref_name], gen_series[s]) for s in ALL)
    bg_ok = all(np.array_equal(bg_series[ref_name], bg_series[s]) for s in ALL)
    status = "PASS" if (gen_ok and bg_ok) else "FAIL"
    if not (gen_ok and bg_ok):
        all_pass = False
    print(f"  {scenario:<24} gen_total equal={gen_ok}  background_gen_mw equal={bg_ok}  [{status}]")

# see docs/notes/Debugging/wind_scope1_equality_check.md#stochastic-monte-carlo-check-draw-order
print("\n=== Stochastic check: 25 Monte Carlo draws, seed=42 (matches Results.py's headline seed) ===")

def paths_from_z(z, scenario):
    demand = M.sample_demand_seq(None, Scenarios[scenario], len(M.YEARS), z_seq=z[:, 0])
    price_seq = M.sample_price_seq(None, M.price_series(scenario, M.YEARS), len(M.YEARS), z_seq=z[:, 1])
    base_bg = M.BACKGROUND.get(scenario)
    if base_bg is not None:
        bg_start_idx = base_bg.index[0] - M.YEARS[0]
        z_bg = z[bg_start_idx: bg_start_idx + len(base_bg.index), 2]
        background_seq = M.sample_background_seq(None, base_bg, z_seq=z_bg)
    else:
        background_seq = None
    return demand, price_seq, background_seq

rng = np.random.default_rng(42)
scen_names = list(M.SCENARIO_WEIGHTS["NetZero_Tilt"].keys())
scen_probs = list(M.SCENARIO_WEIGHTS["NetZero_Tilt"].values())

n_draws = 25
n_fail = 0
for i in range(n_draws):
    capex_mult = rng.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA)
    scenario = rng.choice(scen_names, p=scen_probs)
    wx_seq = M.sample_wx_seq(rng, len(M.YEARS))
    capex_estimate_seq = M.sample_capex_estimate_seq(rng, capex_mult, len(M.YEARS))
    z = M.sample_correlated_gbm_shocks(rng, len(M.YEARS))
    demand, price_seq, background_seq = paths_from_z(z, scenario)

    gen_series = {}
    for sname, factory in ALL.items():
        opts = factory(capex_mult)
        result = Run_Strategy((sname, opts), demand, scenario, wx_seq, capex_mult,
                               capex_estimate_seq, price_seq, background_seq)
        gen_series[sname] = result[4]["gen_total"]

    ref_name = "Do Nothing"
    draw_ok = all(np.array_equal(gen_series[ref_name], gen_series[s]) for s in ALL)
    if not draw_ok:
        n_fail += 1
        all_pass = False
        print(f"  draw {i}: scenario={scenario} capex_mult={capex_mult:.3f}  FAIL -- gen_total diverges across strategies")

print(f"  {n_draws - n_fail}/{n_draws} draws PASS (identical gen_total across all {len(ALL)} strategies)")

print(f"\n{'ALL CHECKS PASS' if all_pass else 'AT LEAST ONE CHECK FAILED'} -- WIND_AS_OPTION={M.WIND_AS_OPTION}")
