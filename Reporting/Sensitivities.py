# Sensitivity sweeps, split out of Results.py. Run Results.py first (with
# RUN_MC=True) so MC_CACHE_PATH exists -- every Monte Carlo sweep below loads
# that cache's draws instead of redrawing them.
#
# [1] Henao, Sauma, Reyes, Gonzalez (2017) Value of the option to defer a
#     transmission investment, Energy Economics 65.
# [2] Nur, MacKenzie, Min (2026) Valuation of a sequential compound option for
#     generation/transmission expansion, J. Economy and Technology 4.
# [4] Graca Gomes, Cardin, Wu (2025) Strategic real options for solar PV, IET PNZ 2025.

import os
import sys
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

import numpy as np
import matplotlib.pyplot as plt
import pickle

import Model.System_Model as M
from Model.System_Model import Run_Strategy, Strategies_2, Strategies_Flex, Scenarios, DFES_ONLY
import Model.Options as O
from Model.Options import STAGED_LINK_FIXED_PER_STAGE_SWEEP, LINK_OPEX_SWEEP
from Model.Decision_Rules import STAGED_LINK_THETA_SWEEP
from Inputs.Data_Processing.Generation.GBM_Correlation import PLACEHOLDER_CORR_MATRIX
from Reporting._shared import check_cache_provenance, paths_from_stored_z, do_nothing, print_metrics_table

# All plots this file produces are saved here.
SENSITIVITIES_PLOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sensitivities_Plots")
os.makedirs(SENSITIVITIES_PLOTS_DIR, exist_ok=True)

MC_CACHE_PATH = os.path.join(REPO_ROOT, "Extra", "MC_Cache", "headline_mc.pkl")
with open(MC_CACHE_PATH, "rb") as _f:
    _CACHE = pickle.load(_f)

check_cache_provenance(_CACHE, MC_CACHE_PATH)

ALL_STRATEGIES = {"Do Nothing": do_nothing, **Strategies_2, **Strategies_Flex}
TARGET_STRATEGIES = ["Baseline", "Fixed 4-Stage", "Flexible 4-Stage", "Flexible 1-Stage (Cost-Aware)", "Flexible 1-Stage"]
TARGET_LABELS = {s: s for s in TARGET_STRATEGIES}   # identity map -- see Results.py's own TARGET_LABELS comment
# The standard 4-strategy set every headline chart shows (Baseline, Fixed
# 4-Stage, Flexible 4-Stage, Flexible 1-Stage), matching Results.py's own
# target curves -- prints below still use the full TARGET_STRATEGIES.
PLOT_STRATEGIES = [s for s in TARGET_STRATEGIES if s != "Flexible 1-Stage (Cost-Aware)"]
palette = ["#1f4e79", "#2e7d32", "firebrick", "#b8860b", "#6a3d9a", "#e07b39"]

def crossover(rates, gap):
    s = np.sign(gap)
    for i in range(len(gap) - 1):
        if s[i] != s[i + 1] and s[i] != 0:
            return rates[i] + (rates[i+1] - rates[i]) * abs(gap[i]) / abs(gap[i] - gap[i+1])
    return None

# ---- discount rate table, Flat vs Green Book, crossover curves ------------
# All three below are deterministic (no Monte Carlo), so they don't touch
# the MC cache at all -- they call Run_Strategy directly.
def enpv(sname, r):
    M.set_rate(r)
    opts = Strategies_2[sname](1.0)
    return np.mean([Run_Strategy((sname, opts), Scenarios[s], s)[3]
                    for s in DFES_ONLY]) / 1e6

print("\n=== discount rate sensitivity: ENPV, £m ===")
rates_t = [0.025, 0.035, 0.05, 0.07, 0.10]
print(f"{'Strategy':<18}" + "".join(f"{r*100:>9.1f}%" for r in rates_t))
for sname in Strategies_2:
    print(f"{sname:<18}" + "".join(f"{enpv(sname, r):>10.0f}" for r in rates_t))

