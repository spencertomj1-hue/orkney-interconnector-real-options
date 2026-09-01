# Regenerates the mc_draws.csv cache replay: see docs/notes/Reporting/ScenarioDiscovery/ScenarioDiscovery_Regenerate.md#overview

import pickle
import os
import sys
import numpy as np
import pandas as pd

# sys.path setup: see docs/notes/Reporting/ScenarioDiscovery/ScenarioDiscovery_Regenerate.md#syspath-setup-rationale
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import Model.System_Model as M
from Model.System_Model import Run_Strategy, Scenarios, Strategies_2, Strategies_Flex
from Model.Model_Components import Decision
from Model.Options import NewLink, Stage1_Wind_Buildout, Stage2_Wind_Buildout
from Model.Decision_Rules import MAIN_LINK_BG_GEN_THRESHOLD as _BG_THRESH

MC_CACHE_PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                  "Methodology_4/Coding/Extra/MC_Cache/headline_mc.pkl")
with open(MC_CACHE_PATH, "rb") as _f:
    _CACHE = pickle.load(_f)

def _check_cache_provenance(cache, path):
    meta = cache.get("metadata")
    if meta is None:
        raise RuntimeError(
            f"{path} has no provenance metadata (written before this guard existed) -- "
            "regenerate it (or re-stamp it) before trusting its marg_store/marg_cost/marg_energy.")
    mismatches = [f"{k}: cache={meta[k]!r} vs current={cur!r}"
                  for k, cur in (("INCLUDE_WIND_BUILDOUT", M.INCLUDE_WIND_BUILDOUT),
                                 ("WIND_AS_OPTION", M.WIND_AS_OPTION))
                  if meta[k] != cur]
    if mismatches:
        raise RuntimeError(
            f"{path} was built under different model flags than this run expects -- "
            f"regenerate the cache before trusting it: " + "; ".join(mismatches))

_check_cache_provenance(_CACHE, MC_CACHE_PATH)
print(f"INCLUDE_WIND_BUILDOUT={M.INCLUDE_WIND_BUILDOUT}, WIND_AS_OPTION={M.WIND_AS_OPTION} "
      "(current headline default, unchanged by this script)")

N = _CACHE["n"]
assert N == 2000 and _CACHE["seed"] == 42

def _paths_from_stored_z(z, scenario):
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

def _do_nothing(capex_mult=1.0):
    return [Decision(NewLink(capex_mult), None),
            Decision(Stage1_Wind_Buildout(), None),
            Decision(Stage2_Wind_Buildout(), None)]

ALL_STRATEGIES = {"Do Nothing": _do_nothing, **Strategies_2, **Strategies_Flex}
print("strategies:", list(ALL_STRATEGIES.keys()))

# Replay rationale: see docs/notes/Reporting/ScenarioDiscovery/ScenarioDiscovery_Regenerate.md#replay-recomputing-marg_store-marg_cost-marg_energy-under-current-defaults
marg_store = {sname: np.empty(N) for sname in ALL_STRATEGIES}
marg_cost = {sname: np.empty(N) for sname in ALL_STRATEGIES}
marg_energy = {sname: np.empty(N) for sname in ALL_STRATEGIES}

print(f"running {N} draws x {len(ALL_STRATEGIES)} strategies...", flush=True)
for i in range(N):
    capex_mult = _CACHE["draw_capex"][i]
    scenario = _CACHE["draw_scenario"][i]
    wx_seq = _CACHE["draw_wx_seq"][i]
    capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
    demand, price_seq, background_seq = _paths_from_stored_z(_CACHE["draw_z"][i], scenario)

    for sname, factory in ALL_STRATEGIES.items():
        opts = factory(capex_mult)
        res = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                            capex_mult, capex_estimate_seq, price_seq, background_seq)
        marg_store[sname][i] = res[3]
        marg_cost[sname][i] = res[0]
        marg_energy[sname][i] = res[1]
print("replay done.\n")

draw_capex = _CACHE["draw_capex"]
draw_scenario = _CACHE["draw_scenario"]

# ---- lcoe_from_stores, copy-pasted verbatim from Results.py (defined ------
# ---- locally there, not importable) ----------------------------------------
def lcoe_from_stores(cost_store, energy_store, strategies, ref="Do Nothing"):
    dC_ref = cost_store[ref]
    dE_ref = energy_store[ref]
    out = {}
    dominates_frac = {}
    for sname in strategies:
        if sname == ref:
            continue
        dE = energy_store[sname] - dE_ref
        dC = cost_store[sname] - dC_ref
        dominates = (dC < 0) & (dE > 0)
        valid = (np.abs(dE) > 1e-9) & ~dominates
        out[sname] = np.where(valid, dC / dE / 1000, np.nan)
        dominates_frac[sname] = float(dominates.mean())
    return out, dominates_frac

# ---- path -> scalar summaries, copy-pasted verbatim from Results.py's -----
# ---- SCENARIO_DISCOVERY-gated block (same assumptions, same flags) --------
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
    _demand, _price_seq, _bg_seq = _paths_from_stored_z(_CACHE["draw_z"][_i], draw_scenario[_i])
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
print(f"columns: {list(_experiments.columns)}")
