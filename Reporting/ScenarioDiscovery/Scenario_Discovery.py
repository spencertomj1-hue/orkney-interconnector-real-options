# Standalone PRIM (Patient Rule Induction Method) scenario discovery over the
# headline Monte Carlo draws. Run this BY HAND, after Results.py has been run
# once with System_Model.SCENARIO_DISCOVERY=True, so mc_draws.csv exists.
# Never imported by System_Model.py or Results.py -- the core model must
# never depend on ema_workbench, and it doesn't; this file is the sole
# consumer of that PRIM dependency.
#
# PRIM background: given an input matrix X (uncertain scenario parameters)
# and a binary outcome y (1="loss"), PRIM iteratively shrinks ("peels") a box
# around the data, each step removing whichever slice raises the box's
# DENSITY (fraction of in-box points that are y=1) the most. As the box
# shrinks, its COVERAGE (fraction of all y=1 points captured) falls -- that
# trade-off, traced step by step, is the "peeling trajectory". The final
# box's bounds are the result: e.g. "loss concentrates where capex_mult>2.1
# AND scenario==Falling Behind". Friedman & Fisher (1999) is the original
# algorithm; Bryant & Lempert (2010) is the exploratory-modelling application
# (Robust Decision Making) that ema_workbench.analysis.prim implements.

import os
import numpy as np
import pandas as pd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from ema_workbench.analysis import prim

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SD_DIR = os.path.join(THIS_DIR, "Extra")
HEADLINE_DIR = os.path.join(THIS_DIR, "Main_Plots")  # renamed from Headline_Plots outside this session
MC_DRAWS_CSV = os.path.join(SD_DIR, "mc_draws.csv")

# OUTCOME definition -- pick the one matching your P(loss) definition.
OUTCOME = "npv_below_zero"          # default: loss = NPV < 0
# alt: "worse_than_do_nothing"      # loss = NPV_strategy - NPV_do_nothing < 0
# alt: "lcoe_above_threshold"       # loss = incremental LCOE vs Do Nothing > LCOE_FAIL_THRESHOLD

# £/MWh cutoff for the lcoe_above_threshold OUTCOME -- a cost-of-energy fail
# criterion rather than an NPV one, so it can surface a different loss region
# (e.g. a strategy might stay NPV-positive on average while still clearing a
# high per-MWh cost bar on the same draws). Illustrative, not fitted.
LCOE_FAIL_THRESHOLD = 80.0

# Human-readable form of OUTCOME for chart titles, so titles show "NPV < £0"
# rather than the raw Python identifier "npv_below_zero".
OUTCOME_DISPLAY = {
    "npv_below_zero": "loss defined as NPV < £0",
    "worse_than_do_nothing": "loss defined as NPV worse than Do Nothing",
    "lcoe_above_threshold": f"loss defined as incremental LCOE > £{LCOE_FAIL_THRESHOLD:.0f}/MWh vs Do Nothing",
    "regret": "regret vs best of the 4 build strategies (excl. Do Nothing)",
}

# The 4 headline strategies plus Flexible 1-Stage (Cost-Aware) as a 5th (Do
# Nothing is the reference for worse_than_do_nothing/lcoe_above_threshold,
# not looped here). Column names must match Results.py's own derivation
# exactly ("npv_" + sname.lower().replace(" ", "_").replace("-", "_")) --
# confirmed directly against mc_draws.csv's actual header, not guessed.
STRATEGY_TO_COL = {
    "Baseline": "npv_baseline",
    "Fixed 4-Stage": "npv_fixed_4_stage",
    "Flexible 1-Stage": "npv_flexible_1_stage",
    "Flexible 4-Stage": "npv_flexible_4_stage",
    "Flexible 1-Stage (Cost-Aware)": "npv_flexible_1_stage_(cost_aware)",
}

# Same strategies, pointed at Results.py's per-draw incremental-LCOE columns
# instead of NPV -- used only when OUTCOME="lcoe_above_threshold".
STRATEGY_TO_LCOE_COL = {
    "Baseline": "lcoe_baseline",
    "Fixed 4-Stage": "lcoe_fixed_4_stage",
    "Flexible 1-Stage": "lcoe_flexible_1_stage",
    "Flexible 4-Stage": "lcoe_flexible_4_stage",
    "Flexible 1-Stage (Cost-Aware)": "lcoe_flexible_1_stage_(cost_aware)",
}


# Kept as a function (not a module-level constant) so it re-reads OUTCOME if
# that's changed after import, same as OUTCOME_DISPLAY.get(OUTCOME, ...) elsewhere.
def strategy_col_map():
    return STRATEGY_TO_LCOE_COL if OUTCOME == "lcoe_above_threshold" else STRATEGY_TO_COL

# Passed straight through to ema_workbench.analysis.prim.Prim -- these are its
# own default values, named here so they're visible and easy to tune without
# digging into the library. PEEL_ALPHA: fraction of in-box points considered
# for removal at each peeling step. PASTE_ALPHA: fraction considered for
# re-addition in PRIM's pasting phase (undoes an overly greedy peel).
# MASS_MIN: peeling stops once the box would hold less than this fraction of
# all draws.
PEEL_ALPHA = 0.05
PASTE_ALPHA = 0.05
MASS_MIN = 0.05

# Draws are paired across strategies (all strategies in one run_marginalised()
# call share the same draw index -- same capex_mult/scenario/weather/GBM
# shocks). Set here as a constant, not re-derived from the CSV, since the CSV
# alone can't prove pairing -- it reflects a fact about how Results.py
# produced it. If that MC loop is ever changed to draw independently per
# strategy, this must be flipped to False by hand.
PAIRED_DRAWS = True