# ---- flat 3.5% vs Green Book's actual declining schedule -------------------
# The table above sweeps a single FLAT rate throughout, but Green Book's real
# schedule declines (3.5% years 1-30, 3.0% years 31-75, ...) and this model's
# 33-year horizon (2019-2051) puts 2 years (2050, 2051) in the 3.0% band --
# checked directly for the size of that difference rather than assumed.
print("\n=== Flat 3.5% vs Green Book declining schedule: ENPV, £m ===")
M.set_rate(0.035)
print(f"{'Strategy':<18}{'Flat_3.5%':>12}{'GB_declining':>14}{'Delta_%':>10}")
for sname in Strategies_2:
    opts = Strategies_2[sname](1.0)
    M.DISCOUNT_MODE = "flat"
    npv_flat = np.mean([Run_Strategy((sname, opts), Scenarios[s], s)[3] for s in DFES_ONLY])
    M.DISCOUNT_MODE = "green_book_declining"
    npv_gb = np.mean([Run_Strategy((sname, opts), Scenarios[s], s)[3] for s in DFES_ONLY])
    M.DISCOUNT_MODE = "flat"
    delta_pct = (npv_gb - npv_flat) / abs(npv_flat) if npv_flat else float("nan")
    print(f"{sname:<18}{npv_flat/1e6:>12.0f}{npv_gb/1e6:>14.0f}{delta_pct:>10.1%}")

# ---- crossover curves -----------------------------------------------------
# Discount-rate sensitivity of build-now-vs-defer value, and the crossing
# rate where the ranking flips, is the same real-options question [1]
# resolves with a binomial tree and [2] resolves with a binomial lattice.
rates = np.arange(0.01, 0.121, 0.005)
PAIRS = [("Baseline", "Fixed 4-Stage")]
curves = {f"{a} − {b}": np.array([enpv(a, r) - enpv(b, r) for r in rates])
          for a, b in PAIRS}
M.set_rate(0.035)   # restore

fig, ax = plt.subplots(figsize=(7.5, 4.5))
for i, ((label, gap), col) in enumerate(zip(curves.items(), ["#1f4e79", "#2e7d32"])):
    ax.plot(rates * 100, gap, lw=2, color=col, label=label)
    c = crossover(rates, gap)
    if c is not None:
        ax.plot(c * 100, 0, "o", color=col, zorder=5)
        ax.annotate(f"{c*100:.2f}%", (c * 100, 0), color=col,
                    textcoords="offset points", xytext=(6, 10 - 22 * i))
    print(f"crossover {label}: "
          + (f"{c*100:.2f}%" if c is not None else "none in 1-12%"))

ax.axhline(0, color="grey", lw=0.8)
ax.axvline(3.5, color="firebrick", ls="--", lw=1, label="Green Book 3.5%")
ax.set_xlabel("Discount rate (%)")
ax.set_ylabel("ΔENPV, £m")
ax.set_title("Build early vs defer, mean across DFES scenarios")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(os.path.join(SENSITIVITIES_PLOTS_DIR, "discount_sensitivity.png"), dpi=200)
plt.close(fig)

# ---- 7. weighting sensitivity: Equal (comparison vs the NetZero_Tilt --
# ---- headline used everywhere else) -------------------------------------
# The NetZero_Tilt ranking comes straight from the cache (Results.py's
# headline run). The Equal-weighted run is a genuinely different experiment
# (different scenario draw probabilities, so not reconstructable from the
# cache's stored draws) -- it needs its own fresh run.
def _run_marginalised_weighting(weights, seed=42, n=2000, strategies=None):
    if strategies is None:
        strategies = Strategies_2
    rng = np.random.default_rng(seed)
    scen_names = list(weights.keys())
    scen_probs = list(weights.values())

    store = {sname: np.empty(n) for sname in strategies}

    for i in range(n):
        capex_mult = rng.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA)
        scenario = rng.choice(scen_names, p=scen_probs)
        wx_seq = M.sample_wx_seq(rng, len(M.YEARS))
        capex_estimate_seq = M.sample_capex_estimate_seq(rng, capex_mult, len(M.YEARS))
        z = M.sample_correlated_gbm_shocks(rng, len(M.YEARS))
        demand, price_seq, background_seq = paths_from_stored_z(z, scenario)

        for sname, factory in strategies.items():
            opts = factory(capex_mult)
            result = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                                   capex_mult, capex_estimate_seq, price_seq, background_seq)
            store[sname][i] = result[3]

    return store

marg_store_equal = _run_marginalised_weighting(M.SCENARIO_WEIGHTS["Equal"], strategies=ALL_STRATEGIES)
print_metrics_table(marg_store_equal, "Equal", ALL_STRATEGIES)

