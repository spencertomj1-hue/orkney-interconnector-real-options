# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#purpose-and-scope

import pickle
import os
import sys
import numpy as np
import matplotlib.pyplot as plt

# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#sys-path-setup-for-comparisons-scripts
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import Model.System_Model as M
from Model.System_Model import Run_Strategy, Scenarios
from Model.Model_Components import Decision
from Model.Options import NewLink, Stage1_Wind_Buildout, Stage2_Wind_Buildout

MC_CACHE_PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                  "Methodology_4/Coding/Extra/MC_Cache/headline_mc.pkl")
with open(MC_CACHE_PATH, "rb") as _f:
    _CACHE = pickle.load(_f)

# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#cache-provenance-guard-rationale
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

# Local-only zero-build reference case -- copy-pasted from Results.py/Sensitivities.py
def _do_nothing(capex_mult=1.0):
    return [Decision(NewLink(capex_mult), None),
            Decision(Stage1_Wind_Buildout(), None),
            Decision(Stage2_Wind_Buildout(), None)]

STRATEGY_FACTORIES = {
    "Do Nothing": _do_nothing,
    "Baseline": M._baseline,
    "Fixed 4-Stage": M._staged,
    "Flexible 1-Stage": M._flexible,
    "Flexible 1-Stage (Cost-Aware)": M._flexible_cost_aware,
}

def _run_all(include_wind_buildout, label):
    _prev_include_wind_buildout = M.INCLUDE_WIND_BUILDOUT
    M.INCLUDE_WIND_BUILDOUT = include_wind_buildout
    print(f"running '{label}' (INCLUDE_WIND_BUILDOUT={include_wind_buildout}), "
          f"{N} draws x {len(STRATEGY_FACTORIES)} strategies...", flush=True)

    npv = {sname: np.empty(N) for sname in STRATEGY_FACTORIES}
    cost = {sname: np.empty(N) for sname in STRATEGY_FACTORIES}
    energy = {sname: np.empty(N) for sname in STRATEGY_FACTORIES}
    # see docs/notes/Comparisons/NoWindBuildout_Comparison.md#lcot-inputs-captured-per-strategy
    link_cost = {sname: np.empty(N) for sname in STRATEGY_FACTORIES}
    link_export = {sname: np.empty(N) for sname in STRATEGY_FACTORIES}
    rule_log = {"Flexible 1-Stage": [], "Flexible 1-Stage (Cost-Aware)": []}

    for i in range(N):
        capex_mult = _CACHE["draw_capex"][i]
        scenario = _CACHE["draw_scenario"][i]
        wx_seq = _CACHE["draw_wx_seq"][i]
        capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
        demand, price_seq, background_seq = _paths_from_stored_z(_CACHE["draw_z"][i], scenario)

        for sname, factory in STRATEGY_FACTORIES.items():
            opts = factory(capex_mult)
            res = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                                capex_mult, capex_estimate_seq, price_seq, background_seq)
            npv[sname][i], cost[sname][i], energy[sname][i] = res[0 + 3], res[0], res[1]
            state = res[4]
            link_cost[sname][i] = state["link_cost_total"]
            link_export[sname][i] = state["pv_link_export_gwh"]
            if sname in rule_log:
                rule_log[sname].append(res[5]["Main Link"])

    M.INCLUDE_WIND_BUILDOUT = _prev_include_wind_buildout   # restore ambient default (currently False)
    return npv, cost, energy, link_cost, link_export, rule_log


npv_without, cost_without, energy_without, link_cost_without, link_export_without, rl_without = _run_all(
    False, "without Stage1/2 wind (standard)")

print("all runs done.\n")

# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#sanity-check-against-the-cache
for sname in ["Baseline", "Fixed 4-Stage", "Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)"]:
    cached = _CACHE["marg_store"][sname]
    max_abs_diff = float(np.max(np.abs(npv_without[sname] - cached)))
    print(f"sanity check {sname:<22} max|rerun-cache| = £{max_abs_diff:,.2f} (should be ~0)")
print()

def lcoe_vs_do_nothing(cost, energy, cost_ref, energy_ref):
    dE = energy - energy_ref
    dC = cost - cost_ref
    dominates = (dC < 0) & (dE > 0)
    valid = (np.abs(dE) > 1e-9) & ~dominates
    lcoe = np.where(valid, dC / dE / 1000, np.nan)
    return lcoe, float(dominates.mean())

