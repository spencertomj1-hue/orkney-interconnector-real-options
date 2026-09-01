# see docs/notes/Comparisons/FixAB_Comparison.md#purpose-and-replay-methodology

import pickle
import os
import sys
import numpy as np

# see docs/notes/Comparisons/FixAB_Comparison.md#sys-path-setup-for-comparisons-scripts
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import Model.System_Model as M
from Model.System_Model import Run_Strategy, Scenarios

MC_CACHE_PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                  "Methodology_4/Coding/Extra/MC_Cache/headline_mc.pkl")
with open(MC_CACHE_PATH, "rb") as _f:
    _CACHE = pickle.load(_f)

# see docs/notes/Comparisons/FixAB_Comparison.md#cache-provenance-guard-rationale
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

N = _CACHE["n"]
assert N == 2000 and _CACHE["seed"] == 42, "expected the headline seed=42, N=2000 cache"

# see docs/notes/Comparisons/FixAB_Comparison.md#replay-helper-_paths_from_stored_z
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

# ---- configs ----------------------------------------------------------
# see docs/notes/Comparisons/FixAB_Comparison.md#fix-a-v3-dfes-only-observable-rationale
FIXA_KWARGS = {"observable": "dfes_background_gen_mw"}
FIXB_KWARGS = {"gate_mode": "npv_proxy"}

CONFIGS = {
    "Current":       {"flex": {}, "cost_aware": {}},
    "+FixA":         {"flex": dict(FIXA_KWARGS), "cost_aware": dict(FIXA_KWARGS)},
    "+FixB":         {"flex": {}, "cost_aware": dict(FIXB_KWARGS)},
    "+FixA+FixB":    {"flex": dict(FIXA_KWARGS), "cost_aware": {**FIXA_KWARGS, **FIXB_KWARGS}},
}

# ---- strategy-invariant arms: read straight from the cache -------------
CACHED_STRATEGIES = ["Do Nothing", "Baseline", "Fixed 4-Stage"]
npv_store = {sname: {"Current": _CACHE["marg_store"][sname],
                      "+FixA": _CACHE["marg_store"][sname],
                      "+FixB": _CACHE["marg_store"][sname],
                      "+FixA+FixB": _CACHE["marg_store"][sname]}
             for sname in CACHED_STRATEGIES}
cost_store = {sname: {cfg: _CACHE["marg_cost"][sname] for cfg in CONFIGS} for sname in CACHED_STRATEGIES}
energy_store = {sname: {cfg: _CACHE["marg_energy"][sname] for cfg in CONFIGS} for sname in CACHED_STRATEGIES}

# "Current" for the two rule-driven strategies also comes straight from the
# cache (same kwargs => same call => no reason to redraw).
for sname in ["Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)"]:
    npv_store.setdefault(sname, {})["Current"] = _CACHE["marg_store"][sname]
    cost_store.setdefault(sname, {})["Current"] = _CACHE["marg_cost"][sname]
    energy_store.setdefault(sname, {})["Current"] = _CACHE["marg_energy"][sname]

rule_log_store = {"Flexible 1-Stage": {"Current": _CACHE["marg_rule_log"]["Flexible 1-Stage"]["Main Link"]},
                   "Flexible 1-Stage (Cost-Aware)": {"Current": _CACHE["marg_rule_log"]["Flexible 1-Stage (Cost-Aware)"]["Main Link"]}}

# ---- rerun Flexible / Flexible 1-Stage (Cost-Aware) for +FixA / +FixB / +FixA+FixB --
RERUN_CONFIGS = ["+FixA", "+FixB", "+FixA+FixB"]