_marg_store_tilt = _CACHE["marg_store"]   # NetZero_Tilt, from Results.py's headline run
rank_tilt = sorted(_marg_store_tilt, key=lambda s: -_marg_store_tilt[s].mean())
rank_equal = sorted(marg_store_equal, key=lambda s: -marg_store_equal[s].mean())
if rank_tilt == rank_equal:
    print(f"\nENPV ranking UNCHANGED between NetZero_Tilt and Equal weightings: "
          f"{rank_tilt}")
else:
    print(f"\nENPV ranking CHANGES between weightings:")
    print(f"  NetZero_Tilt: {rank_tilt}")
    print(f"  Equal:        {rank_equal}")

# Colour here encodes WEIGHTING, not strategy -- deliberately doesn't reuse
# `palette` (which codes strategy identity everywhere else in this file), to
# avoid implying the wrong thing is being colour-coded.
_WEIGHTING_COLOR = {"NetZero_Tilt": "#1f4e79", "Equal": "firebrick"}
fig, ax = plt.subplots(figsize=(8.5, 4.5))
_snames = list(ALL_STRATEGIES.keys())
_x = np.arange(len(_snames))
_width = 0.35
_tilt_means = [_marg_store_tilt[s].mean() / 1e6 for s in _snames]
_equal_means = [marg_store_equal[s].mean() / 1e6 for s in _snames]
ax.bar(_x - _width / 2, _tilt_means, _width, color=_WEIGHTING_COLOR["NetZero_Tilt"], label="NetZero_Tilt")
ax.bar(_x + _width / 2, _equal_means, _width, color=_WEIGHTING_COLOR["Equal"], label="Equal")
ax.axhline(0, color="grey", lw=0.8)
ax.set_xticks(_x)
ax.set_xticklabels(_snames, rotation=20, ha="right")
ax.set_ylabel("ENPV, £m")
ax.set_title("Scenario-weighting sensitivity — ENPV by strategy, NetZero_Tilt vs Equal")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(os.path.join(SENSITIVITIES_PLOTS_DIR, "weighting_sensitivity.png"), dpi=200)
plt.close(fig)

# ---- 9+10. RESIDUAL_ON_OVERRUN & CONSTRAINT_COST sensitivity, combined ----
# Both sweeps share NetZero_Tilt weighting, n=500, drawn once per iteration --
# every Strategies_2 strategy runs under all settings (2 residual flags + N
# constraint costs) on the same shared draw, taken from the cache's first
# N_SENS rows.
N_SENS = 500
_orig_residual_flag = M.RESIDUAL_ON_OVERRUN
_orig_constraint_cost = M.CONSTRAINT_COST
residual_flags = (True, False)
constraint_cost_values = M.CONSTRAINT_COST_SWEEP

residual_draws = {flag: {sname: np.empty(N_SENS) for sname in Strategies_2} for flag in residual_flags}
constraint_draws = {cc: {sname: np.empty(N_SENS) for sname in Strategies_2} for cc in constraint_cost_values}

for i in range(N_SENS):
    capex_mult = _CACHE["draw_capex"][i]
    scenario = _CACHE["draw_scenario"][i]
    wx_seq = _CACHE["draw_wx_seq"][i]
    capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
    demand, price_seq, background_seq = paths_from_stored_z(_CACHE["draw_z"][i], scenario)

    for sname, factory in Strategies_2.items():
        opts = factory(capex_mult)

        for _flag in residual_flags:
            M.RESIDUAL_ON_OVERRUN = _flag
            result = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                                   capex_mult, capex_estimate_seq, price_seq, background_seq)
            residual_draws[_flag][sname][i] = result[3]
        M.RESIDUAL_ON_OVERRUN = _orig_residual_flag

        for _cc in constraint_cost_values:
            M.CONSTRAINT_COST = _cc
            result = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                                   capex_mult, capex_estimate_seq, price_seq, background_seq)
            constraint_draws[_cc][sname][i] = result[3]
        M.CONSTRAINT_COST = _orig_constraint_cost

residual_sensitivity = {flag: {sname: vals.mean() for sname, vals in d.items()}
                         for flag, d in residual_draws.items()}
constraint_sensitivity = {cc: {sname: vals.mean() for sname, vals in d.items()}
                           for cc, d in constraint_draws.items()}