STRATEGIES = ["Baseline", "Fixed 4-Stage", "Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)"]
print("=== Without Stage1/2 wind buildout (standard), seed=42, N=2000, NetZero_Tilt ===")
header = f"{'Strategy':<22}{'ENPV_£m':>10}{'P(NPV<0)':>10}{'IncrLCOE_£/MWh':>16}{'dominates%':>12}"
print(header)
print("-" * len(header))
for sname in STRATEGIES:
    lcoe, dom_frac = lcoe_vs_do_nothing(cost_without[sname], energy_without[sname],
                                         cost_without["Do Nothing"], energy_without["Do Nothing"])
    enpv = npv_without[sname].mean() / 1e6
    p_neg = float(np.mean(npv_without[sname] < 0))
    mean_lcoe = np.nanmean(lcoe)
    print(f"{sname:<22}{enpv:>10.1f}{p_neg:>10.2f}{mean_lcoe:>16.2f}{dom_frac*100:>11.1f}%")

print("=== Link build-year distributions (Main Link), without Stage1/2 wind ===")
for sname in ["Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)"]:
    infos = rl_without[sname]
    fired = np.array([info["fired"] for info in infos])
    build_years = np.array([info["build_year"] for info in infos if info["fired"]])
    print(f"\n--- {sname} (fired={fired.mean():.3f}) ---")
    if len(build_years) == 0:
        print("  never fires")
        continue
    vals, counts = np.unique(build_years, return_counts=True)
    print(f"  mean_build_year={build_years.mean():.2f}, std={build_years.std():.2f}")
    for v, c in zip(vals, counts):
        print(f"    {int(v)}: {c}")

# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#flexible-1-stage-build-year-by-scenario
print("\n--- Flexible 1-Stage build year by scenario, without Stage1/2 wind ---")
scen = _CACHE["draw_scenario"]
infos = rl_without["Flexible 1-Stage"]
build_years = np.array([info["build_year"] if info["fired"] else np.nan for info in infos])
for s in sorted(set(scen)):
    mask = scen == s
    vals = build_years[mask]
    vals = vals[~np.isnan(vals)]
    if len(vals) == 0:
        print(f"  {s:<22} never fires (n={mask.sum()})")
    else:
        print(f"  {s:<22} mean={vals.mean():.2f}  std={vals.std():.2f}  n_fired={len(vals)}/{mask.sum()}")

# ---- LCOT (Levelised Cost of Transmission), without Stage1/2 wind --------
# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#lcot-definition-and-never-built-draws
def lcot_from_stores(link_cost, link_export, strategies):
    never_built_frac = {}
    out = {}
    for sname in strategies:
        lc = link_cost[sname]
        le = link_export[sname]
        never_built_frac[sname] = float(((lc <= 1e-9) | (le <= 1e-9)).mean())
        out[sname] = lc / (le * 1000)
    return out, never_built_frac


LCOT_STRATEGIES = ["Baseline", "Fixed 4-Stage", "Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)"]
lcot_without, lcot_never_built_frac = lcot_from_stores(link_cost_without, link_export_without, LCOT_STRATEGIES)

print("\n=== LCOT never-built fractions, without Stage1/2 wind ===")
for sname in LCOT_STRATEGIES:
    frac = lcot_never_built_frac[sname]
    if frac > 0:
        print(f"  {sname:<22} link never built in {frac:6.1%} of draws -- LCOT there reflects the "
              f"existing 40MW cable's own opex (currently an unverified £0 placeholder)")
    else:
        print(f"  {sname:<22} link built in every draw")

print("\n=== LCOT (Levelised Cost of Transmission) summary, without Stage1/2 wind -- £/MWh ===")
print(f"{'Strategy':<22}{'mean':>9}{'P5':>9}{'P50':>9}{'P95':>9}")
for sname in LCOT_STRATEGIES:
    v = lcot_without[sname]
    print(f"{sname:<22}{v.mean():>9.2f}{np.percentile(v, 5):>9.2f}"
          f"{np.percentile(v, 50):>9.2f}{np.percentile(v, 95):>9.2f}")

# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#re-plotting-the-lcot-target-curve
palette = ["#1f4e79", "#2e7d32", "#6a3d9a", "firebrick", "#e07b39", "#b8860b"]
LCOT_COLOR_MAP = dict(zip(LCOT_STRATEGIES, palette))
LCOT_PLOT_STRATEGIES = [s for s in LCOT_STRATEGIES if s != "Flexible 1-Stage (Cost-Aware)"]
fig, ax = plt.subplots(figsize=(7.5, 4.5))
for sname in LCOT_PLOT_STRATEGIES:
    v = lcot_without[sname]
    xs = np.sort(v)
    ys = np.arange(1, len(xs) + 1) / len(xs)
    ax.plot(xs, ys, lw=2, color=LCOT_COLOR_MAP[sname], label=sname)
ax.set_xlabel("LCOT, £/MWh (discounted Link-only cost / discounted energy exported through the link)")
ax.set_ylabel("Cumulative probability")
ax.set_title("Target curves — LCOT, without Stage1/2 wind buildout\n"
             f"(N={N}, seed={_CACHE['seed']})", fontsize=11)
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
            "Methodology_4/Images/target_curves_lcot_nowind.png", dpi=200)
plt.show()
print("\n(LCOT target curve, without-wind -> Images/target_curves_lcot_nowind.png)")

# ---- FIX 2: first-order stochastic dominance, Flexible 1-Stage vs Flexible 1-Stage ---------
# ---- Cost-Aware, without Stage1/2 wind -------------------------------------
# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#first-order-stochastic-dominance-check
def fosd_check(x, y, label_x, label_y, tol=1e-9):
    grid = np.unique(np.concatenate([x, y]))
    sx = np.sort(x)
    sy = np.sort(y)
    Fx = np.searchsorted(sx, grid, side="right") / len(x)
    Fy = np.searchsorted(sy, grid, side="right") / len(y)
    diff = Fx - Fy   # <=0 everywhere -> x FOSD y (x stochastically larger); >=0 everywhere -> y FOSD x

    if np.all(diff <= tol):
        verdict = f"{label_x} FOSD-dominates {label_y}"
    elif np.all(diff >= -tol):
        verdict = f"{label_y} FOSD-dominates {label_x}"
    else:
        verdict = f"NEITHER dominates -- the two NPV CDFs cross"

    # see docs/notes/Comparisons/NoWindBuildout_Comparison.md#fosd-coarse-grid-for-crossing-report
    coarse = np.linspace(grid.min(), grid.max(), 500)
    Fx_c = np.searchsorted(sx, coarse, side="right") / len(x)
    Fy_c = np.searchsorted(sy, coarse, side="right") / len(y)
    diff_c = Fx_c - Fy_c
    sign_c = np.sign(diff_c)
    sign_c[sign_c == 0] = 1   # treat exact-zero as a continuation, not its own flip
    flips = np.where(np.diff(sign_c) != 0)[0]
    crossings = coarse[flips] if len(flips) else np.array([])

    return verdict, diff, crossings


def cvar(x, alpha=0.10):
    # Expected value of the worst alpha-fraction of outcomes (left-tail risk).
    var = np.percentile(x, alpha * 100)
    tail = x[x <= var]
    return float(tail.mean())


npv_flex = npv_without["Flexible 1-Stage"]
npv_ca = npv_without["Flexible 1-Stage (Cost-Aware)"]

verdict, diff, crossings = fosd_check(npv_flex, npv_ca, "Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)")

print("\n=== First-order stochastic dominance: Flexible 1-Stage vs Flexible 1-Stage (Cost-Aware), without Stage1/2 wind ===")
print(f"Verdict: {verdict}")
if "NEITHER" in verdict:
    if len(crossings):
        print(f"CDFs cross at approximately NPV = " + ", ".join(f"£{c/1e6:.0f}m" for c in crossings))
    else:
        print("Sign changes but the coarse grid didn't resolve a clean crossing point -- see min/max diff below.")
print(f"max(F_Flexible - F_CostAware) = {diff.max():+.4f}   "
      f"min(F_Flexible - F_CostAware) = {diff.min():+.4f}")
print("(negative => Flexible 1-Stage's CDF sits below CostAware's at that NPV level, "
      "i.e. Flexible 1-Stage assigns LESS probability to being at-or-below that NPV -- "
      "Flexible 1-Stage 'ahead' there; positive => CostAware ahead there.)")