# year_bg135_raw_crossed is NaN for draws where background generation never
# raw-crosses 135MW within the model horizon. PRIM can't handle NaN, so it's
# filled with a fixed after-horizon sentinel (treated as "later than every
# real crossing year") rather than dropping the column or the rows.
# Hardcoded rather than imported from System_Model.YEARS, to keep this file
# fully standalone -- if the model horizon ever changes, update by hand.
NEVER_CROSSED_YEAR_SENTINEL = 2052

# DROP_TRIGGER_DRIVERS: year_bg135_raw_crossed and background_terminal_mw are
# crossing-time/level features of background_gen_mw, which IS the flexible
# strategies' exercise trigger (see Model/Decision_Rules.py make_main_link_rule
# / make_staged_link_strategy) -- including them in the PRIM driver set for a
# flexible strategy risks explaining the loss region with a near-tautology of
# its own decision rule. When True, both are dropped from the fit for flexible
# strategies only; rigid strategies (Baseline, Fixed 4-Stage) have no such
# circularity and always keep the full driver set.
DROP_TRIGGER_DRIVERS = False
TRIGGER_DRIVER_COLS = ["year_bg135_raw_crossed", "background_terminal_mw"]
FLEXIBLE_STRATEGIES = {"Flexible 1-Stage", "Flexible 4-Stage", "Flexible 1-Stage (Cost-Aware)"}

# NO_BOX_DENSITY_THRESHOLD: below this, PRIM found a box but it isn't actually
# separating losses from profits well enough to report as a finding -- see
# run_prim_for_strategy's post-find_box() check.
NO_BOX_DENSITY_THRESHOLD = 0.5


def load_data():
    if not os.path.exists(MC_DRAWS_CSV):
        raise FileNotFoundError(
            f"{MC_DRAWS_CSV} not found -- run Results.py once with "
            f"System_Model.SCENARIO_DISCOVERY = True first (see that flag's "
            f"comment in System_Model.py for where the capture block lives).")
    return pd.read_csv(MC_DRAWS_CSV)


# The DFES scenario dimension is categorical. ema_workbench's Prim supports a
# categorical column NATIVELY -- given dtype "category" it peels by removing
# one category at a time (set-membership, e.g. scen:{A}) rather than
# continuous quantile peeling. Cast explicitly rather than relying on
# implicit string/object auto-detection. Simpler and more interpretable than
# one-hot dummies (no risk of PRIM fixing collinear dummy columns to
# contradictory values), and is what the library's PRIM is actually built to
# do -- not run-PRIM-once-per-scenario, which would fragment the ~2000 draws
# into 4 much smaller, noisier sub-ensembles.
def prepare_inputs(df):
    continuous_cols = ["capex_mult", "wind_cf_proxy_mean", "capex_estimate_year0",
                        "demand_terminal_gwh", "price_terminal_gbp_mwh",
                        "background_terminal_mw", "year_bg135_raw_crossed"]
    X = df[continuous_cols].copy()
    X["year_bg135_raw_crossed"] = X["year_bg135_raw_crossed"].fillna(NEVER_CROSSED_YEAR_SENTINEL)
    assert not X.isna().any().any(), "unexpected NaN in a continuous PRIM input besides year_bg135_raw_crossed"

    X["scenario"] = df["scenario"].astype("category")
    return X


def compute_loss_flag(df, value_col, outcome):
    if outcome == "npv_below_zero":
        return (df[value_col] < 0).astype(int)
    if outcome == "worse_than_do_nothing":
        return ((df[value_col] - df["npv_do_nothing"]) < 0).astype(int)
    if outcome == "lcoe_above_threshold":
        # NaN entries (dE~0, or a "dominates" draw -- see Results.py's
        # lcoe_from_stores) compare False under >, i.e. NOT a high-LCOE
        # failure -- correct, since a dominates draw is strictly better than
        # Do Nothing, not a cost-per-unit figure at all.
        return (df[value_col] > LCOE_FAIL_THRESHOLD).astype(int)
    raise ValueError(f"unknown OUTCOME {outcome!r}")


# REGRET_NPV_COLS / REGRET_STRATEGIES / compute_regret: regret is defined only
# over the 4 headline build strategies -- npv_do_nothing is deliberately
# excluded from the max(). Do Nothing isn't one of the 2x2 choices in Plot 1/
# Plot 2, and an empty-cable draw's NPV would otherwise swamp regret with a
# comparison that has nothing to do with choosing among the 4 build strategies.
REGRET_STRATEGIES = ["Baseline", "Fixed 4-Stage", "Flexible 1-Stage", "Flexible 4-Stage"]
REGRET_NPV_COLS = [STRATEGY_TO_COL[s] for s in REGRET_STRATEGIES]


def compute_regret(df, value_col):
    # npv_* columns in mc_draws.csv are raw £ (min ~-9e8, max ~1.3e9 -- matches
    # the Results/target_curves NPV chart's -£750m..£1000m range), not £m --
    # divide here so every downstream £m label (prints, box_summary.csv,
    # colorbar, frontier plot) is correct without a conversion at each call site.
    best = df[REGRET_NPV_COLS].max(axis=1)
    return ((best - df[value_col]) / 1e6).clip(lower=0)