# True credits residual value on the overrun-inflated capex (refunds the
# overrun as salvage); default False credits base capex only.
print("\n=== RESIDUAL_ON_OVERRUN sensitivity: ENPV, marginalised MC, NetZero_Tilt weighting, N=500 ===")
print(f"{'Strategy':<18}{'ENPV True':>12}{'ENPV False':>12}{'delta':>10}")
for sname in Strategies_2:
    v_true = residual_sensitivity[True][sname] / 1e6
    v_false = residual_sensitivity[False][sname] / 1e6
    print(f"{sname:<18}{v_true:>12.1f}{v_false:>12.1f}{(v_false - v_true):>10.1f}")

# Sweep values sourced in System_Model.py (CONSTRAINT_COST_SWEEP) -- one
# source of truth, not redefined here.
print("\n=== CONSTRAINT_COST sensitivity: ENPV, marginalised MC, NetZero_Tilt weighting, N=500 ===")
print(f"{'Strategy':<18}" + "".join(f"{'£' + str(_cc) + '/MWh':>14}" for _cc in constraint_cost_values))
for sname in Strategies_2:
    print(f"{sname:<18}" + "".join(
        f"{constraint_sensitivity[_cc][sname] / 1e6:>14.1f}" for _cc in constraint_cost_values))

# ---- 11. STAGED_LINK_FIXED_PER_STAGE sensitivity ------------------------
# No real-world figure exists to calibrate this against, so it's swept
# instead of guessed harder. "Flexible 4-Stage" re-runs at every
# fixed_per_stage value, "Flexible 1-Stage" (unaffected) runs once, all on
# the same cached draws -- testing how a phased design's own per-stage cost
# assumption moves its value relative to a non-staged alternative, the same
# question [4] asks of phased PV deployment against a fixed design.
print("\n=== STAGED_LINK_FIXED_PER_STAGE sensitivity: ENPV, marginalised MC, NetZero_Tilt weighting, N=500 ===")
fps_values = STAGED_LINK_FIXED_PER_STAGE_SWEEP

flex_draws_fps = np.empty(N_SENS)
staged_draws_fps = {fp: np.empty(N_SENS) for fp in fps_values}

for i in range(N_SENS):
    capex_mult = _CACHE["draw_capex"][i]
    scenario = _CACHE["draw_scenario"][i]
    wx_seq = _CACHE["draw_wx_seq"][i]
    capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
    demand, price_seq, background_seq = paths_from_stored_z(_CACHE["draw_z"][i], scenario)

    opts_flex = Strategies_Flex["Flexible 1-Stage"](capex_mult)
    flex_draws_fps[i] = Run_Strategy(("Flexible 1-Stage", opts_flex), demand, scenario, wx_seq,
                                      capex_mult, capex_estimate_seq, price_seq, background_seq)[3]

    for fp in fps_values:
        opts_staged = M._flexible_staged(capex_mult, fixed_per_stage=fp)
        staged_draws_fps[fp][i] = Run_Strategy(("Flexible 4-Stage", opts_staged), demand, scenario, wx_seq,
                                                 capex_mult, capex_estimate_seq, price_seq, background_seq)[3]

flex_mean_fps = flex_draws_fps.mean() / 1e6
print(f"{'fixed_per_stage_£m':<20}{'Staged_ENPV_£m':>16}{'Flexible_ENPV_£m':>18}"
      f"{'paired_median_diff':>20}{'frac_staged<flex':>18}")
for fp in fps_values:
    staged = staged_draws_fps[fp]
    diff = (staged - flex_draws_fps) / 1e6
    print(f"{fp/1e6:<20.1f}{staged.mean()/1e6:>16.1f}{flex_mean_fps:>18.1f}"
          f"{np.median(diff):>20.1f}{(diff < 0).mean():>18.2f}")

# ---- 12. STAGED_LINK_THETA sensitivity -----------------------------------
# theta multiplies the Ofgem-scaled background_gen_mw threshold each stage
# 2+ triggers on -- no real basis for a specific value, swept instead of
# guessed harder. Same cache-draw pattern as section 11.
print("\n=== STAGED_LINK_THETA sensitivity: ENPV, marginalised MC, NetZero_Tilt weighting, N=500 ===")
theta_values = STAGED_LINK_THETA_SWEEP

flex_draws_theta = np.empty(N_SENS)
staged_draws_theta = {th: np.empty(N_SENS) for th in theta_values}

