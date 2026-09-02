# Three focused PRIM summary figures for the paper's headline loss-driver
# findings: (1) price & demand, (2) bg135-crossing year, (3) capex overrun.
# Reads the already-computed PRIM boxes from box_summary.csv (no re-run of
# PRIM needed) and the full 2000-draw range from mc_draws.csv.

import ast
import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SD_DIR = os.path.join(THIS_DIR, "Extra")
OUT_DIR = os.path.join(THIS_DIR, "Headline_Plots")

MC_DRAWS_CSV = os.path.join(SD_DIR, "mc_draws.csv")
BOX_SUMMARY_CSV = os.path.join(OUT_DIR, "box_summary.csv")

NEVER_CROSSED_YEAR_SENTINEL = 2052

# 4 headline strategies -- Flexible 1-Stage (Cost-Aware) is excluded from
# these comparison charts, matching the convention already used for
# cross_strategy_comparison.png (box_summary.csv / its own box_graph still
# carry it in full).
STRATEGY_ORDER = ["Baseline", "Fixed 4-Stage", "Flexible 1-Stage", "Flexible 4-Stage"]
STRATEGY_COLORS_HEX = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]

CHART_INK = "#0b0b0b"
CHART_INK_MUTED = "#898781"
CHART_GRIDLINE = "#e1e0d9"
CHART_SURFACE = "#fcfcfb"


def load():
    mc = pd.read_csv(MC_DRAWS_CSV)
    mc["year_bg135_raw_crossed"] = mc["year_bg135_raw_crossed"].fillna(NEVER_CROSSED_YEAR_SENTINEL)
    summary = pd.read_csv(BOX_SUMMARY_CSV)
    summary["bounds"] = summary["bounds"].apply(ast.literal_eval)
    bounds = {row["strategy"]: row["bounds"] for _, row in summary.iterrows()}
    return mc, bounds


def full_range(mc, col):
    return float(mc[col].min()), float(mc[col].max())


def fmt_value(v, unit="", years=False):
    if years:
        return f"{v:.0f}"
    if abs(v) >= 100:
        return f"{v:,.0f}{unit}"
    if abs(v) >= 1:
        return f"{v:,.2f}{unit}"
    return f"{v:.4g}{unit}"


def draw_panel(ax, mc, bounds, dim, label, unit="", log=False, years=False):
    full_lo, full_hi = full_range(mc, dim)
    n = len(STRATEGY_ORDER)
    bar_h = 0.62

    ax.set_facecolor(CHART_SURFACE)
    ax.barh(0, full_hi - full_lo, left=full_lo, height=bar_h * (n + 0.6),
            color=CHART_GRIDLINE, zorder=1)

    restricting = [s for s in STRATEGY_ORDER if dim in bounds[s]]
    y0 = -(len(restricting) - 1) / 2
    row = 0
    for i, name in enumerate(STRATEGY_ORDER):
        b = bounds[name].get(dim)
        if b is None:
            continue
        lo, hi = b
        color = STRATEGY_COLORS_HEX[i]
        y = y0 + row
        ax.barh(y, hi - lo, left=lo, height=bar_h, color=color, zorder=2)
        mid = (lo + hi) / 2 if not log else (lo * hi) ** 0.5
        ax.text(mid, y, f"{fmt_value(lo, unit, years)} – {fmt_value(hi, unit, years)}",
                ha="center", va="center", fontsize=9, color="white", fontweight="bold", zorder=3)
        row += 1

    ax.set_ylim(-(n + 0.6) / 2, (n + 0.6) / 2)
    ax.set_yticks([])
    ax.set_title(label, loc="left", fontsize=12, color=CHART_INK, fontweight="bold", pad=10)
    if log:
        ax.set_xscale("log")
        ax.set_xlim(full_lo * 0.85, full_hi * 1.15)
        ax.xaxis.set_major_locator(mticker.FixedLocator([10, 20, 50, 100, 200, 500, 800]))
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.xaxis.set_minor_locator(mticker.NullLocator())
    ax.tick_params(axis="x", colors=CHART_INK_MUTED, labelsize=9)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(CHART_GRIDLINE)