def run_prim_for_strategy(name, value_col, df, X):
    y = compute_loss_flag(df, value_col, OUTCOME)
    n_pos = int(y.sum())
    print(f"\n=== PRIM: {name} (outcome={OUTCOME}, loss cases = {n_pos}/{len(y)} = {n_pos/len(y):.1%}) ===")

    X_fit = X
    if DROP_TRIGGER_DRIVERS and name in FLEXIBLE_STRATEGIES:
        dropped = [c for c in TRIGGER_DRIVER_COLS if c in X_fit.columns]
        X_fit = X_fit.drop(columns=dropped)
        print(f"  DROP_TRIGGER_DRIVERS: dropped {dropped} (circular w/ {name}'s exercise trigger)")

    # X/y are drawn from mc_draws.csv, whose `scenario` column was sampled with
    # p=SCENARIO_WEIGHTS["NetZero_Tilt"] at MC-cache build time (Reporting/Results.py:141)
    # -- the tilt is already embedded in these 2000 draws, so this fit is unweighted
    # only in the sense of not re-weighting on top of that; no separate reweighting needed.
    p = prim.Prim(X_fit, y, peel_alpha=PEEL_ALPHA, paste_alpha=PASTE_ALPHA, mass_min=MASS_MIN)
    box = p.find_box()

    final_id = box.peeling_trajectory.index[-1]
    print(f"  coverage={box.coverage:.3f}  density={box.density:.3f}  "
          f"n_points={int(box.peeling_trajectory.loc[final_id, 'n'])}  res_dim={box.res_dim}")
    box.inspect(final_id)
    if box.density < NO_BOX_DENSITY_THRESHOLD:
        print(f"  no separable loss region (density={box.density:.3f}, n_loss={n_pos} diffuse)")

    return box


def run_regret_prim_for_strategy(name, value_col, df, X):
    regret = compute_regret(df, value_col)
    full_mean = float(regret.mean())
    print(f"\n=== Regret RegressionPrim: {name} (mean regret over full population = £{full_mean:.2f}m) ===")

    X_fit = X
    if DROP_TRIGGER_DRIVERS and name in FLEXIBLE_STRATEGIES:
        dropped = [c for c in TRIGGER_DRIVER_COLS if c in X_fit.columns]
        X_fit = X_fit.drop(columns=dropped)
        print(f"  DROP_TRIGGER_DRIVERS: dropped {dropped} (circular w/ {name}'s exercise trigger)")

    p = prim.RegressionPrim(X_fit, regret.to_numpy(), peel_alpha=PEEL_ALPHA, paste_alpha=PASTE_ALPHA,
                             mass_min=MASS_MIN, maximization=True)
    box = p.find_box()

    print(f"  box mean regret=£{float(box.mean):.2f}m  mass={float(box.mass):.3f}  res_dim={box.res_dim}")
    box.inspect(box.peeling_trajectory.index[-1])

    # Maximization tripwire (don't trust the flag blind): ema_workbench's
    # RegressionPrim.__init__ carries `self._maximization = maximization  # fixme
    # this is not working correctly` on its own maximization param
    # (ema_workbench/analysis/prim.py:1983). If the selected box's mean regret
    # isn't actually higher than the full-population mean, the flag found a
    # LOW-regret box instead of a high-regret one -- halt before any output is
    # written rather than emit a mislabelled box.
    if not (box.stats["mean"] > full_mean):
        raise RuntimeError(
            f"MAXIMIZATION TRIPWIRE FAILED for {name}: box.stats['mean']=£{box.stats['mean']:.2f}m is "
            f"not greater than the full-population mean regret (£{full_mean:.2f}m). RegressionPrim's "
            f"maximization flag may be inverted -- halting, no plots emitted.")

    return box


# Trajectory CSV + 2 plots, both ema_workbench's own built-in visualisations
# (not hand-rolled): show_tradeoff() is the standard PRIM coverage-vs-density
# curve, one point per peeling step, so you can see the whole trade-off, not
# just the final box's stats; inspect(..., style="graph") draws the FINAL
# box's own bounds as bars against the full data range per dimension, given
# its own fig/ax since the default figsize truncates dimension-name labels
# when 5+ dimensions are restricted (several boxes here have that many).
def save_trajectory(name, box):
    slug = name.lower().replace(" ", "_")
    traj_df = box.peeling_trajectory
    csv_path = os.path.join(SD_DIR, f"peeling_trajectory_{slug}.csv")
    traj_df.to_csv(csv_path)

    fig = box.show_tradeoff()
    fig.suptitle(f"{name} -- {OUTCOME_DISPLAY.get(OUTCOME, OUTCOME)}")
    tradeoff_png_path = os.path.join(SD_DIR, f"peeling_trajectory_{slug}.png")
    fig.savefig(tradeoff_png_path, dpi=150)
    plt.close(fig)

    final_id = box.peeling_trajectory.index[-1]
    fig2, ax2 = plt.subplots(figsize=(9, 1.2 + 0.6 * box.res_dim))
    box.inspect(final_id, style="graph", ax=ax2)
    fig2.suptitle(f"{name} final box -- {OUTCOME_DISPLAY.get(OUTCOME, OUTCOME)}")
    fig2.tight_layout()
    box_png_path = os.path.join(SD_DIR, f"box_graph_{slug}.png")
    fig2.savefig(box_png_path, dpi=150)
    plt.close(fig2)

    return csv_path, tradeoff_png_path, box_png_path


# box.box_lims[-1] is a DataFrame, index [min, max], one column per input
# dimension. The categorical "scenario" column stores both rows as the SAME
# set of allowed categories, so .iloc[0] alone is enough to read it.
# "Restricted" means this dimension's bounds are narrower than the FULL data
# range it started at (box_lims of trajectory step 0).
def box_bounds_dict(box):
    full = box.box_lims[0]
    final = box.box_lims[-1]
    bounds = {}
    for col in final.columns:
        if isinstance(final[col].iloc[0], (set, frozenset)):
            if final[col].iloc[0] != full[col].iloc[0]:
                bounds[col] = sorted(final[col].iloc[0])
        else:
            lo, hi = float(final[col].iloc[0]), float(final[col].iloc[1])
            full_lo, full_hi = float(full[col].iloc[0]), float(full[col].iloc[1])
            if lo > full_lo + 1e-9 or hi < full_hi - 1e-9:
                bounds[col] = (round(lo, 4), round(hi, 4))
    return bounds


