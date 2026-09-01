# PRIM scenario-discovery pipeline: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#overview

import os
import pandas as pd
import matplotlib.pyplot as plt
from ema_workbench.analysis import prim

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SD_DIR = os.path.join(THIS_DIR, "Extra")
MC_DRAWS_CSV = os.path.join(SD_DIR, "mc_draws.csv")

# OUTCOME definition -- pick the one matching your P(loss) definition.
OUTCOME = "npv_below_zero"          # default: loss = NPV < 0
# alt: "worse_than_do_nothing"      # loss = NPV_strategy - NPV_do_nothing < 0
# alt: "lcoe_above_threshold"       # loss = incremental LCOE vs Do Nothing > LCOE_FAIL_THRESHOLD

# LCOE_FAIL_THRESHOLD cutoff rationale: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#lcoe_fail_threshold-cutoff-rationale
LCOE_FAIL_THRESHOLD = 80.0

# Human-readable form of OUTCOME for chart titles, so titles show "NPV < £0"
# rather than the raw Python identifier "npv_below_zero".
OUTCOME_DISPLAY = {
    "npv_below_zero": "loss defined as NPV < £0",
    "worse_than_do_nothing": "loss defined as NPV worse than Do Nothing",
    "lcoe_above_threshold": f"loss defined as incremental LCOE > £{LCOE_FAIL_THRESHOLD:.0f}/MWh vs Do Nothing",
}

# STRATEGY_TO_COL: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#strategy_to_col-strategy-selection-and-column-naming-convention
STRATEGY_TO_COL = {
    "Baseline": "npv_baseline",
    "Fixed 4-Stage": "npv_fixed_4_stage",
    "Flexible 1-Stage": "npv_flexible_1_stage",
    "Flexible 4-Stage": "npv_flexible_4_stage",
    "Flexible 1-Stage (Cost-Aware)": "npv_flexible_1_stage_(cost_aware)",
}

# STRATEGY_TO_LCOE_COL: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#strategy_to_lcoe_col
STRATEGY_TO_LCOE_COL = {
    "Baseline": "lcoe_baseline",
    "Fixed 4-Stage": "lcoe_fixed_4_stage",
    "Flexible 1-Stage": "lcoe_flexible_1_stage",
    "Flexible 4-Stage": "lcoe_flexible_4_stage",
    "Flexible 1-Stage (Cost-Aware)": "lcoe_flexible_1_stage_(cost_aware)",
}


# strategy_col_map rationale: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#strategy_col_map-why-a-function-not-a-constant
def strategy_col_map():
    return STRATEGY_TO_LCOE_COL if OUTCOME == "lcoe_above_threshold" else STRATEGY_TO_COL

# PRIM parameter defaults: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#peel_alpha-paste_alpha-mass_min-prim-parameter-defaults
PEEL_ALPHA = 0.05
PASTE_ALPHA = 0.05
MASS_MIN = 0.05

# PAIRED_DRAWS: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#paired_draws
PAIRED_DRAWS = True

# NEVER_CROSSED_YEAR_SENTINEL: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#never_crossed_year_sentinel
NEVER_CROSSED_YEAR_SENTINEL = 2052


def load_data():
    if not os.path.exists(MC_DRAWS_CSV):
        raise FileNotFoundError(
            f"{MC_DRAWS_CSV} not found -- run Results.py once with "
            f"System_Model.SCENARIO_DISCOVERY = True first (see that flag's "
            f"comment in System_Model.py for where the capture block lives).")
    return pd.read_csv(MC_DRAWS_CSV)


# prepare_inputs categorical handling: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#prepare_inputs-categorical-handling-of-the-scenario-dimension
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
        # NaN handling under lcoe_above_threshold: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#compute_loss_flag-nan-handling-under-lcoe_above_threshold
        return (df[value_col] > LCOE_FAIL_THRESHOLD).astype(int)
    raise ValueError(f"unknown OUTCOME {outcome!r}")


