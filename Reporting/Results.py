# Reporting and plotting. Run this, not System_Model.py.
# References [3],[4]: see docs/notes/Reporting/Results.md#references

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import matplotlib.pyplot as plt
import pickle
from datetime import datetime, timezone

import Model.System_Model as M
import Model.Options as O
from Model.System_Model import Run_Strategy, Strategies_2, Strategies_Flex, Scenarios
from Model.Model_Components import Decision
from Model.Options import NewLink, Stage1_Wind_Buildout, Stage2_Wind_Buildout
from Model.Decision_Rules import MAIN_LINK_BG_GEN_THRESHOLD as _BG_THRESH

# All plots this file produces are saved here (tables/CSVs are unaffected --
# see PNZ_TABLE_DIR below, which stays where it was).
RESULTS_PLOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Results_Plots")
os.makedirs(RESULTS_PLOTS_DIR, exist_ok=True)

# Waterfall/CVaR plots (added below) go alongside the scenario-discovery
# headline plots per explicit instruction, not into RESULTS_PLOTS_DIR.
SCENARIO_DISCOVERY_PLOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                             "ScenarioDiscovery", "Main_Plots")
os.makedirs(SCENARIO_DISCOVERY_PLOTS_DIR, exist_ok=True)

# ---- shared chart style ----------------------------------------------------
# see docs/notes/Reporting/Results.md#shared-chart-style
INK = "#0b0b0b"            # primary text
INK_SECONDARY = "#52514e"  # axis labels
INK_MUTED = "#898781"      # ticks
GRIDLINE = "#e1e0d9"       # hairline gridlines
AXIS_LINE = "#c3c2b7"      # kept spines (left/bottom)
SURFACE = "#fcfcfb"        # chart background

# Fixed hue order rationale: see docs/notes/Reporting/Results.md#categorical-palette-fixed-hue-order-rationale
CATEGORICAL = ["#2a78d6", "#eb6834", "#1b7e5d", "#b41e91",
               "#756f17", "#008300", "#4a3aa7", "#e34948"]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": AXIS_LINE,
    "axes.labelcolor": INK_SECONDARY,
    "axes.labelsize": 10,
    "text.color": INK,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.frameon": False,
    "legend.fontsize": 9.5,
    "savefig.facecolor": SURFACE,
    "savefig.dpi": 200,
})


def _style_ax(ax, grid_axis="y"):
    # Recessive chrome: no top/right box, hairline left/bottom spines, a
    # muted gridline behind the data (never in front, never dashed).
    ax.set_facecolor(SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(AXIS_LINE)
        ax.spines[spine].set_linewidth(0.8)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    if grid_axis:
        ax.grid(axis=grid_axis, color=GRIDLINE, lw=0.8, zorder=0)
        ax.set_axisbelow(True)
    return ax


def _titled(ax, title, subtitle=None, fontsize=12.5):
    # see docs/notes/Reporting/Results.md#_titled-headline-and-subtitle-styling
    ax.set_title(title, fontsize=fontsize, fontweight="bold", color=INK,
                 loc="left", pad=16 if subtitle else 8)
    if subtitle:
        ax.text(0.0, 1.02, subtitle, transform=ax.transAxes, ha="left", va="bottom",
                 fontsize=9, color=INK_SECONDARY)


RUN_MC = True   # False skips every Monte Carlo section below for quick iteration

# see docs/notes/Reporting/Results.md#mc_cache_path-purpose-and-scope
MC_CACHE_PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                  "Methodology_4/Coding/Extra/MC_Cache/headline_mc.pkl")

# see docs/notes/Reporting/Results.md#_do_nothing-role-as-zero-build-reference-case
def _do_nothing(capex_mult=1.0):
    return [Decision(NewLink(capex_mult), None),
            Decision(Stage1_Wind_Buildout(), None),
            Decision(Stage2_Wind_Buildout(), None)]

