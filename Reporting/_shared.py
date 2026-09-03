# Helpers shared by Results.py, Sensitivities.py and ScenarioDiscovery_Regenerate.py
# (previously copy-pasted into each of the three).

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np

import Model.System_Model as M
from Model.System_Model import Scenarios, Strategies_2
from Model.Model_Components import Decision
from Model.Options import NewLink


# Loud-fail provenance guard: a cache built under different model-defining
# flags than this run's current ones would silently produce wrong-world
# numbers. A pre-guard cache (no "metadata" key) fails loud too, not a
# silent pass -- an un-stamped cache's provenance is unknown, not assumed-fine.
def check_cache_provenance(cache, path):
    meta = cache.get("metadata")
    if meta is None:
        raise RuntimeError(
            f"{path} has no provenance metadata (written before this guard existed) -- "
            "regenerate it (or re-stamp it) before trusting its marg_store/marg_cost/marg_energy.")
    # no model flags tracked here currently (wind-as-option removed) -- kept
    # as an empty tuple so future flags can be added without restructuring.
    mismatches = [f"{k}: cache={meta[k]!r} vs current={cur!r}"
                  for k, cur in ()
                  if meta[k] != cur]
    if mismatches:
        raise RuntimeError(
            f"{path} was built under different model flags than this run expects -- "
            f"regenerate the cache before trusting it: " + "; ".join(mismatches))


# Turns a stored correlated shock block z (n_years, 3) + scenario name into
# (demand, price_seq, background_seq) with no rng involved -- the sample_*_seq
# functions never touch their rng argument when z_seq is supplied, so passing
# None is safe. Lets a stored draw's paths be replayed exactly without an rng.
def paths_from_stored_z(z, scenario):
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


# Local zero-build reference case (a Decision with BuildYear=None never
# fires -- see Model_Components.Decision.IsBuilt); not part of
# System_Model.Strategies_2, kept here as the "build nothing" baseline
# every dNPV/dEnergy/incremental-LCOE figure is measured against.
def do_nothing(capex_mult=1.0):
    return [Decision(NewLink(capex_mult), None)]


# Undiscounted capex of the fixed-year asset(s) built in the earliest
# build year, £, at capex_mult=1.0 -- a reference figure, not
# draw-dependent. Rule entries are skipped: build year isn't known until firing.
def initial_year_capex(factory):
    opts = factory(1.0)
    decisions = [d for d in opts if isinstance(d, Decision) and d.BuildYear() is not None]
    if not decisions:
        return 0.0
    first_year = min(d.BuildYear() for d in decisions)
    return sum(d.Asset().Capex() for d in decisions if d.BuildYear() == first_year)


# Incremental LCOE per draw vs ref, same definition as the deterministic
# headline table. dC<0 & dE>0 (strategy costs less and delivers more) is
# excluded from the ratio, not just guarded like the dE~0 case: that's
# genuine first-order dominance, not a bug, but £/MWh "cost of energy"
# isn't meaningful for it -- a saving divided by a gain isn't a cost per
# unit. Reported as its own "dominates" rate instead.
def lcoe_from_stores(cost_store, energy_store, strategies=None, ref="Do Nothing"):
    if strategies is None:
        strategies = Strategies_2
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


def print_metrics_table(store, label, strategies=None):
    if strategies is None:
        strategies = Strategies_2
    print(f"\n=== Metrics table — marginalised MC, {label} weighting (£m) ===")
    enpvs = {sname: vals.mean() for sname, vals in store.items()}
    print(f"{'Strategy':<20}{'ENPV':>9}{'P5':>9}{'P50':>9}{'P95':>9}"
          f"{'StdDev':>9}{'P(NPV<0)':>10}{'InitCapex':>11}{'dENPVvsBest':>13}")
    for sname, vals in store.items():
        v = vals / 1e6
        others = [e for s, e in enpvs.items() if s != sname]
        best_other = max(others) if others else float("nan")
        d_best = (enpvs[sname] - best_other) / 1e6
        p_neg = float(np.mean(vals < 0))
        init_capex = initial_year_capex(strategies[sname]) / 1e6
        print(f"{sname:<20}{v.mean():>9.0f}{np.percentile(v, 5):>9.0f}"
              f"{np.percentile(v, 50):>9.0f}{np.percentile(v, 95):>9.0f}"
              f"{v.std():>9.0f}{p_neg:>10.2f}{init_capex:>11.0f}{d_best:>13.0f}")
    print("(InitCapex = undiscounted capex of fixed-year assets built in the "
          "earliest build year -- 0/partial for flexible strategies, whose "
          "build years are drawn at runtime. dENPVvsBest = ENPV(strategy) - "
          "ENPV(best other strategy in this table).)")