def add_legend(fig, y=-0.05):
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in STRATEGY_COLORS_HEX]
    fig.legend(handles, STRATEGY_ORDER, loc="lower center", bbox_to_anchor=(0.5, y),
               ncol=len(STRATEGY_ORDER), frameon=False, fontsize=10)


def add_titles(fig, title, subtitle, y_title=1.1, y_subtitle=1.035):
    fig.text(0.01, y_title, title, fontsize=15, color=CHART_INK, fontweight="bold",
              ha="left", transform=fig.transFigure)
    fig.text(0.01, y_subtitle, subtitle, fontsize=10.5, color=CHART_INK_MUTED,
              ha="left", transform=fig.transFigure)


def save(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=CHART_SURFACE)
    plt.close(fig)
    print(f"  -> {path}")


def plot_price_demand(mc, bounds):
    fig, axes = plt.subplots(2, 1, figsize=(9, 4.8), facecolor=CHART_SURFACE)
    draw_panel(axes[0], mc, bounds, "price_terminal_gbp_mwh",
               "Terminal wholesale price (log scale)", " £/MWh", log=True)
    draw_panel(axes[1], mc, bounds, "demand_terminal_gwh", "Terminal demand", " GWh")
    add_titles(fig, "Where strategies lose money: price & demand",
               "PRIM box bounds per strategy vs full range across all 2000 draws — NetZero_Tilt weighting")
    add_legend(fig, y=-0.07)
    fig.text(0.5, -0.13,
              "Grey band = full range across all draws. Coloured bar = this strategy's PRIM box on this "
              "dimension (no bar = unrestricted).",
              ha="center", fontsize=8, color=CHART_INK_MUTED)
    fig.tight_layout()
    save(fig, "price_demand_summary.png")


def plot_bg135_crossing(mc, bounds):
    fig, ax = plt.subplots(1, 1, figsize=(9, 2.6), facecolor=CHART_SURFACE)
    draw_panel(ax, mc, bounds, "year_bg135_raw_crossed",
               "Year background generation first exceeds 135 MW", years=True)
    add_titles(fig, "Where strategies lose money: background-generation timing",
               "Baseline/Fixed strategies are exposed to a LATE crossing; flexible strategies to an EARLY one",
               y_title=1.28, y_subtitle=1.12)
    add_legend(fig, y=-0.22)
    fig.text(0.5, -0.42,
              "Grey band = full range across all draws (2028–2052; 2052 = never crossed within horizon).",
              ha="center", fontsize=8, color=CHART_INK_MUTED)
    fig.tight_layout()
    save(fig, "bg135_crossing_summary.png")


def plot_capex_overrun(mc, bounds):
    fig, ax = plt.subplots(1, 1, figsize=(9, 2.6), facecolor=CHART_SURFACE)
    draw_panel(ax, mc, bounds, "capex_mult", "Capex overrun multiplier", "x")
    add_titles(fig, "Where strategies lose money: capex overrun",
               "PRIM box bounds per strategy vs full range across all 2000 draws — NetZero_Tilt weighting",
               y_title=1.28, y_subtitle=1.12)
    add_legend(fig, y=-0.22)
    fig.text(0.5, -0.42,
              "Grey band = full range across all draws (0.45x–4.56x). All strategies' upper bounds sit at "
              "the sample maximum — the constraint is a floor on overrun, not a ceiling.",
              ha="center", fontsize=8, color=CHART_INK_MUTED)
    fig.tight_layout()
    save(fig, "capex_overrun_summary.png")


if __name__ == "__main__":
    mc, bounds = load()
    print("Writing headline summary plots...")
    plot_price_demand(mc, bounds)
    plot_bg135_crossing(mc, bounds)
    plot_capex_overrun(mc, bounds)