# One panel per dimension, each on its own real-unit LINEAR x-axis (not a
# shared 0-1 "position within range" axis -- a reader has no intuition for
# what "0.4" means on an axis mixing capex multiples, £/MWh and years). No
# log-scaled axes anywhere, by explicit request -- a dimension with a very
# wide full range can render a tightly-restricted box as a thin sliver near
# the low end; that's a consequence of the choice, not an oversight.
# ema_workbench has no built-in "compare N separate Prim() runs" plot (its
# own multi-box tools compare SEQUENTIAL boxes from one Prim run on one y,
# not separate runs on different strategies), so this figure is hand-rolled,
# but it only lays out numbers ema_workbench already computed (box_lims).
# Colours are the first 4 slots of this project's validated categorical
# palette, fixed order.
STRATEGY_COLORS_HEX = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#9b59b6"]   # blue, orange, aqua, yellow, purple
CHART_INK = "#0b0b0b"
CHART_INK_MUTED = "#898781"
CHART_GRIDLINE = "#e1e0d9"
CHART_SURFACE = "#fcfcfb"

# Dimensions never shown on this comparison figure, even if some strategy's
# box restricts them -- still a legitimate PRIM input everywhere else
# (mc_draws.csv, prepare_inputs(), each strategy's own box_graph_*.png,
# box_summary.csv). Excluded only because they clutter this combined view,
# per explicit request -- not a claim they're uninformative.
# price_terminal_gbp_mwh specifically: its full range spans four orders of
# magnitude, so on this figure's strictly-linear axes every strategy's box
# would collapse to an unreadable sliver at x=0 -- dropped rather than shown
# broken (log scale would fix it but was explicitly ruled out).
COMPARISON_PLOT_EXCLUDE_DIMS = {"capex_estimate_year0", "price_terminal_gbp_mwh", "wind_cf_proxy_mean"}

# Column name -> (display label, unit suffix for value labels).
DIM_DISPLAY = {
    "capex_mult": ("Capex overrun multiplier", "x"),
    "wind_cf_proxy_mean": ("Wind capacity factor (path mean)", ""),
    "demand_terminal_gwh": ("Terminal demand", " GWh"),
    "price_terminal_gbp_mwh": ("Terminal wholesale price", " £/MWh"),
    "background_terminal_mw": ("Terminal background generation", " MW"),
    "year_bg135_raw_crossed": ("Year background gen. first exceeds 135MW", ""),
    "scenario": ("DFES scenario", ""),
}


# YEAR_LIKE_DIMS: calendar years, printed as plain integers (2028), never
# thousands-comma-grouped (2,028 reads as a quantity, not a year).
YEAR_LIKE_DIMS = {"year_bg135_raw_crossed"}


def _fmt_value(v, unit, dim=None):
    if dim in YEAR_LIKE_DIMS:
        return f"{v:.0f}"
    if abs(v) >= 100:
        return f"{v:,.0f}{unit}"
    if abs(v) >= 1:
        return f"{v:,.2f}{unit}"
    return f"{v:.4g}{unit}"


