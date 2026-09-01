# see docs/notes/Comparisons/WXMode_Comparison.md#purpose-replay-mechanics-and-expected-effects

import pickle
import os
import sys
import numpy as np

# see docs/notes/Comparisons/WXMode_Comparison.md#sys-path-setup-for-comparisons-scripts
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import Model.System_Model as M
from Model.System_Model import Run_Strategy, Scenarios

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
print(f"INCLUDE_WIND_BUILDOUT={M.INCLUDE_WIND_BUILDOUT} (headline no-wind default, unchanged by this script)")

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

STRATEGY_FACTORIES = {
    "Baseline": M._baseline,
    "Fixed 4-Stage": M._staged,
    "Flexible 1-Stage": M._flexible,
    "Flexible 1-Stage (Cost-Aware)": M._flexible_cost_aware,
}

WX_ARMS = ["iid", "ar1"]

def cvar(x, alpha=0.10):
    var = np.percentile(x, alpha * 100)
    return float(x[x <= var].mean())

npv = {wx_mode: {sname: np.empty(N) for sname in STRATEGY_FACTORIES} for wx_mode in WX_ARMS}
rule_log = {wx_mode: {"Flexible 1-Stage": [], "Flexible 1-Stage (Cost-Aware)": []} for wx_mode in WX_ARMS}

for wx_mode in WX_ARMS:
    print(f"running WX_MODE={wx_mode!r} ({N} draws x {len(STRATEGY_FACTORIES)} strategies)...", flush=True)
    for i in range(N):
        capex_mult = _CACHE["draw_capex"][i]
        scenario = _CACHE["draw_scenario"][i]
        capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
        demand, price_seq, background_seq = _paths_from_stored_z(_CACHE["draw_z"][i], scenario)

        if wx_mode == "iid":
            # The cached draw IS already an iid draw -- reuse it directly,
            # same weather every other analysis this session has used.
            wx_seq = _CACHE["draw_wx_seq"][i]
        else:
            # Fresh, deterministic per-draw seed -- genuinely new weather
            # sampling under AR1, everything else held fixed from the cache.
            rng_wx = np.random.default_rng([2026, i])
            wx_seq = M.sample_wx_seq(rng_wx, len(M.YEARS), mode="ar1")

        for sname, factory in STRATEGY_FACTORIES.items():
            opts = factory(capex_mult)
            res = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                                capex_mult, capex_estimate_seq, price_seq, background_seq)
            npv[wx_mode][sname][i] = res[3]
            if sname in rule_log[wx_mode]:
                rule_log[wx_mode][sname].append(res[5]["Main Link"])

print("all runs done.\n")

print("=== IID vs AR(1) weather, no-wind default (seed=42, N=2000, NetZero_Tilt) ===")
header = f"{'Strategy':<22}{'WX_MODE':<9}{'ENPV_£m':>10}{'std_£m':>9}{'P(NPV<0)':>10}{'CVaR10_£m':>11}"
print(header)
print("-" * len(header))
for sname in STRATEGY_FACTORIES:
    for wx_mode in WX_ARMS:
        v = npv[wx_mode][sname]
        print(f"{sname:<22}{wx_mode:<9}{v.mean()/1e6:>10.1f}{v.std()/1e6:>9.1f}"
              f"{float(np.mean(v < 0)):>10.2f}{cvar(v)/1e6:>11.1f}")
    print()

print("=== Main Link build-year distribution: does trigger timing move under AR1? ===")
for sname in ["Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)"]:
    print(f"\n--- {sname} ---")
    for wx_mode in WX_ARMS:
        infos = rule_log[wx_mode][sname]
        fired = np.array([info["fired"] for info in infos])
        build_years = np.array([info["build_year"] for info in infos if info["fired"]])
        if len(build_years) == 0:
            print(f"  {wx_mode:<5} fired={fired.mean():.3f}  (never fires)")
        else:
            print(f"  {wx_mode:<5} fired={fired.mean():.3f}  mean_build_year={build_years.mean():.2f}  "
                  f"std={build_years.std():.2f}")

print(f"\n(replayed capex/scenario/price/demand/background from {MC_CACHE_PATH}, seed={_CACHE['seed']}, "
      f"n={N}; weather freshly drawn per WX_MODE, see header comment)")