for i in range(N_SENS):
    capex_mult = _CACHE["draw_capex"][i]
    scenario = _CACHE["draw_scenario"][i]
    wx_seq = _CACHE["draw_wx_seq"][i]
    capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
    demand, price_seq, background_seq = paths_from_stored_z(_CACHE["draw_z"][i], scenario)

    opts_flex = Strategies_Flex["Flexible 1-Stage"](capex_mult)
    flex_draws_theta[i] = Run_Strategy(("Flexible 1-Stage", opts_flex), demand, scenario, wx_seq,
                                        capex_mult, capex_estimate_seq, price_seq, background_seq)[3]

    for th in theta_values:
        opts_staged = M._flexible_staged(capex_mult, theta=th)
        staged_draws_theta[th][i] = Run_Strategy(("Flexible 4-Stage", opts_staged), demand, scenario, wx_seq,
                                                   capex_mult, capex_estimate_seq, price_seq, background_seq)[3]

flex_mean_theta = flex_draws_theta.mean() / 1e6
print(f"{'theta':<10}{'Staged_ENPV_£m':>16}{'Flexible_ENPV_£m':>18}"
      f"{'paired_median_diff':>20}{'frac_staged<flex':>18}")
for th in theta_values:
    staged = staged_draws_theta[th]
    diff = (staged - flex_draws_theta) / 1e6
    print(f"{th:<10.2f}{staged.mean()/1e6:>16.1f}{flex_mean_theta:>18.1f}"
          f"{np.median(diff):>20.1f}{(diff < 0).mean():>18.2f}")

# ---- 13. LINK_OPEX_RATE sensitivity --------------------------------------
# Link assets read LINK_OPEX_RATE as a plain module global at construction
# time, so mutating Options.LINK_OPEX_RATE before each factory() call takes effect.
print("\n=== LINK_OPEX_RATE sensitivity: ENPV, marginalised MC, NetZero_Tilt weighting, N=500 ===")
opex_values = LINK_OPEX_SWEEP
_orig_link_opex_rate = O.LINK_OPEX_RATE

opex_draws = {rate: {sname: np.empty(N_SENS) for sname in Strategies_2} for rate in opex_values}

for i in range(N_SENS):
    capex_mult = _CACHE["draw_capex"][i]
    scenario = _CACHE["draw_scenario"][i]
    wx_seq = _CACHE["draw_wx_seq"][i]
    capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
    demand, price_seq, background_seq = paths_from_stored_z(_CACHE["draw_z"][i], scenario)

    for sname, factory in Strategies_2.items():
        for rate in opex_values:
            O.LINK_OPEX_RATE = rate
            opts = factory(capex_mult)
            result = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                                   capex_mult, capex_estimate_seq, price_seq, background_seq)
            opex_draws[rate][sname][i] = result[3]
        O.LINK_OPEX_RATE = _orig_link_opex_rate

opex_sensitivity = {rate: {sname: vals.mean() for sname, vals in d.items()}
                     for rate, d in opex_draws.items()}
print(f"{'Strategy':<18}" + "".join(f"{rate:>14.4f}" for rate in opex_values))
for sname in Strategies_2:
    print(f"{sname:<18}" + "".join(
        f"{opex_sensitivity[rate][sname] / 1e6:>14.1f}" for rate in opex_values))

# ---- 14. AVAIL (wake + availability + electrical losses) sensitivity ----
# Unlike LINK_OPEX_RATE, AVAIL is baked into WIND_CF_BY_YEAR once at import
# time, not read fresh per year -- compute_wind_cf_by_year(avail) recomputes
# that dict, swapped in before each draw and restored after.
print("\n=== AVAIL (wake+availability+electrical losses) sensitivity: ENPV, marginalised MC, NetZero_Tilt weighting, N=500 ===")
avail_values = [0.85, M.AVAIL, 0.95]
_orig_wind_cf_by_year = M.WIND_CF_BY_YEAR
wind_cf_by_avail = {av: M.compute_wind_cf_by_year(av) for av in avail_values}

avail_draws = {av: {sname: np.empty(N_SENS) for sname in Strategies_2} for av in avail_values}

for i in range(N_SENS):
    capex_mult = _CACHE["draw_capex"][i]
    scenario = _CACHE["draw_scenario"][i]
    wx_seq = _CACHE["draw_wx_seq"][i]
    capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
    demand, price_seq, background_seq = paths_from_stored_z(_CACHE["draw_z"][i], scenario)

    for sname, factory in Strategies_2.items():
        opts = factory(capex_mult)
        for av in avail_values:
            M.WIND_CF_BY_YEAR = wind_cf_by_avail[av]
            result = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                                   capex_mult, capex_estimate_seq, price_seq, background_seq)
            avail_draws[av][sname][i] = result[3]
    M.WIND_CF_BY_YEAR = _orig_wind_cf_by_year

