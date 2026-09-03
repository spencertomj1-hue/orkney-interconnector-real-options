# Bootstrap CI on the staging x optionality interaction term. Diagnostic only
# -- reads mc_draws.csv (verified row-identical to Results.py's marg_store via
# headline_mc.pkl provenance, see conversation), no model/valuation code touched.

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
MC_DRAWS_CSV = os.path.join(THIS_DIR, "Extra", "mc_draws.csv")
OUT_DIR = os.path.join(THIS_DIR, "Main_Plots")

CHART_INK = "#0b0b0b"
CHART_INK_MUTED = "#898781"
CHART_SURFACE = "#fcfcfb"

N_BOOTSTRAP = 1000
SEED = 42


def _summarize(name, point, boot):
    lo, hi = np.percentile(boot, [2.5, 97.5])
    frac_neg = float((boot < 0).mean())
    straddles = bool(lo < 0 < hi)
    print(f"\n{name}:")
    print(f"  point estimate = £{point/1e6:+.2f}m")
    print(f"  bootstrap mean = £{boot.mean()/1e6:+.2f}m   std = £{boot.std()/1e6:.2f}m")
    print(f"  95% CI = [£{lo/1e6:+.2f}m, £{hi/1e6:+.2f}m]")
    print(f"  fraction of bootstrap samples < 0 = {frac_neg:.3f}")
    print(f"  CI straddles zero: {straddles}")
    return lo, hi, frac_neg, straddles


def bootstrap_interaction(seed=SEED, n_boot=N_BOOTSTRAP, make_plot=True):
    df = pd.read_csv(MC_DRAWS_CSV)
    B = df["npv_baseline"].to_numpy()
    F = df["npv_fixed_4_stage"].to_numpy()
    X1 = df["npv_flexible_1_stage"].to_numpy()
    X4 = df["npv_flexible_4_stage"].to_numpy()
    n = len(df)

    # raw £ per draw
    interaction_i = X4 - F - X1 + B
    staging_i = ((F - B) + (X4 - X1)) / 2
    optionality_i = ((X1 - B) + (X4 - F)) / 2

    point_interaction = float(interaction_i.mean())
    point_staging = float(staging_i.mean())
    point_optionality = float(optionality_i.mean())

    print(f"n draws = {n}")
    print(f"Point estimate: mean(interaction_i) = £{point_interaction/1e6:+.2f}m")

    # Resample the SAME index into all four arrays each iteration -- resampling
    # each strategy independently would break the paired-draws structure.
    rng = np.random.default_rng(seed)
    boot_interaction = np.empty(n_boot)
    boot_staging = np.empty(n_boot)
    boot_optionality = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_interaction[b] = interaction_i[idx].mean()
        boot_staging[b] = staging_i[idx].mean()
        boot_optionality[b] = optionality_i[idx].mean()

    print(f"\n=== Bootstrap results (N={n_boot} resamples, £m) ===")
    interaction_summary = _summarize("interaction (Flex4 - Fixed - Flex1 + Baseline)",
                                      point_interaction, boot_interaction)
    _summarize("staging_effect (Shapley)", point_staging, boot_staging)
    _summarize("optionality_effect (Shapley)", point_optionality, boot_optionality)

    if not make_plot:
        return

    lo, hi, frac_neg, straddles = interaction_summary
    fig, ax = plt.subplots(figsize=(7.5, 4.5), facecolor=CHART_SURFACE)
    ax.hist(boot_interaction / 1e6, bins=40, color="#2a78d6", alpha=0.85, zorder=2)
    ax.axvline(0, color=CHART_INK, lw=1.5, ls="-", zorder=3)
    ax.axvline(lo / 1e6, color=CHART_INK_MUTED, lw=1.2, ls="--", zorder=3)
    ax.axvline(hi / 1e6, color=CHART_INK_MUTED, lw=1.2, ls="--", zorder=3)
    ax.axvline(point_interaction / 1e6, color="#eb6834", lw=2, ls="-", zorder=4)
    ax.set_facecolor(CHART_SURFACE)
    ax.set_xlabel("Bootstrap mean interaction, £m")
    ax.set_ylabel("Bootstrap samples")
    ax.set_title("Staging x optionality interaction -- bootstrap distribution (N=1000)",
                 fontsize=12, color=CHART_INK, fontweight="bold")
    ax.text(0.02, 0.95,
            f"point = £{point_interaction/1e6:+.1f}m\n95% CI = [£{lo/1e6:+.1f}m, £{hi/1e6:+.1f}m]\n"
            f"straddles zero: {straddles}",
            transform=ax.transAxes, va="top", fontsize=9, color=CHART_INK)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()

    path = os.path.join(OUT_DIR, "interaction_bootstrap.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=CHART_SURFACE)
    plt.close(fig)
    print(f"\nBootstrap distribution plot -> {path}")
    return path


if __name__ == "__main__":
    bootstrap_interaction()