print(f"\n{'':<22}{'mean_£m':>10}{'median_£m':>11}{'P5_£m':>9}{'P95_£m':>9}"
      f"{'P(NPV<0)':>10}{'CVaR10_£m':>11}")
for label, v in [("Flexible 1-Stage", npv_flex), ("Flexible 1-Stage (Cost-Aware)", npv_ca)]:
    print(f"{label:<22}{v.mean()/1e6:>10.1f}{np.median(v)/1e6:>11.1f}"
          f"{np.percentile(v, 5)/1e6:>9.1f}{np.percentile(v, 95)/1e6:>9.1f}"
          f"{float(np.mean(v < 0)):>10.2f}{cvar(v)/1e6:>11.1f}")
print("(CVaR10 = mean NPV of the worst 10% of draws -- the tail risk figure "
      "a median/mean comparison alone can't show.)")

# ---- Value of flexibility per scenario, and regret/max-regret -------------
# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#value-of-flexibility-and-regret-tables
SCEN_ORDER = ["Electric Engagement", "Falling Behind", "Holistic Transition", "Hydrogen Evolution"]
SCEN_ABBR = {"Electric Engagement": "EE", "Falling Behind": "FB",
             "Holistic Transition": "HT", "Hydrogen Evolution": "HE"}
RIGID_STRATEGIES = ["Baseline", "Fixed 4-Stage"]
FLEX_STRATEGIES = ["Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)"]
REGRET_STRATEGIES = ["Do Nothing", "Baseline", "Fixed 4-Stage", "Flexible 1-Stage", "Flexible 1-Stage (Cost-Aware)"]

scen = _CACHE["draw_scenario"]

def scenario_mean_npv(npv_dict, scen, strategies):
    return {sname: {s: float(npv_dict[sname][scen == s].mean()) for s in SCEN_ORDER}
            for sname in strategies}

smean_flex = scenario_mean_npv(npv_without, scen, RIGID_STRATEGIES + FLEX_STRATEGIES)
vof = {
    fname: {s: smean_flex[fname][s] - max(smean_flex[r][s] for r in RIGID_STRATEGIES) for s in SCEN_ORDER}
    for fname in FLEX_STRATEGIES
}

print("\n=== Value of flexibility per scenario: ENPV(flex) - ENPV(best rigid), £m, without Stage1/2 wind ===")
print("(best rigid = max(Baseline, Fixed 4-Stage) in that scenario -- where the option actually pays)")
print(f"{'Scenario':<6}{'BestRigid':>12}{'Flexible 1-Stage':>12}{'VoF(Flex)':>12}"
      f"{'CostAware':>12}{'VoF(CA)':>12}")
for s in SCEN_ORDER:
    best_rigid = max(smean_flex[r][s] for r in RIGID_STRATEGIES)
    print(f"{SCEN_ABBR[s]:<6}{best_rigid/1e6:>12.1f}{smean_flex['Flexible 1-Stage'][s]/1e6:>12.1f}"
          f"{vof['Flexible 1-Stage'][s]/1e6:>+12.1f}{smean_flex['Flexible 1-Stage (Cost-Aware)'][s]/1e6:>12.1f}"
          f"{vof['Flexible 1-Stage (Cost-Aware)'][s]/1e6:>+12.1f}")

print("\n=== Regret table: best-achievable NPV minus this strategy's NPV, per scenario, £m, "
      "without Stage1/2 wind ===")
print("(best-achievable = max over ALL 5 strategies in that scenario; MaxRegret = the canonical "
      "Savage minimax-regret robustness metric -- the worst-case shortfall from optimal across scenarios)")
smean_regret = scenario_mean_npv(npv_without, scen, REGRET_STRATEGIES)
regret = {}
maxregret = {}
header = f"{'Strategy':<22}" + "".join(f"{SCEN_ABBR[s]:>10}" for s in SCEN_ORDER) + f"{'MaxRegret':>12}"
print(header)
for strat in REGRET_STRATEGIES:
    regrets = {s: max(smean_regret[s2][s] for s2 in REGRET_STRATEGIES) - smean_regret[strat][s] for s in SCEN_ORDER}
    max_regret = max(regrets.values())
    regret[strat] = regrets
    maxregret[strat] = max_regret
    row = (f"{strat:<22}" + "".join(f"{regrets[s]/1e6:>10.1f}" for s in SCEN_ORDER)
           + f"{max_regret/1e6:>12.1f}")
    print(row)