avail_sensitivity = {av: {sname: vals.mean() for sname, vals in d.items()}
                      for av, d in avail_draws.items()}
print(f"{'Strategy':<18}" + "".join(f"{'AVAIL=' + str(av):>14}" for av in avail_values))
for sname in Strategies_2:
    print(f"{sname:<18}" + "".join(
        f"{avail_sensitivity[av][sname] / 1e6:>14.1f}" for av in avail_values))

# ---- 15. GBM_SHOCK_CORR sensitivity: measured (active) vs placeholder ---
# GBM_SHOCK_CORR is now measured from data, not the original hand-picked
# guess (PLACEHOLDER_CORR_MATRIX) -- this quantifies that swap's ENPV effect.
# Unlike every sweep above, this one changes how the correlated paths are
# drawn, not just how Run_Strategy scores a fixed set of paths -- but it's
# still fully reconstructable from the cache: since draw_z = z_indep @
# L_measured.T and L_measured = cholesky(GBM_SHOCK_CORR) is known,
# z_indep = solve(L_measured, draw_z.T).T recovers the independent shock
# block exactly, then re-correlating that same z_indep under either
# candidate matrix isolates the correlation structure's effect from draw
# noise, without redrawing.
print("\n=== GBM_SHOCK_CORR sensitivity: measured (active) vs placeholder, ENPV, marginalised MC, NetZero_Tilt weighting, N=500 ===")
corr_settings = {"placeholder": PLACEHOLDER_CORR_MATRIX, "measured": M.GBM_SHOCK_CORR}
_L_measured = np.linalg.cholesky(M.GBM_SHOCK_CORR)

def _paths_from_z_indep(z_indep, corr, scenario):
    L = np.linalg.cholesky(corr)
    z = z_indep @ L.T
    return paths_from_stored_z(z, scenario)

corr_draws = {label: {sname: np.empty(N_SENS) for sname in Strategies_2} for label in corr_settings}

for i in range(N_SENS):
    capex_mult = _CACHE["draw_capex"][i]
    scenario = _CACHE["draw_scenario"][i]
    wx_seq = _CACHE["draw_wx_seq"][i]
    capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
    z_indep = np.linalg.solve(_L_measured, _CACHE["draw_z"][i].T).T

    paths = {label: _paths_from_z_indep(z_indep, corr, scenario) for label, corr in corr_settings.items()}

    for sname, factory in Strategies_2.items():
        opts = factory(capex_mult)
        for label, (demand, price_seq, background_seq) in paths.items():
            result = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                                   capex_mult, capex_estimate_seq, price_seq, background_seq)
            corr_draws[label][sname][i] = result[3]

corr_sensitivity = {label: {sname: vals.mean() for sname, vals in d.items()}
                     for label, d in corr_draws.items()}
print(f"{'Strategy':<18}{'placeholder_£m':>16}{'measured_£m':>14}{'delta_£m':>12}")
for sname in Strategies_2:
    v_ph = corr_sensitivity["placeholder"][sname] / 1e6
    v_meas = corr_sensitivity["measured"][sname] / 1e6
    print(f"{sname:<18}{v_ph:>16.1f}{v_meas:>14.1f}{(v_meas - v_ph):>12.1f}")

# ---- 17. CAPEX_P90 breakeven: how much would cost-overrun tail risk ----
# ---- need to shrink for commitment to reliably beat Do Nothing? --------
# CAPEX_P90 is anchored to a single data point (SSEN's Sept 2024
# Orkney-Caithness contract announcement -- a floor, not a realised outturn).
# Do Nothing came out competitive with, and often ahead of, the rigid
# strategies in the headline MC -- this asks how sensitive that is to
# CAPEX_P90 specifically, holding CAPEX_MEDIAN (1.4x, itself unsourced)
# fixed. Reuses the cache's scenario/wx_seq/z (index-paired with every other
# sweep in this file) and reconstructs z_capex by inverting the stored
# capex_mult, so this section is paired-draw-consistent with the rest of the
# file (its numbers differ from an earlier pre-refactor version that used an
# out-of-step draw order -- a deliberate change, not a bug).
print("\n=== CAPEX_P90 breakeven vs Do Nothing, marginalised MC, NetZero_Tilt weighting, N=500 ===")
CAPEX_SWEEP_STRATS = list(ALL_STRATEGIES.keys())   # Do Nothing + Baseline + Staged + Flexible + Flexible 4-Stage + Flexible 1-Stage (Cost-Aware)
_capex_mu_fixed = np.log(M.CAPEX_MEDIAN)
p90_values = sorted({1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5, 4.0, round(M.CAPEX_P90, 2)})