for cfg_name in RERUN_CONFIGS:
    kwargs = CONFIGS[cfg_name]
    print(f"running {cfg_name} ({N} draws x 2 strategies)...", flush=True)

    npv_flex = np.empty(N); cost_flex = np.empty(N); energy_flex = np.empty(N)
    npv_ca = np.empty(N); cost_ca = np.empty(N); energy_ca = np.empty(N)
    rl_flex = []
    rl_ca = []

    for i in range(N):
        capex_mult = _CACHE["draw_capex"][i]
        scenario = _CACHE["draw_scenario"][i]
        wx_seq = _CACHE["draw_wx_seq"][i]
        capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
        demand, price_seq, background_seq = _paths_from_stored_z(_CACHE["draw_z"][i], scenario)

        opts_flex = M._flexible(capex_mult, **kwargs["flex"])
        res_flex = Run_Strategy(("Flexible 1-Stage", opts_flex), demand, scenario, wx_seq,
                                 capex_mult, capex_estimate_seq, price_seq, background_seq)
        npv_flex[i], cost_flex[i], energy_flex[i] = res_flex[3], res_flex[0], res_flex[1]
        rl_flex.append(res_flex[5]["Main Link"])

        opts_ca = M._flexible_cost_aware(capex_mult, **kwargs["cost_aware"])
        res_ca = Run_Strategy(("Flexible 1-Stage (Cost-Aware)", opts_ca), demand, scenario, wx_seq,
                               capex_mult, capex_estimate_seq, price_seq, background_seq)
        npv_ca[i], cost_ca[i], energy_ca[i] = res_ca[3], res_ca[0], res_ca[1]
        rl_ca.append(res_ca[5]["Main Link"])

    npv_store["Flexible 1-Stage"][cfg_name] = npv_flex
    cost_store["Flexible 1-Stage"][cfg_name] = cost_flex
    energy_store["Flexible 1-Stage"][cfg_name] = energy_flex
    rule_log_store["Flexible 1-Stage"][cfg_name] = rl_flex

    npv_store["Flexible 1-Stage (Cost-Aware)"][cfg_name] = npv_ca
    cost_store["Flexible 1-Stage (Cost-Aware)"][cfg_name] = cost_ca
    energy_store["Flexible 1-Stage (Cost-Aware)"][cfg_name] = energy_ca
    rule_log_store["Flexible 1-Stage (Cost-Aware)"][cfg_name] = rl_ca

print("all configs done.\n")

# ---- incremental LCOE vs Do Nothing, same definition as Results.py --------
def lcoe_vs_do_nothing(cost, energy, cost_ref, energy_ref):
    dE = energy - energy_ref
    dC = cost - cost_ref
    dominates = (dC < 0) & (dE > 0)
    valid = (np.abs(dE) > 1e-9) & ~dominates
    lcoe = np.where(valid, dC / dE / 1000, np.nan)
    return lcoe, float(dominates.mean())

# ---- comparison table -------------------------------------------------
STRATEGIES = ["Baseline", "Fixed 4-Stage", "Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)"]
print("=== Strategy x Config comparison (seed=42, N=2000, NetZero_Tilt, replayed from cache) ===")
header = f"{'Strategy':<22}{'Config':<14}{'ENPV_£m':>10}{'P(NPV<0)':>10}{'IncrLCOE_£/MWh':>16}{'dominates%':>12}"
print(header)
print("-" * len(header))
for sname in STRATEGIES:
    for cfg_name in CONFIGS:
        npv = npv_store[sname][cfg_name]
        cost = cost_store[sname][cfg_name]
        energy = energy_store[sname][cfg_name]
        cost_ref = cost_store["Do Nothing"][cfg_name]
        energy_ref = energy_store["Do Nothing"][cfg_name]
        lcoe, dom_frac = lcoe_vs_do_nothing(cost, energy, cost_ref, energy_ref)
        enpv = npv.mean() / 1e6
        p_neg = float(np.mean(npv < 0))
        mean_lcoe = np.nanmean(lcoe)
        print(f"{sname:<22}{cfg_name:<14}{enpv:>10.1f}{p_neg:>10.2f}{mean_lcoe:>16.2f}{dom_frac*100:>11.1f}%")
    print()

# ---- link build-year distributions -------------------------------------
print("=== Link build-year distributions (Main Link) ===")
for sname in ["Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)"]:
    print(f"\n--- {sname} ---")
    for cfg_name in CONFIGS:
        infos = rule_log_store[sname][cfg_name]
        fired = np.array([info["fired"] for info in infos])
        build_years = np.array([info["build_year"] for info in infos if info["fired"]])
        if len(build_years) == 0:
            print(f"  {cfg_name:<14} fired={fired.mean():.3f}  (never fires)")
            continue
        vals, counts = np.unique(build_years, return_counts=True)
        dist = ", ".join(f"{int(v)}:{c}" for v, c in zip(vals, counts))
        print(f"  {cfg_name:<14} fired={fired.mean():.3f}  mean_build_year={build_years.mean():.2f}  "
              f"dist=[{dist}]")

print(f"\n(replayed from {MC_CACHE_PATH}, seed={_CACHE['seed']}, n={N})")