# ---- plots ------------------------------------------------------------
# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#plot-trimming-note
palette5 = ["#888888", "#1f4e79", "#2e7d32", "firebrick", "#b8860b"]   # Do Nothing, Baseline, Fixed 4-Stage, Flexible 1-Stage, Flexible 1-Stage (Cost-Aware)
REGRET_COLOR_MAP = dict(zip(REGRET_STRATEGIES, palette5))
flex_colors = {"Flexible 1-Stage": "firebrick", "Flexible 1-Stage (Cost-Aware)": "#b8860b"}
FLEX_PLOT_STRATEGIES = [s for s in FLEX_STRATEGIES if s != "Flexible 1-Stage (Cost-Aware)"]
REGRET_PLOT_STRATEGIES = [s for s in REGRET_STRATEGIES if s != "Flexible 1-Stage (Cost-Aware)"]
x = np.arange(len(SCEN_ORDER))
scen_labels = [SCEN_ABBR[s] for s in SCEN_ORDER]

# 1. Value of flexibility per scenario, without Stage1/2 wind (standard).
fig, ax = plt.subplots(figsize=(7, 4.5))
width = 0.5
n = len(FLEX_PLOT_STRATEGIES)
for i, fname in enumerate(FLEX_PLOT_STRATEGIES):
    vals = [vof[fname][s] / 1e6 for s in SCEN_ORDER]
    ax.bar(x + (i - (n - 1) / 2) * width, vals, width, color=flex_colors[fname], label=fname)
ax.axhline(0, color="grey", lw=0.8)
ax.set_xticks(x)
ax.set_xticklabels(scen_labels)
ax.set_ylabel("VoF = ENPV(flex) - ENPV(best rigid), £m")
ax.set_title("Value of flexibility per scenario: ENPV(flex) - ENPV(best rigid)")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
            "Methodology_4/Images/value_of_flexibility_per_scenario.png", dpi=200)
plt.show()

# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#regret-per-scenario-chart-baseline
fig, ax = plt.subplots(figsize=(8, 4.5))
width = 0.8 / len(REGRET_PLOT_STRATEGIES)
n = len(REGRET_PLOT_STRATEGIES)
for i, strat in enumerate(REGRET_PLOT_STRATEGIES):
    vals = [regret[strat][s] / 1e6 for s in SCEN_ORDER]
    ax.bar(x + (i - (n - 1) / 2) * width, vals, width, color=REGRET_COLOR_MAP[strat], label=strat)
ax.set_xticks(x)
ax.set_xticklabels(scen_labels)
ax.set_ylabel("Regret = best-achievable NPV - strategy NPV, £m")
ax.set_title("Regret per scenario (lower = closer to that scenario's best strategy)")
ax.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
            "Methodology_4/Images/regret_per_scenario.png", dpi=200)
plt.show()

# see docs/notes/Comparisons/NoWindBuildout_Comparison.md#max-regret-summary-chart-note
fig, ax = plt.subplots(figsize=(7.5, 4.5))
xs = np.arange(len(REGRET_PLOT_STRATEGIES))
vals = [maxregret[strat] / 1e6 for strat in REGRET_PLOT_STRATEGIES]
ax.bar(xs, vals, color=[REGRET_COLOR_MAP[strat] for strat in REGRET_PLOT_STRATEGIES])
ax.set_xticks(xs)
ax.set_xticklabels(REGRET_PLOT_STRATEGIES, rotation=20, ha="right")
ax.set_ylabel("Max regret across EE/FB/HT/HE, £m (lower = more robust)")
ax.set_title("Minimax regret by strategy, without Stage1/2 wind buildout")
fig.tight_layout()
fig.savefig("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
            "Methodology_4/Images/max_regret_summary.png", dpi=200)
plt.show()

print("\n(plots -> Images/value_of_flexibility_per_scenario.png, Images/regret_per_scenario.png, "
      "Images/max_regret_summary.png)")

print(f"\n(replayed from {MC_CACHE_PATH}, seed={_CACHE['seed']}, n={N})")