# dims=None (default): auto-select every dimension restricted by at least one
# strategy's box, minus COMPARISON_PLOT_EXCLUDE_DIMS, most-restricted-by
# first -- the full "where does each strategy lose money" survey. Pass an
# explicit dims list to instead render exactly those dimensions, in that
# order, regardless of whether every strategy's box actually restricts them
# -- a focused variant for a specific pair/subset. out_name lets a focused
# call avoid overwriting the full comparison's output file.
def plot_cross_strategy_comparison(boxes, dims=None, out_name="cross_strategy_comparison"):
    strategy_names = list(boxes.keys())
    n_strat = len(strategy_names)
    ref_full = next(iter(boxes.values())).box_lims[0]   # same X every strategy -> same full range
    box_bounds = {name: box_bounds_dict(box) for name, box in boxes.items()}
    if dims is not None:
        all_dims = list(dims)
    else:
        all_dims = sorted({dim for b in box_bounds.values() for dim in b} - COMPARISON_PLOT_EXCLUDE_DIMS,
                           key=lambda d: -sum(d in box_bounds[n] for n in strategy_names))   # most-restricted-by first
    if not all_dims:
        return None

    fig, axes = plt.subplots(len(all_dims), 1, figsize=(8, 1.5 * len(all_dims)),
                              facecolor=CHART_SURFACE)
    if len(all_dims) == 1:
        axes = [axes]

    bar_h = 0.6
    for ax, dim in zip(axes, all_dims):
        ax.set_facecolor(CHART_SURFACE)
        label, unit = DIM_DISPLAY.get(dim, (dim, ""))
        is_categorical = isinstance(ref_full[dim].iloc[0], (set, frozenset))

        if is_categorical:
            # Set-membership restriction, not a numeric range -- printed as
            # text per strategy rather than a bar (position on an axis has
            # no meaning for a category).
            ax.axis("off")
            ax.set_title(label, loc="left", fontsize=10, color=CHART_INK, fontweight="bold")
            lines = []
            for s_i, name in enumerate(strategy_names):
                bound = box_bounds[name].get(dim)
                text = f"{name}: {sorted(bound)}" if bound else f"{name}: (unrestricted)"
                lines.append((text, STRATEGY_COLORS_HEX[s_i % len(STRATEGY_COLORS_HEX)]))
            for i, (text, color) in enumerate(lines):
                ax.text(0.0, 1 - (i + 0.5) / len(lines), text, transform=ax.transAxes,
                        va="center", fontsize=8, color=color)
            continue

        full_lo, full_hi = float(ref_full[dim].iloc[0]), float(ref_full[dim].iloc[1])

        # Full-range reference band, neutral grey (context, not a per-strategy
        # colour), drawn once behind every bar.
        ax.barh(0, full_hi - full_lo, left=full_lo, height=bar_h * (n_strat + 0.6),
                color=CHART_GRIDLINE, zorder=1)

        n_restricting = sum(dim in box_bounds[n] for n in strategy_names)
        y0 = -(n_restricting - 1) / 2
        row = 0
        for s_i, name in enumerate(strategy_names):
            bound = box_bounds[name].get(dim)
            if bound is None:
                continue   # unrestricted on this dimension -- no bar, just the grey reference band
            lo, hi = bound
            color = STRATEGY_COLORS_HEX[s_i % len(STRATEGY_COLORS_HEX)]
            y = y0 + row
            ax.barh(y, hi - lo, left=lo, height=bar_h, color=color, zorder=2)
            mid = (lo + hi) / 2
            ax.text(mid, y, f"{_fmt_value(lo, unit, dim)} - {_fmt_value(hi, unit, dim)}",
                    ha="center", va="center", fontsize=7, color="white", fontweight="bold", zorder=3)
            row += 1

        ax.set_ylim(-(n_strat + 0.6) / 2, (n_strat + 0.6) / 2)
        ax.set_yticks([])
        ax.set_title(label, loc="left", fontsize=10, color=CHART_INK, fontweight="bold")
        ax.tick_params(axis="x", colors=CHART_INK_MUTED, labelsize=8)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color(CHART_GRIDLINE)

    fig.suptitle(f"Where does each strategy lose money?\n{OUTCOME_DISPLAY.get(OUTCOME, OUTCOME)}",
                 fontsize=13, color=CHART_INK, fontweight="bold", y=1.02)
    handles = [plt.Rectangle((0, 0), 1, 1, color=STRATEGY_COLORS_HEX[i % len(STRATEGY_COLORS_HEX)])
               for i in range(n_strat)]
    fig.legend(handles, strategy_names, loc="lower center", bbox_to_anchor=(0.5, -0.02),
               ncol=n_strat, frameon=False, fontsize=9)
    fig.text(0.5, -0.06, "Grey band = full range across all 2000 draws. Coloured bar = this "
                         "strategy's PRIM box on this dimension (no bar = unrestricted).",
             ha="center", fontsize=8, color=CHART_INK_MUTED)
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])

    path = os.path.join(SD_DIR, f"{out_name}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=CHART_SURFACE)
    plt.close(fig)
    return path


# PLOT 1 -- supersedes the old plot_price_capex_scatter_by_strategy (same
# price x capex axes, same box-overlay logic) with continuous regret colour
# and a 2x2 layout, one panel per headline build strategy. Not standalone --
# takes df/boxes/regret_boxes from __main__ rather than refitting PRIM itself,
# since __main__ already has both the binary and regret fits in hand.
def plot_loss_regret_scatter_by_strategy(df, boxes, regret_boxes, out_name="loss_regret_scatter_by_strategy"):
    strategies = REGRET_STRATEGIES   # the 4 headline build strategies, in 2x2 order
    assert len(strategies) == 4, f"expected 4 strategies for a 2x2 layout, got {strategies}"

    # Shared colour scale across all 4 panels. Regret is zero-inflated (=0 for
    # whichever strategy is best on a given draw); log1p keeps those zeros at
    # the bottom of the scale while compressing the long positive tail so the
    # non-zero spread stays visible rather than a pale field with one dark spike.
    all_regret = pd.concat([compute_regret(df, STRATEGY_TO_COL[s]) for s in strategies])
    vmax = float(np.log1p(all_regret).max())
    norm = mcolors.Normalize(vmin=0.0, vmax=vmax)
    cmap = plt.get_cmap("magma")

    fig, axes = plt.subplots(2, 2, figsize=(10.5, 9.5), facecolor=CHART_SURFACE, sharex=True, sharey=True)
    axes_flat = axes.flatten()

    for ax, name in zip(axes_flat, strategies):
        value_col = STRATEGY_TO_COL[name]
        regret = compute_regret(df, value_col)
        c = np.log1p(regret)

        ax.scatter(df["price_terminal_gbp_mwh"], df["capex_mult"], c=c, cmap=cmap, norm=norm,
                   s=10, alpha=0.85, linewidths=0, zorder=2)

        # box overlay: BINARY-loss PRIM box only, only where that strategy's
        # binary density clears NO_BOX_DENSITY_THRESHOLD -- never a regret-box
        # overlay (regret has no equivalent separability concept).
        binary_box = boxes[name]
        if binary_box.density >= NO_BOX_DENSITY_THRESHOLD:
            bounds = box_bounds_dict(binary_box)
            full = binary_box.box_lims[0]
            x_lo, x_hi = bounds.get("price_terminal_gbp_mwh",
                                     (float(full["price_terminal_gbp_mwh"].iloc[0]), float(full["price_terminal_gbp_mwh"].iloc[1])))
            y_lo, y_hi = bounds.get("capex_mult",
                                     (float(full["capex_mult"].iloc[0]), float(full["capex_mult"].iloc[1])))
            ax.add_patch(plt.Rectangle((x_lo, y_lo), x_hi - x_lo, y_hi - y_lo,
                                        fill=False, edgecolor=CHART_INK, linewidth=2, zorder=3))
            cause = "sharp corner" if name in ("Baseline", "Fixed 4-Stage") else "still separable"
        else:
            ax.text(0.03, 0.03, "no separable loss region", transform=ax.transAxes,
                    fontsize=8, color=CHART_INK_MUTED, ha="left", va="bottom", style="italic")
            cause = "dispersed, no box"

        # cause as an in-axes annotation, not appended to the title -- a long
        # cause string (esp. on the demand x generation variant) can be wider
        # than one 2x2 column, and titles don't wrap, so they'd overflow into
        # the neighbouring panel regardless of tight_layout/subplot spacing.
        ax.set_xscale("log")
        ax.set_facecolor(CHART_SURFACE)
        ax.set_title(name, fontsize=11, color=CHART_INK, fontweight="bold")
        ax.text(0.03, 0.90, cause, transform=ax.transAxes, fontsize=8.5, color=CHART_INK_MUTED,
                ha="left", va="top", style="italic")
        ax.tick_params(colors=CHART_INK_MUTED, labelsize=8)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

    for ax in axes[-1, :]:
        ax.set_xlabel("Terminal wholesale price, £/MWh", fontsize=9, color=CHART_INK_MUTED)
    for ax in axes[:, 0]:
        ax.set_ylabel("Capex overrun multiplier, x", fontsize=9, color=CHART_INK_MUTED)

    fig.suptitle("Where strategies lose money -- rigid strategies fail at a sharp price/capex corner,\n"
                 "flexible strategies fail more diffusely",
                 fontsize=13, color=CHART_INK, fontweight="bold", y=1.02)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(sm, ax=axes, shrink=0.8, pad=0.02)
    cbar.set_label("log1p(regret vs best build strategy), £m", fontsize=9, color=CHART_INK_MUTED)

    handles = [plt.Line2D([0], [0], color=CHART_INK, linewidth=2,
                          label=f"Binary-loss PRIM box (density ≥ {NO_BOX_DENSITY_THRESHOLD})")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.01), frameon=False, fontsize=9)
    fig.tight_layout(rect=[0, 0.03, 0.9, 0.93])

    path = os.path.join(HEADLINE_DIR, f"{out_name}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=CHART_SURFACE)
    plt.close(fig)
    return path


# PLOT A -- same design as plot_loss_regret_scatter_by_strategy, demand x
# background axes instead of price x capex. Colour scale: log1p(regret), no
# 95th-pct clip -- plot_loss_regret_scatter_by_strategy doesn't clip either
# (see its own comment), and since regret is a per-draw/per-strategy scalar
# independent of which 2 dims it's plotted against, recomputing the norm here
# from the same compute_regret() calls yields the numerically identical scale
# -- "reuse the exact norm" is satisfied by construction, not by caching.
# Panel titles are derived from box_bounds_dict, not hardcoded: both dims
# restricted -> "separable"; one unrestricted -> "partial (<dim> unrestricted)";
# no box (density < NO_BOX_DENSITY_THRESHOLD) -> "dispersed, no box".
def plot_loss_regret_scatter_demand_generation(df, boxes, regret_boxes,
                                                out_name="loss_regret_scatter_demand_generation"):
    strategies = REGRET_STRATEGIES
    assert len(strategies) == 4, f"expected 4 strategies for a 2x2 layout, got {strategies}"

    all_regret = pd.concat([compute_regret(df, STRATEGY_TO_COL[s]) for s in strategies])
    vmax = float(np.log1p(all_regret).max())
    norm = mcolors.Normalize(vmin=0.0, vmax=vmax)
    cmap = plt.get_cmap("magma")

    fig, axes = plt.subplots(2, 2, figsize=(10.5, 9.5), facecolor=CHART_SURFACE, sharex=True, sharey=True)
    axes_flat = axes.flatten()

    for ax, name in zip(axes_flat, strategies):
        value_col = STRATEGY_TO_COL[name]
        regret = compute_regret(df, value_col)
        c = np.log1p(regret)

        ax.scatter(df["demand_terminal_gwh"], df["background_terminal_mw"], c=c, cmap=cmap, norm=norm,
                   s=10, alpha=0.85, linewidths=0, zorder=2)

        binary_box = boxes[name]
        if binary_box.density >= NO_BOX_DENSITY_THRESHOLD:
            bounds = box_bounds_dict(binary_box)
            full = binary_box.box_lims[0]
            demand_restricted = "demand_terminal_gwh" in bounds
            bg_restricted = "background_terminal_mw" in bounds
            x_lo, x_hi = bounds.get("demand_terminal_gwh",
                                     (float(full["demand_terminal_gwh"].iloc[0]), float(full["demand_terminal_gwh"].iloc[1])))
            y_lo, y_hi = bounds.get("background_terminal_mw",
                                     (float(full["background_terminal_mw"].iloc[0]), float(full["background_terminal_mw"].iloc[1])))
            ax.add_patch(plt.Rectangle((x_lo, y_lo), x_hi - x_lo, y_hi - y_lo,
                                        fill=False, edgecolor=CHART_INK, linewidth=2, zorder=3))
            if demand_restricted and bg_restricted:
                cause = "separable"
            elif demand_restricted:
                cause = "partial (generation unrestricted)"
            elif bg_restricted:
                cause = "partial (demand unrestricted)"
            else:
                cause = "partial (both unrestricted)"   # box exists (other dims restrict it) but not on these 2
        else:
            ax.text(0.03, 0.03, "no separable loss region\n(price×capex or demand×generation)",
                    transform=ax.transAxes, fontsize=8, color=CHART_INK_MUTED, ha="left", va="bottom",
                    style="italic")
            cause = "dispersed, no box"

        # cause as an in-axes annotation, not appended to the title -- see
        # plot_loss_regret_scatter_by_strategy's identical comment: these
        # cause strings are long enough to overflow a 2x2 column if titled.
        ax.set_yscale("log")
        ax.set_facecolor(CHART_SURFACE)
        ax.set_title(name, fontsize=11, color=CHART_INK, fontweight="bold")
        ax.text(0.03, 0.90, cause, transform=ax.transAxes, fontsize=8.5, color=CHART_INK_MUTED,
                ha="left", va="top", style="italic")
        ax.tick_params(colors=CHART_INK_MUTED, labelsize=8)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

    for ax in axes[-1, :]:
        ax.set_xlabel("Terminal demand, GWh", fontsize=9, color=CHART_INK_MUTED)
    for ax in axes[:, 0]:
        ax.set_ylabel("Terminal background generation, MW", fontsize=9, color=CHART_INK_MUTED)

    fig.suptitle("Where strategies lose money -- demand x background-generation view\n"
                 "(titles reflect what each strategy's box actually restricts on these axes)",
                 fontsize=13, color=CHART_INK, fontweight="bold", y=1.02)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(sm, ax=axes, shrink=0.8, pad=0.02)
    cbar.set_label("log1p(regret vs best build strategy), £m", fontsize=9, color=CHART_INK_MUTED)

    handles = [plt.Line2D([0], [0], color=CHART_INK, linewidth=2,
                          label=f"Binary-loss PRIM box (density ≥ {NO_BOX_DENSITY_THRESHOLD}), projected onto demand x generation")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.01), frameon=False, fontsize=9)

    path = os.path.join(HEADLINE_DIR, f"{out_name}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=CHART_SURFACE)
    plt.close(fig)
    return path


# PLOT 2 -- PRIM frontier. Panel 1: binary density vs coverage, the canonical
# Friedman & Fisher PRIM trade-off curve. Panel 2: continuous mean-regret-in-
# box vs box mass -- RegressionPrimBox exposes no coverage/density (binary-
# only concepts, see Phase 1 report (c)), so mass is the natural x-axis.
# Restricted to the 4 headline strategies in both panels (only they have a
# regret box, for a like-for-like comparison across the two panels).
def plot_prim_frontier(boxes, regret_boxes, out_name="prim_frontier"):
    strategies = REGRET_STRATEGIES

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.4), facecolor=CHART_SURFACE)

    for i, name in enumerate(strategies):
        color = STRATEGY_COLORS_HEX[i % len(STRATEGY_COLORS_HEX)]
        traj = boxes[name].peeling_trajectory
        ax1.plot(traj["coverage"], traj["density"], color=color, linewidth=1.5, alpha=0.85, zorder=2)
        final_id = traj.index[-1]
        cov, dens = traj.loc[final_id, "coverage"], traj.loc[final_id, "density"]
        ax1.scatter([cov], [dens], color=color, s=70, zorder=3, edgecolor=CHART_INK, linewidth=0.8)
        ax1.annotate(f"{name}\ncov={cov:.2f}, dens={dens:.2f}", (cov, dens),
                     textcoords="offset points", xytext=(6, 6), fontsize=7.5, color=CHART_INK)

    ax1.axhline(NO_BOX_DENSITY_THRESHOLD, color=CHART_INK_MUTED, linestyle="--", linewidth=1, zorder=1)
    ax1.text(0.99, NO_BOX_DENSITY_THRESHOLD + 0.02, f"NO_BOX_DENSITY_THRESHOLD = {NO_BOX_DENSITY_THRESHOLD}",
              transform=ax1.get_yaxis_transform(), fontsize=7, color=CHART_INK_MUTED, ha="right")
    ax1.set_xlabel("Coverage", fontsize=10, color=CHART_INK_MUTED)
    ax1.set_ylabel("Density", fontsize=10, color=CHART_INK_MUTED)
    ax1.set_title("Binary loss: density vs coverage", fontsize=11, color=CHART_INK, fontweight="bold")
    ax1.set_xlim(-0.02, 1.02)
    ax1.set_ylim(-0.02, 1.02)
    ax1.set_facecolor(CHART_SURFACE)
    for spine in ("top", "right"):
        ax1.spines[spine].set_visible(False)

    for i, name in enumerate(strategies):
        color = STRATEGY_COLORS_HEX[i % len(STRATEGY_COLORS_HEX)]
        traj = regret_boxes[name].peeling_trajectory
        ax2.plot(traj["mass"], traj["mean"], color=color, linewidth=1.5, alpha=0.85, zorder=2)
        final_id = traj.index[-1]
        mass, mean = traj.loc[final_id, "mass"], traj.loc[final_id, "mean"]
        ax2.scatter([mass], [mean], color=color, s=70, zorder=3, edgecolor=CHART_INK, linewidth=0.8)
        ax2.annotate(f"{name}\nmass={mass:.2f}, mean=£{mean:.1f}m", (mass, mean),
                     textcoords="offset points", xytext=(6, 6), fontsize=7.5, color=CHART_INK)

    ax2.set_xlabel("Box mass (support)", fontsize=10, color=CHART_INK_MUTED)
    ax2.set_ylabel("Mean regret in box, £m", fontsize=10, color=CHART_INK_MUTED)
    ax2.set_title("Regret: mean-in-box vs mass", fontsize=11, color=CHART_INK, fontweight="bold")
    ax2.set_facecolor(CHART_SURFACE)
    for spine in ("top", "right"):
        ax2.spines[spine].set_visible(False)

    handles = [plt.Line2D([0], [0], color=STRATEGY_COLORS_HEX[i % len(STRATEGY_COLORS_HEX)], linewidth=2, label=n)
               for i, n in enumerate(strategies)]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.04), ncol=len(strategies),
               frameon=False, fontsize=9)
    fig.suptitle("PRIM peeling frontier -- binary loss (left) and continuous regret (right)",
                 fontsize=13, color=CHART_INK, fontweight="bold", y=1.03)
    fig.tight_layout()

    path = os.path.join(HEADLINE_DIR, f"{out_name}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=CHART_SURFACE)
    plt.close(fig)
    return path


if __name__ == "__main__":
    df = load_data()
    X = prepare_inputs(df)
    print(f"Loaded {len(df)} draws from {MC_DRAWS_CSV}")
    print(f"OUTCOME = {OUTCOME!r}")

    boxes = {}
    for name, value_col in strategy_col_map().items():
        boxes[name] = run_prim_for_strategy(name, value_col, df, X)

    # ---- regret RegressionPrim run (continuous outcome, alongside binary) ---
    # Runs BEFORE any output is written (including the binary trajectory/box-
    # graph outputs below): if run_regret_prim_for_strategy's maximization
    # tripwire fires for any strategy, it raises and this script halts here --
    # nothing gets saved this run, since Plot 1/2 depend on both binary and
    # regret boxes together.
    regret_boxes = {}
    for name in REGRET_STRATEGIES:
        regret_boxes[name] = run_regret_prim_for_strategy(name, STRATEGY_TO_COL[name], df, X)
    print(f"\nMaximization tripwire passed for all {len(regret_boxes)} regret fits.")

    # ---- binary trajectory / box-graph outputs (only reached past the tripwire) ----
    for name, box in boxes.items():
        csv_path, tradeoff_png_path, box_png_path = save_trajectory(name, box)
        print(f"  trajectory -> {csv_path}")
        print(f"  trade-off plot -> {tradeoff_png_path}")
        print(f"  box graph -> {box_png_path}")

    # ---- box summary table, all strategies, both outcome types --------------
    summary_rows = []
    for name, box in boxes.items():
        # null bounds for a diffuse (density < NO_BOX_DENSITY_THRESHOLD) box --
        # see run_prim_for_strategy's post-find_box() check.
        bounds = None if box.density < NO_BOX_DENSITY_THRESHOLD else box_bounds_dict(box)
        summary_rows.append({"strategy": name, "outcome_type": "binary",
                              "n_points": int(box.peeling_trajectory["n"].iloc[-1]), "mass": float(box.mass),
                              "coverage": box.coverage, "density": box.density, "mean": float(box.mean),
                              "n_restricted_dims": box.res_dim, "bounds": bounds})
    for name, box in regret_boxes.items():
        summary_rows.append({"strategy": name, "outcome_type": "regret",
                              "n_points": int(box.peeling_trajectory["n"].iloc[-1]), "mass": float(box.mass),
                              "coverage": None, "density": None, "mean": float(box.mean),
                              "n_restricted_dims": box.res_dim, "bounds": box_bounds_dict(box)})
    summary_df = pd.DataFrame(summary_rows)
    summary_csv_path = os.path.join(SD_DIR, "box_summary.csv")
    summary_df.to_csv(summary_csv_path, index=False)
    print(f"\nBox summary table -> {summary_csv_path}")
    headline_summary_csv_path = os.path.join(HEADLINE_DIR, "box_summary.csv")
    summary_df.to_csv(headline_summary_csv_path, index=False)
    print(f"Box summary table (Headline_Plots copy) -> {headline_summary_csv_path}")

    # ---- cross-strategy box comparison --------------------------------------
    if PAIRED_DRAWS:
        print("\n=== Cross-strategy box comparison (draws are paired -- see PAIRED_DRAWS comment) ===")
        box_bounds = {name: box_bounds_dict(box) for name, box in boxes.items()}
        all_dims = sorted({dim for b in box_bounds.values() for dim in b})
        for dim in all_dims:
            print(f"  {dim}:")
            for name, b in box_bounds.items():
                bound = b.get(dim, "(unrestricted)")
                print(f"    {name:<18} {bound}")
        # Charts only drop Cost-Aware (prints/box_summary.csv above keep it,
        # and its own single-strategy box_graph/peeling-trajectory outputs
        # are untouched -- this exclusion is for the shared comparison chart only).
        # also excluding any strategy whose box is diffuse (density < NO_BOX_DENSITY_THRESHOLD) --
        # its bounds are already null in box_summary.csv, so there's nothing meaningful to bar-chart.
        plot_boxes = {name: box for name, box in boxes.items()
                      if name != "Flexible 1-Stage (Cost-Aware)" and box.density >= NO_BOX_DENSITY_THRESHOLD}

        comparison_png_path = plot_cross_strategy_comparison(plot_boxes)
        if comparison_png_path:
            print(f"\nCross-strategy comparison plot -> {comparison_png_path}")

        # Focused 2-panel variant of the same figure -- demand and the
        # bg135-crossing year only, for a reader who wants just those two
        # rather than the full dimension survey above.
        demand_bg135_png_path = plot_cross_strategy_comparison(
            plot_boxes, dims=["demand_terminal_gwh", "year_bg135_raw_crossed"],
            out_name="cross_strategy_comparison_demand_bg135")
        if demand_bg135_png_path:
            print(f"Cross-strategy comparison plot (demand & bg135-crossing only) -> {demand_bg135_png_path}")
    else:
        print("\n(draws are NOT paired -- cross-strategy box differences below may partly "
              "reflect sampling noise between independent draw streams, not a genuine "
              "strategy difference. Interpret with caution.)")

    # ---- Plot 1: loss/regret scatter (supersedes plot_price_capex_scatter_by_strategy) ----
    scatter_path = plot_loss_regret_scatter_by_strategy(df, boxes, regret_boxes)
    print(f"\nLoss/regret scatter -> {scatter_path}")

    # ---- Plot 2: PRIM frontier (binary density-coverage + regret mean-vs-mass) ----
    frontier_path = plot_prim_frontier(boxes, regret_boxes)
    print(f"PRIM frontier -> {frontier_path}")

    # ---- Plot A: loss/regret scatter, demand x background-generation axes ---
    # (frontier is axis-independent -- confirmed no Plot B needed, see report)
    demand_gen_scatter_path = plot_loss_regret_scatter_demand_generation(df, boxes, regret_boxes)
    print(f"Loss/regret scatter (demand x generation) -> {demand_gen_scatter_path}")