def run_prim_for_strategy(name, value_col, df, X):
    y = compute_loss_flag(df, value_col, OUTCOME)
    n_pos = int(y.sum())
    print(f"\n=== PRIM: {name} (outcome={OUTCOME}, loss cases = {n_pos}/{len(y)} = {n_pos/len(y):.1%}) ===")

    p = prim.Prim(X, y, peel_alpha=PEEL_ALPHA, paste_alpha=PASTE_ALPHA, mass_min=MASS_MIN)
    box = p.find_box()

    final_id = box.peeling_trajectory.index[-1]
    print(f"  coverage={box.coverage:.3f}  density={box.density:.3f}  "
          f"n_points={int(box.peeling_trajectory.loc[final_id, 'n'])}  res_dim={box.res_dim}")
    box.inspect(final_id)

    return box


# save_trajectory plot choices: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#save_trajectory-plot-choices
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


# box_bounds_dict box_lims structure: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#box_bounds_dict-box_lims-structure-and-restricted-definition
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


# Cross-strategy comparison figure design & colour choices: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#cross-strategy-comparison-figure-design-and-colour-choices
STRATEGY_COLORS_HEX = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#9b59b6"]   # blue, orange, aqua, yellow, purple
CHART_INK = "#0b0b0b"
CHART_INK_MUTED = "#898781"
CHART_GRIDLINE = "#e1e0d9"
CHART_SURFACE = "#fcfcfb"

# COMPARISON_PLOT_EXCLUDE_DIMS rationale: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#comparison_plot_exclude_dims-why-these-dimensions-are-dropped
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


# dims parameter semantics: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#plot_cross_strategy_comparison-dims-parameter-semantics
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
            # categorical dimension rendering: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#categorical-dimension-rendering-in-plot_cross_strategy_comparison
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

        # full-range reference band: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#full-range-reference-band-in-plot_cross_strategy_comparison
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


if __name__ == "__main__":
    df = load_data()
    X = prepare_inputs(df)
    print(f"Loaded {len(df)} draws from {MC_DRAWS_CSV}")
    print(f"OUTCOME = {OUTCOME!r}")

    boxes = {}
    for name, value_col in strategy_col_map().items():
        box = run_prim_for_strategy(name, value_col, df, X)
        boxes[name] = box
        csv_path, tradeoff_png_path, box_png_path = save_trajectory(name, box)
        print(f"  trajectory -> {csv_path}")
        print(f"  trade-off plot -> {tradeoff_png_path}")
        print(f"  box graph -> {box_png_path}")

    # ---- box summary table, all strategies ---------------------------------
    summary_rows = []
    for name, box in boxes.items():
        bounds = box_bounds_dict(box)
        summary_rows.append({"strategy": name, "n_points": int(box.peeling_trajectory["n"].iloc[-1]),
                              "coverage": box.coverage, "density": box.density,
                              "n_restricted_dims": box.res_dim, "bounds": bounds})
    summary_df = pd.DataFrame(summary_rows)
    summary_csv_path = os.path.join(SD_DIR, "box_summary.csv")
    summary_df.to_csv(summary_csv_path, index=False)
    print(f"\nBox summary table -> {summary_csv_path}")

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
        # excluding Flexible 1-Stage (Cost-Aware) from the charts: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#cross-strategy-comparison-excluding-flexible-1-stage-cost-aware-from-the-charts
        plot_boxes = {name: box for name, box in boxes.items() if name != "Flexible 1-Stage (Cost-Aware)"}

        comparison_png_path = plot_cross_strategy_comparison(plot_boxes)
        if comparison_png_path:
            print(f"\nCross-strategy comparison plot -> {comparison_png_path}")

        # focused demand/bg135 comparison variant: see docs/notes/Reporting/ScenarioDiscovery/Scenario_Discovery.md#focused-comparison-variant-demand-and-bg135-crossing-year
        demand_bg135_png_path = plot_cross_strategy_comparison(
            plot_boxes, dims=["demand_terminal_gwh", "year_bg135_raw_crossed"],
            out_name="cross_strategy_comparison_demand_bg135")
        if demand_bg135_png_path:
            print(f"Cross-strategy comparison plot (demand & bg135-crossing only) -> {demand_bg135_png_path}")
    else:
        print("\n(draws are NOT paired -- cross-strategy box differences below may partly "
              "reflect sampling noise between independent draw streams, not a genuine "
              "strategy difference. Interpret with caution.)")