if RUN_MC:
    palette = CATEGORICAL[:5]   # fixed hue order -- see shared chart style above

    # ---- helpers used by the new sections below -----------------------------

    # see docs/notes/Reporting/Results.md#initial_year_capex-definition-and-scope
    def initial_year_capex(factory):
        opts = factory(1.0)
        decisions = [d for d in opts if isinstance(d, Decision) and d.BuildYear() is not None]
        if not decisions:
            return 0.0
        first_year = min(d.BuildYear() for d in decisions)
        return sum(d.Asset().Capex() for d in decisions if d.BuildYear() == first_year)

    # see docs/notes/Reporting/Results.md#_paths_from_stored_z-purpose-and-design
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

    # see docs/notes/Reporting/Results.md#run_marginalised-design-and-rationale
    def run_marginalised(weights, seed=42, n=2000, strategies=None):
        if strategies is None:
            strategies = Strategies_2
        rng = np.random.default_rng(seed)
        scen_names = list(weights.keys())
        scen_probs = list(weights.values())

        store = {sname: np.empty(n) for sname in strategies}
        cost_store = {sname: np.empty(n) for sname in strategies}
        energy_store = {sname: np.empty(n) for sname in strategies}
        # see docs/notes/Reporting/Results.md#run_marginalised-curtailment-and-lcot-store-rationale
        curtail_store = {sname: np.empty(n) for sname in strategies}
        gen_total_store = {sname: np.empty(n) for sname in strategies}
        link_cost_store = {sname: np.empty(n) for sname in strategies}
        link_export_store = {sname: np.empty(n) for sname in strategies}
        rule_log_store = {sname: {} for sname in strategies if sname in Strategies_Flex}
        draw_capex = np.empty(n)
        draw_scenario = np.empty(n, dtype=object)
        draw_wx_seq = np.empty((n, len(M.YEARS)), dtype=object)
        draw_capex_estimate_seq = np.empty((n, len(M.YEARS)))
        draw_z = np.empty((n, len(M.YEARS), 3))

        for i in range(n):
            capex_mult = rng.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA)     # 1st: capex
            scenario = rng.choice(scen_names, p=scen_probs)            # 2nd: scenario
            wx_seq = M.sample_wx_seq(rng, len(M.YEARS))                # 3rd: weather (WX_MODE)
            capex_estimate_seq = M.sample_capex_estimate_seq(rng, capex_mult, len(M.YEARS))  # 4th: noisy early cost estimate
            z = M.sample_correlated_gbm_shocks(rng, len(M.YEARS))      # 5th: correlated demand/price/background shock block
            demand, price_seq, background_seq = _paths_from_stored_z(z, scenario)
            draw_capex[i] = capex_mult
            draw_scenario[i] = scenario
            draw_wx_seq[i] = wx_seq
            draw_capex_estimate_seq[i] = capex_estimate_seq
            draw_z[i] = z

            for sname, factory in strategies.items():
                opts = factory(capex_mult)
                result = Run_Strategy((sname, opts), demand, scenario, wx_seq,
                                       capex_mult, capex_estimate_seq, price_seq, background_seq)
                store[sname][i] = result[3]
                cost_store[sname][i] = result[0]
                energy_store[sname][i] = result[1]
                curtail_store[sname][i] = result[2]
                _state = result[4]
                gen_total_store[sname][i] = _state["gen_total"].sum() / 1000   # MWh -> GWh, undiscounted
                link_cost_store[sname][i] = _state["link_cost_total"]
                link_export_store[sname][i] = _state["pv_link_export_gwh"]
                if sname in rule_log_store:
                    for rname, info in result[5].items():
                        rule_log_store[sname].setdefault(rname, []).append(info)

        raw_draws = {"wx_seq": draw_wx_seq, "capex_estimate_seq": draw_capex_estimate_seq, "z": draw_z}
        return (store, draw_capex, draw_scenario, rule_log_store, cost_store, energy_store,
                curtail_store, gen_total_store, link_cost_store, link_export_store, raw_draws)

    # see docs/notes/Reporting/Results.md#sixsigma_xlim-robust-bounds-rationale
    def sixsigma_xlim(pooled_vals):
        med = np.median(pooled_vals)
        mad = np.median(np.abs(pooled_vals - med))
        robust_sigma = 1.4826 * mad
        lo = max(pooled_vals.min(), med - 6 * robust_sigma)
        hi = min(pooled_vals.max(), med + 6 * robust_sigma)
        return lo, hi

    # see docs/notes/Reporting/Results.md#lcoe_from_stores-dominance-exclusion-rationale
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


    # ---- 2. marginalised Monte Carlo (headline), NetZero_Tilt weighting ----
    # see docs/notes/Reporting/Results.md#section-2-marginalised-mc-setup-rationale
    ALL_STRATEGIES = {"Do Nothing": _do_nothing, **Strategies_2, **Strategies_Flex}
    # see docs/notes/Reporting/Results.md#target_strategies-and-target_labels-purpose
    TARGET_STRATEGIES = ["Baseline", "Fixed 4-Stage", "Flexible 4-Stage",
                         "Flexible 1-Stage (Cost-Aware)", "Flexible 1-Stage"]
    TARGET_LABELS = {s: s for s in TARGET_STRATEGIES}
    # see docs/notes/Reporting/Results.md#plot_strategies-scope-and-colour-lookup
    PLOT_STRATEGIES = [s for s in TARGET_STRATEGIES if s != "Flexible 1-Stage (Cost-Aware)"]
    TARGET_COLORS = dict(zip(TARGET_STRATEGIES, palette))

    (marg_store, draw_capex, draw_scenario, marg_rule_log, marg_cost, marg_energy,
     marg_curtail, marg_gen_total, marg_link_cost, marg_link_export, marg_raw_draws) = run_marginalised(
        M.SCENARIO_WEIGHTS["NetZero_Tilt"], n=2000, strategies=ALL_STRATEGIES)

    print_metrics_table(marg_store, "NetZero_Tilt (rigid + flexible)", ALL_STRATEGIES)

    # ---- value-of-flexibility waterfall (additive, new) ---------------------
    # 2x2 design: staging (1-stage vs 4-stage) x optionality (rigid vs flexible).
    # Source: marg_store (dict[str, np.ndarray], plain strategy-name keys, raw £,
    # paired draws) -- NOT mc_draws.csv-style npv_* columns, per corrected
    # instruction. Weighting: plain .mean()/np.percentile() on marg_store arrays
    # only -- NetZero_Tilt is already embedded via the scenario sampling at
    # line 147 (rng.choice(scen_names, p=scen_probs)), so this stays consistent
    # with print_metrics_table's ENPV above without any reweighting step.
    def compute_and_plot_flexibility_waterfall(marg_store, out_dir):
        B, F, X1, X4 = (marg_store["Baseline"], marg_store["Fixed 4-Stage"],
                         marg_store["Flexible 1-Stage"], marg_store["Flexible 4-Stage"])
        enpv_B, enpv_F, enpv_X1, enpv_X4 = B.mean(), F.mean(), X1.mean(), X4.mean()  # raw £

        print("\n=== Value-of-flexibility 2x2 ENPV grid (£m, NetZero_Tilt) ===")
        print(f"{'':<12}{'1-stage':>14}{'4-stage':>14}")
        print(f"{'rigid':<12}{enpv_B/1e6:>14.1f}{enpv_F/1e6:>14.1f}")
        print(f"{'flexible':<12}{enpv_X1/1e6:>14.1f}{enpv_X4/1e6:>14.1f}")

        total_premium = enpv_X4 - enpv_B
        staging_first = [("Fixed - Baseline (staging, at rigid)", enpv_F - enpv_B),
                          ("Flex4 - Fixed (optionality, at 4-stage)", enpv_X4 - enpv_F)]
        optionality_first = [("Flex1 - Baseline (optionality, at 1-stage)", enpv_X1 - enpv_B),
                              ("Flex4 - Flex1 (staging, at flexible)", enpv_X4 - enpv_X1)]
        interaction = enpv_X4 - enpv_F - enpv_X1 + enpv_B

        print("\n=== Decomposition paths (£m) ===")
        print("Staging-first: Baseline -> Fixed 4-Stage -> Flexible 4-Stage")
        for label, v in staging_first:
            print(f"  {label}: {v/1e6:+.2f}")
        print(f"  path total: {sum(v for _, v in staging_first)/1e6:+.2f}")
        print("Optionality-first: Baseline -> Flexible 1-Stage -> Flexible 4-Stage")
        for label, v in optionality_first:
            print(f"  {label}: {v/1e6:+.2f}")
        print(f"  path total: {sum(v for _, v in optionality_first)/1e6:+.2f}")
        print(f"\nInteraction (non-additivity) = Flex4 - Fixed - Flex1 + Baseline = £{interaction/1e6:+.2f}m")

        # Shapley (exact for 2 factors): each factor's effect = mean of its
        # marginal contribution across both orderings.
        shapley_staging = ((enpv_F - enpv_B) + (enpv_X4 - enpv_X1)) / 2
        shapley_optionality = ((enpv_X1 - enpv_B) + (enpv_X4 - enpv_F)) / 2
        shapley_sum = shapley_staging + shapley_optionality

        print("\n=== Shapley decomposition (£m) ===")
        print(f"  staging_effect (Shapley)     = £{shapley_staging/1e6:+.2f}m")
        print(f"  optionality_effect (Shapley) = £{shapley_optionality/1e6:+.2f}m")
        print(f"  sum of Shapley effects       = £{shapley_sum/1e6:+.2f}m")
        print(f"  total premium (Flex4-Baseline) = £{total_premium/1e6:+.2f}m")
        assert abs(shapley_sum - total_premium) < 1e-6, \
            "Shapley staging+optionality should sum EXACTLY to total premium for 2 factors"

        # Why the waterfall below has 2 additive bars, not 3: for exactly 2
        # factors, Shapley splits the interaction 50/50 into both main effects
        # already -- shapley_staging + shapley_optionality == total_premium
        # exactly (assertion above). Stacking the raw `interaction` term on top
        # of BOTH Shapley bars as a third additive segment would therefore
        # overshoot the true Flex4 ENPV by one full interaction term (double-
        # counting it). This is the "(or two Shapley values summing exactly to
        # total premium)" framing offered alongside the original spec's 3-bar
        # description -- taking it because the literal 3-bar version doesn't
        # close. The interaction is still shown, not hidden: as a caption on
        # the chart and printed above, quantifying how much of each Shapley
        # bar is "really" cross-term rather than a pure main effect.
        enpv_B_m, enpv_X4_m = enpv_B / 1e6, enpv_X4 / 1e6
        shap_stage_m, shap_opt_m = shapley_staging/1e6, shapley_optionality/1e6

        fig, ax = plt.subplots(figsize=(8.5, 5.8), facecolor=SURFACE)
        # Reverted to spaced-out bars (not touching), but way thinner than the
        # matplotlib default (0.8) -- and the connecting dashed lines are back,
        # in a higher-contrast colour than the original AXIS_LINE grey.
        x = np.arange(4)
        bar_width = 0.5
        labels = ["Baseline\nENPV", "+ staging effect\n(Shapley)",
                  "+ optionality effect\n(Shapley)", "Flexible 4-Stage\nENPV"]

        ax.bar(x[0], enpv_B_m, width=bar_width, color=INK_MUTED, zorder=2)
        ax.bar(x[1], shap_stage_m, width=bar_width, bottom=enpv_B_m, color=CATEGORICAL[0], zorder=2)
        ax.bar(x[2], shap_opt_m, width=bar_width, bottom=enpv_B_m + shap_stage_m, color=CATEGORICAL[1], zorder=2)
        ax.bar(x[3], enpv_X4_m, width=bar_width, color=INK, zorder=2)

        ax.plot([x[0], x[1]], [enpv_B_m, enpv_B_m], color=INK_SECONDARY, lw=1.3, ls="--", zorder=1)
        ax.plot([x[1], x[2]], [enpv_B_m + shap_stage_m] * 2, color=INK_SECONDARY, lw=1.3, ls="--", zorder=1)
        ax.plot([x[2], x[3]], [enpv_X4_m, enpv_X4_m], color=INK_SECONDARY, lw=1.3, ls="--", zorder=1)

        for xi, y, txt in [(x[0], enpv_B_m, f"£{enpv_B_m:.0f}m"),
                           (x[1], enpv_B_m + shap_stage_m, f"£{shap_stage_m:+.0f}m"),
                           (x[2], enpv_X4_m, f"£{shap_opt_m:+.0f}m"),
                           (x[3], enpv_X4_m, f"£{enpv_X4_m:.0f}m")]:
            ax.annotate(txt, (xi, y), textcoords="offset points", xytext=(0, 5),
                        ha="center", fontsize=9.5, color=INK, fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("ENPV, £m")
        _titled(ax, "Value of flexibility -- Shapley decomposition of Flexible 4-Stage's ENPV premium",
                "Staging x optionality, NetZero_Tilt weighting")
        _style_ax(ax)

        # ASCII "->" not unicode "→": Helvetica Neue (this file's savefig
        # font) is missing the arrow glyph and silently drops it, not fine to render.
        caption = (f"Staging-first: Baseline->Fixed {(enpv_F-enpv_B)/1e6:+.0f}m->Flex4 {(enpv_X4-enpv_F)/1e6:+.0f}m   |   "
                   f"Optionality-first: Baseline->Flex1 {(enpv_X1-enpv_B)/1e6:+.0f}m->Flex4 {(enpv_X4-enpv_X1)/1e6:+.0f}m   |   "
                   f"Interaction = £{interaction/1e6:+.1f}m (already split into both Shapley bars above)")
        fig.text(0.5, -0.03, caption, ha="center", fontsize=7.5, color=INK_MUTED, wrap=True)
        fig.tight_layout()

        path = os.path.join(out_dir, "value_of_flexibility_waterfall.png")
        fig.savefig(path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        return path

    waterfall_path = compute_and_plot_flexibility_waterfall(marg_store, SCENARIO_DISCOVERY_PLOTS_DIR)
    print(f"\nValue-of-flexibility waterfall -> {waterfall_path}")

    # ---- CVaR / Expected Shortfall (additive, new) ---------------------------
    def compute_and_plot_cvar(marg_store, out_dir):
        cvar_strategies = ["Baseline", "Fixed 4-Stage", "Flexible 1-Stage", "Flexible 4-Stage"]
        print("\n=== VaR / CVaR (Expected Shortfall), NetZero_Tilt weighting (£m) ===")
        print(f"{'Strategy':<20}{'ENPV':>9}{'VaR5':>9}{'CVaR5':>9}{'VaR10':>9}{'CVaR10':>9}")
        cvar5_by_strategy = {}
        for sname in cvar_strategies:
            v = marg_store[sname]   # raw £, paired draws
            enpv = v.mean()
            var5 = np.percentile(v, 5)
            cvar5 = v[v <= var5].mean()
            var10 = np.percentile(v, 10)
            cvar10 = v[v <= var10].mean()
            cvar5_by_strategy[sname] = cvar5
            print(f"{sname:<20}{enpv/1e6:>9.0f}{var5/1e6:>9.0f}{cvar5/1e6:>9.0f}{var10/1e6:>9.0f}{cvar10/1e6:>9.0f}")
        print("(VaR5/VaR10 = 5th/10th percentile of paired NPV. CVaR5/CVaR10 = mean NPV of draws "
              "at or below that percentile -- expected shortfall in the worst 5%/10% of outcomes.)")

        fig, ax = plt.subplots(figsize=(7, 4.8), facecolor=SURFACE)
        x = np.arange(len(cvar_strategies))
        heights_m = [cvar5_by_strategy[s] / 1e6 for s in cvar_strategies]
        bar_colors = [CATEGORICAL[i] for i in range(len(cvar_strategies))]
        ax.bar(x, heights_m, color=bar_colors, zorder=2)
        for xi, h in zip(x, heights_m):
            ax.annotate(f"£{h:.0f}m", (xi, h), textcoords="offset points",
                        xytext=(0, 5 if h >= 0 else -15), ha="center", fontsize=9.5, fontweight="bold")
        ax.axhline(0, color=AXIS_LINE, lw=0.8, zorder=1)
        ax.set_xticks(x)
        ax.set_xticklabels(cvar_strategies, fontsize=9)
        ax.set_ylabel("CVaR @ 5%, £m")
        _titled(ax, "Tail risk by strategy -- CVaR (Expected Shortfall) at 5%",
                "Mean NPV of the worst 5% of paired draws, NetZero_Tilt weighting")
        _style_ax(ax)
        fig.tight_layout()

        path = os.path.join(out_dir, "cvar_by_strategy.png")
        fig.savefig(path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        return path

    cvar_path = compute_and_plot_cvar(marg_store, SCENARIO_DISCOVERY_PLOTS_DIR)
    print(f"CVaR chart -> {cvar_path}")

    # ---- persist the headline draws for Scenario_Discovery.py/Sensitivities.py
    # see docs/notes/Reporting/Results.md#persisting-the-headline-mc-cache
    import os as _os
    _os.makedirs(_os.path.dirname(MC_CACHE_PATH), exist_ok=True)
    with open(MC_CACHE_PATH, "wb") as _f:
        pickle.dump({
            "seed": 42, "n": 2000, "weighting": "NetZero_Tilt",
            "years": M.YEARS,
            "draw_capex": draw_capex, "draw_scenario": draw_scenario,
            "draw_wx_seq": marg_raw_draws["wx_seq"],
            "draw_capex_estimate_seq": marg_raw_draws["capex_estimate_seq"],
            "draw_z": marg_raw_draws["z"],
            "capex_mu": M.CAPEX_MU, "capex_sigma": M.CAPEX_SIGMA,
            "marg_store": marg_store, "marg_cost": marg_cost, "marg_energy": marg_energy,
            "marg_curtail": marg_curtail, "marg_gen_total": marg_gen_total,
            "marg_link_cost": marg_link_cost, "marg_link_export": marg_link_export,
            "marg_rule_log": marg_rule_log,
            # see docs/notes/Reporting/Results.md#mc-cache-provenance-stamp-rationale
            "metadata": {
                "INCLUDE_WIND_BUILDOUT": M.INCLUDE_WIND_BUILDOUT,
                "WIND_AS_OPTION": M.WIND_AS_OPTION,
                "n": 2000,
                "seed": 42,
                "RATE": M.RATE,
                "generated_utc": datetime.now(timezone.utc).isoformat(),
            },
        }, _f)
    print(f"\n(headline MC cache written to {MC_CACHE_PATH})")

    # ---- optional: scenario discovery capture layer (gated, additive) ------
    # see docs/notes/Reporting/Results.md#scenario-discovery-capture-layer-gating-and-scope
    if M.SCENARIO_DISCOVERY:
        import pandas as _pd

        # ---- path -> scalar summaries -------------------------------------
        # see docs/notes/Reporting/Results.md#scenario-discovery-path-to-scalar-summary-approach

        # see docs/notes/Reporting/Results.md#scenario-discovery-wind_cf_proxy_mean-derivation
        _wind_cf_proxy = np.array([
            np.mean([M._year_means[y] for y in _wx]) for _wx in marg_raw_draws["wx_seq"]
        ])

        # see docs/notes/Reporting/Results.md#scenario-discovery-capex_estimate_year0-derivation
        _capex_estimate_year0 = marg_raw_draws["capex_estimate_seq"][:, 0]

        # see docs/notes/Reporting/Results.md#scenario-discovery-terminal-year-path-summaries
        _n = len(draw_capex)
        _demand_terminal = np.empty(_n)
        _price_terminal = np.empty(_n)
        _bg_terminal_mw = np.full(_n, np.nan)
        # see docs/notes/Reporting/Results.md#scenario-discovery-year_bg135_raw_crossed-proxy
        _year_bg135 = np.full(_n, np.nan)
        _years_arr = np.array(M.YEARS)
        for _i in range(_n):
            _demand, _price_seq, _bg_seq = _paths_from_stored_z(marg_raw_draws["z"][_i], draw_scenario[_i])
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

        # see docs/notes/Reporting/Results.md#scenario-discovery-scenario-column-encoding

        # ---- assemble the experiments table: one row per draw -------------
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

        # see docs/notes/Reporting/Results.md#scenario-discovery-incremental-lcoe-column
        _marg_lcoe, _ = lcoe_from_stores(marg_cost, marg_energy, ALL_STRATEGIES)
        for _sname, _vals in _marg_lcoe.items():
            _colname = "lcoe_" + _sname.lower().replace(" ", "_").replace("-", "_")
            _cols[_colname] = _vals

        _experiments = _pd.DataFrame(_cols)
        _sd_dir = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                   "Methodology_4/Coding/Reporting/ScenarioDiscovery/Extra")
        _os.makedirs(_sd_dir, exist_ok=True)
        _sd_csv_path = _os.path.join(_sd_dir, "mc_draws.csv")
        _experiments.to_csv(_sd_csv_path, index=False)
        print(f"\n(scenario discovery experiments table written to {_sd_csv_path}, "
              f"{len(_experiments)} rows x {len(_experiments.columns)} columns)")

    # ---- target curves: absolute NPV, the 4 headline strategies ------------
    # see docs/notes/Reporting/Results.md#target-curves-absolute-npv-rationale
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    _style_ax(ax)
    for sname in PLOT_STRATEGIES:
        vals = marg_store[sname]
        xs = np.sort(vals) / 1e6
        ys = np.arange(1, len(xs) + 1) / len(xs)
        ax.plot(xs, ys, lw=2, color=TARGET_COLORS[sname], label=TARGET_LABELS[sname], zorder=3)
    ax.set_xlabel("NPV, £m")
    ax.set_ylabel("Cumulative probability")
    _titled(ax, "Target curves — absolute NPV",
            f"Marginalised over capex & DFES scenario (N={len(draw_capex)}, NetZero_Tilt weighting)")
    ax.legend(loc="lower right")
    # see docs/notes/Reporting/Results.md#target-curves-x-axis-cropping
    _npv_pooled = np.concatenate([marg_store[s] / 1e6 for s in PLOT_STRATEGIES])
    ax.set_xlim(*sixsigma_xlim(_npv_pooled))
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS_PLOTS_DIR, "target_curves_marginalised.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)

    # see docs/notes/Reporting/Results.md#pnz-2025-results-presentation-methods-overview
    PNZ_OUT_DIR = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                   "Methodology_4/Coding/Extra/PNZ2025_Presentation")
    PNZ_FIG_DIR = RESULTS_PLOTS_DIR   # plots -> Results_Plots/, tables stay under PNZ_OUT_DIR
    PNZ_TABLE_DIR = os.path.join(PNZ_OUT_DIR, "tables")
    os.makedirs(PNZ_TABLE_DIR, exist_ok=True)

    # see docs/notes/Reporting/Results.md#pnz-strategy-name-mapping
    PNZ_BASELINE = "Baseline"
    PNZ_STAGED = "Fixed 4-Stage"
    PNZ_FLEXIBLE = "Flexible 1-Stage"
    PNZ_FLEXIBLE_CA = "Flexible 1-Stage (Cost-Aware)"

    def assert_paired_draws(strategies, store=None):
        # see docs/notes/Reporting/Results.md#assert_paired_draws-purpose
        store = store if store is not None else marg_store
        n_expected = len(draw_capex)
        lengths = {s: len(store[s]) for s in strategies}
        bad = {s: n for s, n in lengths.items() if n != n_expected}
        if bad:
            raise AssertionError(
                f"UNPAIRED DRAWS -- aborting, not proceeding with any ΔNPV/CDF-overlay "
                f"plot. Strategy array lengths {bad} don't match draw_capex's length "
                f"({n_expected}), so a shared per-draw index can't be assumed for: "
                f"{strategies}.")
        return n_expected

    # ---- 3. Cost/input distribution histogram (their Fig. 3 analogue) ------
    def plot_capex_distribution():
        # see docs/notes/Reporting/Results.md#plot_capex_distribution-choice-of-input
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        _style_ax(ax)
        ax.hist(draw_capex, bins=40, color=CATEGORICAL[0], edgecolor=SURFACE,
                 linewidth=0.8, zorder=3)
        ax.axvline(M.CAPEX_MEDIAN, color=INK_SECONDARY, ls="--", lw=1.4,
                   label=f"median = {M.CAPEX_MEDIAN:.2f}x")
        ax.axvline(M.CAPEX_P90, color=CATEGORICAL[7], ls="--", lw=1.4,
                   label=f"P90 = {M.CAPEX_P90:.2f}x")
        ax.set_xlabel("Link capex cost-overrun multiplier (draw_capex)")
        ax.set_ylabel("Draws")
        _titled(ax, "Cost-input distribution — link capex multiplier",
                f"Lognormal draws feeding the headline MC (N={len(draw_capex)}, seed=42)")
        ax.legend()
        fig.tight_layout()
        path = os.path.join(PNZ_FIG_DIR, "input_distribution_capex.png")
        fig.savefig(path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        return path

    # ---- 5. Sensitivity line plots: value of flexibility vs a swept input --
    PNZ_N_SENS = 500   # see docs/notes/Reporting/Results.md#pnz_n_sens-sizing-rationale

    def _paired_value_of_flexibility(values, apply_fn, restore_fn,
                                      flex_name=PNZ_FLEXIBLE, base_name=PNZ_BASELINE):
        # see docs/notes/Reporting/Results.md#_paired_value_of_flexibility-method
        factory_flex = Strategies_Flex[flex_name]
        factory_base = Strategies_2[base_name]
        out = {}
        for v in values:
            apply_fn(v)
            d = np.empty(PNZ_N_SENS)
            for i in range(PNZ_N_SENS):
                capex_mult = draw_capex[i]
                scenario = draw_scenario[i]
                wx_seq = marg_raw_draws["wx_seq"][i]
                capex_estimate_seq = marg_raw_draws["capex_estimate_seq"][i]
                demand, price_seq, background_seq = _paths_from_stored_z(marg_raw_draws["z"][i], scenario)
                npv_flex = Run_Strategy((flex_name, factory_flex(capex_mult)), demand, scenario, wx_seq,
                                         capex_mult, capex_estimate_seq, price_seq, background_seq)[3]
                npv_base = Run_Strategy((base_name, factory_base(capex_mult)), demand, scenario, wx_seq,
                                         capex_mult, capex_estimate_seq, price_seq, background_seq)[3]
                d[i] = npv_flex - npv_base
            out[v] = d
            restore_fn()
        return out

    def _plot_vof_sweep(results, values, xvals, xlabel, title, subtitle, out_name,
                         vline=None, vline_label=None):
        means = np.array([results[v].mean() for v in values]) / 1e6
        p5 = np.array([np.percentile(results[v], 5) for v in values]) / 1e6
        p95 = np.array([np.percentile(results[v], 95) for v in values]) / 1e6

        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        _style_ax(ax)
        ax.fill_between(xvals, p5, p95, color=CATEGORICAL[0], alpha=0.14, lw=0, zorder=1)
        ax.plot(xvals, means, lw=2, marker="o", color=CATEGORICAL[0], zorder=3)
        ax.axhline(0, color=INK_MUTED, lw=0.8)
        if vline is not None:
            ax.axvline(vline, color=INK_SECONDARY, ls="--", lw=1, label=vline_label)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(f"ΔENPV ({PNZ_FLEXIBLE} − {PNZ_BASELINE}), £m")
        _titled(ax, title, subtitle)
        if vline is not None:
            ax.legend()
        fig.tight_layout()
        path = os.path.join(PNZ_FIG_DIR, out_name)
        fig.savefig(path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        return path

    def plot_value_of_flexibility_vs_rate():
        assert_paired_draws([PNZ_BASELINE, PNZ_FLEXIBLE])
        rates = np.round(np.arange(0.01, 0.121, 0.01), 3)
        _orig_rate = M.RATE
        results = _paired_value_of_flexibility(rates, M.set_rate, lambda: M.set_rate(_orig_rate))
        return _plot_vof_sweep(
            results, rates, rates * 100, "Discount rate (%)",
            "Value of flexibility vs discount rate",
            f"ΔENPV = {PNZ_FLEXIBLE} − {PNZ_BASELINE}, paired MC (N={PNZ_N_SENS}), shaded = P5–P95",
            "value_of_flexibility_vs_discount_rate.png",
            vline=3.5, vline_label="Green Book 3.5%")

    def plot_value_of_flexibility_vs_avail():
        assert_paired_draws([PNZ_BASELINE, PNZ_FLEXIBLE])
        avail_values = sorted({0.80, 0.85, round(M.AVAIL, 2), 0.95, 1.00})
        _orig_wind_cf_by_year = M.WIND_CF_BY_YEAR

        def apply(av):
            M.WIND_CF_BY_YEAR = M.compute_wind_cf_by_year(av)

        def restore():
            M.WIND_CF_BY_YEAR = _orig_wind_cf_by_year

        results = _paired_value_of_flexibility(avail_values, apply, restore)
        return _plot_vof_sweep(
            results, avail_values, [v * 100 for v in avail_values],
            "AVAIL — wake + availability + electrical-loss derating (%)",
            "Value of flexibility vs wind availability/derating",
            f"ΔENPV = {PNZ_FLEXIBLE} − {PNZ_BASELINE}, paired MC (N={PNZ_N_SENS}), shaded = P5–P95",
            "value_of_flexibility_vs_avail.png",
            vline=M.AVAIL * 100, vline_label=f"current AVAIL={M.AVAIL:.0%}")

    # ---- 6. Headline % value-of-flexibility figure -------------------------
    def print_headline_value_of_flexibility():
        # see docs/notes/Reporting/Results.md#print_headline_value_of_flexibility-definition
        candidates = [s for s in marg_store if s != "Do Nothing"]
        n = assert_paired_draws(candidates + [PNZ_BASELINE])
        enpvs = {s: marg_store[s].mean() for s in candidates}
        baseline_enpv = marg_store[PNZ_BASELINE].mean()
        best_name = max(enpvs, key=enpvs.get)
        d_enpv = marg_store[best_name] - marg_store[PNZ_BASELINE]   # paired, per draw index
        pct = (enpvs[best_name] - baseline_enpv) / abs(baseline_enpv) * 100
        p_better = float((d_enpv > 0).mean())

        line = (f"HEADLINE — value of flexibility: {best_name} beats {PNZ_BASELINE} by "
                f"{pct:+.1f}% ENPV (£{enpvs[best_name]/1e6:.0f}m vs £{baseline_enpv/1e6:.0f}m, "
                f"paired MC N={n}, P({best_name} > {PNZ_BASELINE})={p_better:.0%})")
        print("\n" + line)

        path = os.path.join(PNZ_TABLE_DIR, "headline_value_of_flexibility.txt")
        with open(path, "w") as f:
            f.write(line + "\n")
        return line

    # ---- 7. Reference cost/parameter input table ----------------------------
    def build_reference_input_table():
        # see docs/notes/Reporting/Results.md#build_reference_input_table-scope
        newlink = O.NewLink(1.0)
        stage1 = O.Stage1_Wind_Buildout()
        stage2 = O.Stage2_Wind_Buildout()

        rows = [
            ("Social discount rate", f"{M.RATE:.1%}", "System_Model.RATE"),
            ("Link opex rate (% of capex, p.a.)", f"{O.LINK_OPEX_RATE:.3%}", "Options.LINK_OPEX_RATE"),
            ("Baseline (NewLink) capacity", f"{newlink.Capacity():.0f} MW", "Options.NewLink"),
            ("Baseline (NewLink) capex, 2023 prices", f"£{newlink.Capex()/1e6:.0f}m",
             "Options.NewLink [Ofgem 2019 Table A3.3]"),
            ("Staged-link fixed cost per stage", f"£{O.STAGED_LINK_FIXED_PER_STAGE/1e6:.1f}m",
             "Options.STAGED_LINK_FIXED_PER_STAGE"),
            ("Staged-link stage sizes (default)",
             ", ".join(f"{s:.1f}" for s in O.STAGED_LINK_STAGE_SIZES_DEFAULT) + " MW",
             "Options.STAGED_LINK_STAGE_SIZES_DEFAULT"),
            ("Stage 1 wind buildout capacity", f"{stage1.Capacity():.1f} MW", "Options.Stage1_Wind_Buildout"),
            ("Stage 1 wind buildout capex", f"£{stage1.Capex()/1e6:.1f}m", "Options.Stage1_Wind_Buildout"),
            ("Stage 2 wind buildout capacity", f"{stage2.Capacity():.1f} MW", "Options.Stage2_Wind_Buildout"),
            ("Stage 2 wind buildout capex", f"£{stage2.Capex()/1e6:.1f}m", "Options.Stage2_Wind_Buildout"),
            ("Wind availability/derating (AVAIL)", f"{M.AVAIL:.0%}", "System_Model.AVAIL"),
            ("Curtailment/constraint-relief cost", f"£{M.CONSTRAINT_COST:.1f}/MWh", "System_Model.CONSTRAINT_COST"),
            ("Capex overrun — median multiplier", f"{M.CAPEX_MEDIAN:.2f}x", "System_Model.CAPEX_MEDIAN"),
            ("Capex overrun — P90 multiplier (derived)", f"{M.CAPEX_P90:.2f}x", "System_Model.CAPEX_P90"),
            ("Capex overrun — lognormal sigma", f"{M.CAPEX_SIGMA:.3f}", "System_Model.CAPEX_SIGMA"),
            ("Main Link background-generation trigger", f"{M.MAIN_LINK_BG_GEN_THRESHOLD:.0f} MW",
             "Decision_Rules.MAIN_LINK_BG_GEN_THRESHOLD"),
            ("Flexible Cost-Aware cost cap", f"{M.MAIN_LINK_COST_CAP:.2f}x", "System_Model.MAIN_LINK_COST_CAP"),
            ("CfD strike price", f"£{M.CFD_STRIKE:.2f}/MWh", "System_Model.CFD_STRIKE"),
            ("Model horizon", f"{M.YEARS[0]}–{M.YEARS[-1]} ({len(M.YEARS)} years)", "System_Model.YEARS"),
        ]

        path = os.path.join(PNZ_TABLE_DIR, "reference_input_table.csv")
        with open(path, "w") as f:
            f.write("Parameter,Value,Source\n")
            for name, value, source in rows:
                f.write(f'"{name}","{value}","{source}"\n')

        width1 = max(len(r[0]) for r in rows) + 2
        width2 = max(len(r[1]) for r in rows) + 2
        print("\n=== Reference input table (model cost/parameter assumptions) ===")
        for name, value, source in rows:
            print(f"{name:<{width1}}{value:<{width2}}{source}")
        print(f"(written to {path})")
        return path

    _pnz_skipped = [
        ("Point-metric summary table (ENPV per strategy)",
         "print_metrics_table() above — console table, ENPV/P5/P50/P95/etc. per strategy"),
        ("Percentile columns (P5/P95 alongside ENPV)",
         "print_metrics_table() above — same table already carries P5/P50/P95 columns"),
        ("CDF / target curves (NPV per strategy, overlaid)",
         "\"Target curves — absolute NPV\" block above -> Images/target_curves_marginalised.png"),
    ]
    _pnz_implemented = [
        ("Cost/input distribution histogram (capex multiplier)", plot_capex_distribution()),
        ("Sensitivity line plot: value of flexibility vs discount rate", plot_value_of_flexibility_vs_rate()),
        ("Sensitivity line plot: value of flexibility vs AVAIL (CF/degradation driver)",
         plot_value_of_flexibility_vs_avail()),
        ("Headline % value-of-flexibility figure", print_headline_value_of_flexibility()),
        ("Reference cost/parameter input table", build_reference_input_table()),
    ]
    print("\n" + "=" * 78)
    print("PNZ 2025 results-presentation methods — implementation summary")
    print("=" * 78)
    print(f"\nSKIPPED (already present, {len(_pnz_skipped)}):")
    for _name, _where in _pnz_skipped:
        print(f"  - {_name}\n      -> {_where}")
    print(f"\nIMPLEMENTED (new, {len(_pnz_implemented)}):")
    for _name, _where in _pnz_implemented:
        print(f"  - {_name}\n      -> {_where}")
    print()

    # see docs/notes/Reporting/Results.md#sections-9-18-moved-to-sensitivitiespy