p90_draws = {p90: {s: np.empty(N_SENS) for s in CAPEX_SWEEP_STRATS} for p90 in p90_values}

for i in range(N_SENS):
    scenario = _CACHE["draw_scenario"][i]
    wx_seq = _CACHE["draw_wx_seq"][i]
    demand, price_seq, background_seq = paths_from_stored_z(_CACHE["draw_z"][i], scenario)
    z_capex = (np.log(_CACHE["draw_capex"][i]) - _CACHE["capex_mu"]) / _CACHE["capex_sigma"]
    _noise_ratio = _CACHE["draw_capex_estimate_seq"][i] / _CACHE["draw_capex"][i]

    for p90 in p90_values:
        sigma = (np.log(p90) - _capex_mu_fixed) / 1.2816
        capex_mult = float(np.exp(_capex_mu_fixed + sigma * z_capex))
        capex_estimate_seq = capex_mult * _noise_ratio
        for sname in CAPEX_SWEEP_STRATS:
            opts = ALL_STRATEGIES[sname](capex_mult)
            result = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                                   capex_mult, capex_estimate_seq, price_seq, background_seq)
            p90_draws[p90][sname][i] = result[3]

p90_enpv = {p90: {s: p90_draws[p90][s].mean() for s in CAPEX_SWEEP_STRATS} for p90 in p90_values}

print(f"{'CAPEX_P90':<12}" + "".join(f"{s:>16}" for s in CAPEX_SWEEP_STRATS))
for p90 in p90_values:
    row = "".join(f"{p90_enpv[p90][s] / 1e6:>16.0f}" for s in CAPEX_SWEEP_STRATS)
    marker = "  <- current" if abs(p90 - M.CAPEX_P90) < 1e-6 else ""
    print(f"{p90:<12.2f}{row}{marker}")

print("\nBreakeven CAPEX_P90 (strategy ENPV crosses Do Nothing's ENPV):")
p90_arr = np.array(p90_values)
gaps = {}
for sname in TARGET_STRATEGIES:
    gap = np.array([p90_enpv[p90][sname] - p90_enpv[p90]["Do Nothing"] for p90 in p90_values]) / 1e6
    gaps[sname] = gap
    c = crossover(p90_arr, gap)
    current_edge = gap[p90_values.index(round(M.CAPEX_P90, 2))]
    print(f"  {TARGET_LABELS[sname]:<18}: " + (f"crosses at P90={c:.2f}x" if c is not None else "no crossing in swept range")
          + f"  (edge at current P90={M.CAPEX_P90:.2f}x: £{current_edge:.0f}m)")

fig, ax = plt.subplots(figsize=(7.5, 4.5))
for sname, col in zip(PLOT_STRATEGIES, palette):
    ax.plot(p90_arr, gaps[sname], lw=2, marker="o", color=col, label=TARGET_LABELS[sname])
    c = crossover(p90_arr, gaps[sname])
    if c is not None:
        ax.plot(c, 0, "o", color=col, zorder=5, markerfacecolor="white", markeredgewidth=2)
        ax.annotate(f"{c:.2f}x", (c, 0), color=col, textcoords="offset points", xytext=(6, 8))
ax.axhline(0, color="grey", lw=0.8)
ax.axvline(M.CAPEX_P90, color="firebrick", ls="--", lw=1, label=f"current calibration ({M.CAPEX_P90:.2f}x)")
ax.set_xlabel("CAPEX_P90 assumption (link cost-overrun multiplier, 90th percentile)")
ax.set_ylabel("ΔENPV vs Do Nothing, £m")
ax.set_title("Cost-overrun tail-risk breakeven: ENPV edge over Do Nothing vs CAPEX_P90\n"
             f"(N={N_SENS}, NetZero_Tilt weighting, CAPEX_MEDIAN=1.4x held fixed)", fontsize=11)
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(os.path.join(SENSITIVITIES_PLOTS_DIR, "capex_p90_breakeven.png"), dpi=200)
plt.close(fig)

