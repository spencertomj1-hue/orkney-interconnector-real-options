# Regenerates Extra/ScenarioDiscovery/mc_draws.csv by replaying the cached
# seed=42, N=2000 draws (no resampling) through the current strategy code --
# mirrors Results.py's SCENARIO_DISCOVERY-gated capture block line for line,
# just fed from the cache's stored draws instead of a fresh run_marginalised()
# call. Run Scenario_Discovery.py after this to redo the PRIM analysis
# against the refreshed CSV.

import pickle
import os
import sys
import numpy as np
import pandas as pd

# Lives in Reporting/ScenarioDiscovery/ -- put Coding/ (2 levels up) back on
# sys.path so the package-qualified imports below resolve regardless of
# invocation cwd.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import Model.System_Model as M
from Model.System_Model import Run_Strategy, Strategies_2, Strategies_Flex
from Model.Decision_Rules import MAIN_LINK_BG_GEN_THRESHOLD as _BG_THRESH
from Reporting._shared import check_cache_provenance, paths_from_stored_z, do_nothing, lcoe_from_stores

MC_CACHE_PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                  "Methodology_4/Coding/Extra/MC_Cache/headline_mc.pkl")
with open(MC_CACHE_PATH, "rb") as _f:
    _CACHE = pickle.load(_f)

check_cache_provenance(_CACHE, MC_CACHE_PATH)

N = _CACHE["n"]
assert N == 2000 and _CACHE["seed"] == 42

ALL_STRATEGIES = {"Do Nothing": do_nothing, **Strategies_2, **Strategies_Flex}

# Recomputed fresh under current strategy defaults rather than read back from
# the cache, so a code change to e.g. a strategy's gate_mode is reflected here
# even though the underlying random draws are replayed unchanged.
marg_store = {sname: np.empty(N) for sname in ALL_STRATEGIES}
marg_cost = {sname: np.empty(N) for sname in ALL_STRATEGIES}
marg_energy = {sname: np.empty(N) for sname in ALL_STRATEGIES}

for i in range(N):
    capex_mult = _CACHE["draw_capex"][i]
    scenario = _CACHE["draw_scenario"][i]
    wx_seq = _CACHE["draw_wx_seq"][i]
    capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
    demand, price_seq, background_seq = paths_from_stored_z(_CACHE["draw_z"][i], scenario)

    for sname, factory in ALL_STRATEGIES.items():
        opts = factory(capex_mult)
        res = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                            capex_mult, capex_estimate_seq, price_seq, background_seq)
        marg_store[sname][i] = res[3]
        marg_cost[sname][i] = res[0]
        marg_energy[sname][i] = res[1]

draw_capex = _CACHE["draw_capex"]
draw_scenario = _CACHE["draw_scenario"]

# ---- path -> scalar summaries, same as Results.py's SCENARIO_DISCOVERY -----
# ---- gated block (same assumptions, same flags) ----------------------------
_wind_cf_proxy = np.array([
    np.mean([M._year_means[y] for y in _wx]) for _wx in _CACHE["draw_wx_seq"]
])
_capex_estimate_year0 = _CACHE["draw_capex_estimate_seq"][:, 0]

_n = N
_demand_terminal = np.empty(_n)
_price_terminal = np.empty(_n)
_bg_terminal_mw = np.full(_n, np.nan)
_year_bg135 = np.full(_n, np.nan)
_years_arr = np.array(M.YEARS)
for _i in range(_n):
    _demand, _price_seq, _bg_seq = paths_from_stored_z(_CACHE["draw_z"][_i], draw_scenario[_i])
    _demand_terminal[_i] = _demand[-1]
    _price_terminal[_i] = _price_seq[-1]
    if _bg_seq is not None:
        _bg_terminal_mw[_i] = _bg_seq.iloc[-1].sum()
        _bg_net_by_year = np.zeros(len(M.YEARS))
        for _yr in _bg_seq.index:
            if _yr in M.YEARS:
                _t = _yr - M.YEARS[0]
                _bg_net_by_year[_t] = sum(
                    max(0.0, mw - M.EXISTING_FLEET_NAMEPLATE.get(tech, 0.0))
                    for tech, mw in _bg_seq.loc[_yr].items())
        _crossed = np.where(_bg_net_by_year > _BG_THRESH)[0]
        if len(_crossed) > 0:
            _year_bg135[_i] = _years_arr[_crossed[0]]

_cols = {
    "draw_id": np.arange(_n),
    "capex_mult": draw_capex,
    "scenario": draw_scenario,
    "wind_cf_proxy_mean": _wind_cf_proxy,
    "capex_estimate_year0": _capex_estimate_year0,
    "demand_terminal_gwh": _demand_terminal,
    "price_terminal_gbp_mwh": _price_terminal,
    "background_terminal_mw": _bg_terminal_mw,
    "year_bg135_raw_crossed": _year_bg135,
}
for _sname in ALL_STRATEGIES:
    _colname = "npv_" + _sname.lower().replace(" ", "_").replace("-", "_")
    _cols[_colname] = marg_store[_sname]

_marg_lcoe, _ = lcoe_from_stores(marg_cost, marg_energy, ALL_STRATEGIES)
for _sname, _vals in _marg_lcoe.items():
    _colname = "lcoe_" + _sname.lower().replace(" ", "_").replace("-", "_")
    _cols[_colname] = _vals

_experiments = pd.DataFrame(_cols)
_sd_dir = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
           "Methodology_4/Coding/Reporting/ScenarioDiscovery/Extra")
_sd_csv_path = _sd_dir + "/mc_draws.csv"
_experiments.to_csv(_sd_csv_path, index=False)
print(f"scenario discovery experiments table written to {_sd_csv_path}, "
      f"{len(_experiments)} rows x {len(_experiments.columns)} columns")