# ---- 18. Cost-aware Main Link: does gating on the noisy early capex -----
# ---- estimate add value ON TOP OF the existing demand-only trigger? -----
# Demand/price/background GBM volatility, not capex overrun, was found to be
# the dominant driver of Baseline's underperformance vs Do Nothing. This asks
# the natural follow-up for "Flexible 1-Stage" (already demand-aware): does
# also gating the build decision on the noisy early capex_mult estimate
# capture further incremental value, or is demand-awareness already doing
# the useful work? cost_cap has no real-world anchor, so it's swept rather
# than guessed; 10.0 is a de facto "unconstrained" control (above virtually
# every realisable capex_estimate draw, so the AND-gate never blocks --
# should reproduce plain "Flexible 1-Stage" almost exactly).
print("\n=== Cost-aware Main Link (cost_cap sweep) vs Flexible vs Do Nothing: "
      "ENPV, marginalised MC, NetZero_Tilt weighting, N=500 ===")
cost_cap_values = [1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.5, 3.0, 10.0]

flex_draws_ca = np.empty(N_SENS)
dn_draws_ca = np.empty(N_SENS)
ca_draws = {cc: np.empty(N_SENS) for cc in cost_cap_values}
ca_fired = {cc: np.zeros(N_SENS, dtype=bool) for cc in cost_cap_values}
ca_build_year = {cc: np.full(N_SENS, np.nan) for cc in cost_cap_values}

for i in range(N_SENS):
    capex_mult = _CACHE["draw_capex"][i]
    scenario = _CACHE["draw_scenario"][i]
    wx_seq = _CACHE["draw_wx_seq"][i]
    capex_estimate_seq = _CACHE["draw_capex_estimate_seq"][i]
    demand, price_seq, background_seq = paths_from_stored_z(_CACHE["draw_z"][i], scenario)

    opts_flex = Strategies_Flex["Flexible 1-Stage"](capex_mult)
    flex_draws_ca[i] = Run_Strategy(("Flexible 1-Stage", opts_flex), demand, scenario, wx_seq,
                                     capex_mult, capex_estimate_seq, price_seq, background_seq)[3]
    dn_draws_ca[i] = Run_Strategy(("Do Nothing", do_nothing(capex_mult)), demand, scenario, wx_seq,
                                   capex_mult, capex_estimate_seq, price_seq, background_seq)[3]

    for cc in cost_cap_values:
        opts_ca = M._flexible_cost_aware(capex_mult, cost_cap=cc)
        result = Run_Strategy(("Flexible 1-Stage (Cost-Aware)", opts_ca), demand, scenario, wx_seq,
                               capex_mult, capex_estimate_seq, price_seq, background_seq)
        ca_draws[cc][i] = result[3]
        rlog = result[5]["Main Link"]
        ca_fired[cc][i] = rlog["fired"]
        if rlog["fired"]:
            ca_build_year[cc][i] = rlog["build_year"]

flex_mean_ca = flex_draws_ca.mean() / 1e6
dn_mean_ca = dn_draws_ca.mean() / 1e6
print(f"{'cost_cap':<10}{'CostAware_ENPV':>16}{'Flexible_ENPV':>16}{'DoNothing_ENPV':>16}"
      f"{'paired_vs_Flex':>16}{'paired_vs_DN':>14}{'never_fired':>13}{'mean_build_yr':>15}")
for cc in cost_cap_values:
    ca = ca_draws[cc]
    diff_flex = (ca - flex_draws_ca) / 1e6
    diff_dn = (ca - dn_draws_ca) / 1e6
    never = 1 - ca_fired[cc].mean()
    mean_by = np.nanmean(ca_build_year[cc])
    print(f"{cc:<10.2f}{ca.mean()/1e6:>16.1f}{flex_mean_ca:>16.1f}{dn_mean_ca:>16.1f}"
          f"{diff_flex.mean():>16.1f}{diff_dn.mean():>14.1f}{never:>13.1%}{mean_by:>15.1f}")

print("(paired_vs_Flex = mean(CostAware - Flexible) on identical draws -- positive means "
      "cost-awareness adds value on top of the existing demand-only trigger. paired_vs_DN = "
      "mean(CostAware - Do Nothing). never_fired = fraction of draws where Main Link never fires "
      "by the 2051 deadline. mean_build_yr excludes never-fired draws.)")
