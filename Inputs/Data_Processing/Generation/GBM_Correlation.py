# Calibrates GBM_SHOCK_CORR (System_Model.py's correlated demand/price/
# background-generation GBM noise) from measured data, rather than the
# unsourced placeholder [demand-price=0.30, demand-background=0.40,
# price-background=0.15] it started as. Kept separate from GBM_Calibration.py
# (pairwise correlation BETWEEN series, not one series' own volatility) but
# reuses that file's per-series admitted-year loaders.

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import numpy as np
from Inputs.Data_Processing.Generation.GBM_Calibration import (
    _load_demand_annual, _load_price_annual, _load_generation_annual,
)

# System_Model.py's original hand-picked placeholders -- used as a fallback
# wherever a pairwise sample is too small to estimate at all, or the
# assembled matrix isn't a valid correlation matrix (see
# _nearest_valid_corr). Kept available as its own matrix too, since
# System_Model.GBM_SHOCK_CORR now points at GBM_SHOCK_CORR_ESTIMATED below --
# Results.py's placeholder-vs-measured sensitivity needs a reference to the
# ORIGINAL guess that isn't just "whatever the active default currently is".
PLACEHOLDER_CORR = {"demand_price": 0.30, "demand_background": 0.40, "price_background": 0.15}
PLACEHOLDER_CORR_MATRIX = np.array([
    [1.00, PLACEHOLDER_CORR["demand_price"], PLACEHOLDER_CORR["demand_background"]],
    [PLACEHOLDER_CORR["demand_price"], 1.00, PLACEHOLDER_CORR["price_background"]],
    [PLACEHOLDER_CORR["demand_background"], PLACEHOLDER_CORR["price_background"], 1.00],
])

# Below this many paired (present in both series, consecutive-year) diffs, a
# correlation estimate is closer to noise than signal -- fall back to the
# placeholder rather than report a number built on 1-2 points.
MIN_PAIRED_DIFFS = 3

# Demand-background measures at -0.51 (n=5 paired years) -- overridden here to
# a small POSITIVE value. Judgement call, not a data problem: 5 years of
# Orkney annual data isn't a reliable guide to the future demand/generation
# relationship, so a mild positive co-movement (shared underlying
# economic-activity driver, the same reasoning System_Model's original
# placeholder used) is kept over the small sample's sign flip.
# demand-price and price-background are NOT overridden -- only this pair.
DEMAND_BACKGROUND_CORR_OVERRIDE = 0.1


# {year: log(series[year+1]) - log(series[year])} for every consecutive pair
# present in series, keyed by the FIRST year of the pair -- so two series'
# diffs can be matched by that key directly (same y -> y+1 transition).
def _log_diffs_by_year(series):
    return {y: np.log(series[y + 1]) - np.log(series[y])
            for y in series if (y + 1) in series}


# Pearson correlation of two {year: log-diff} dicts, restricted to years
# present in BOTH. Small-sample estimate (Orkney annual data, ~10 years
# total) -- not a number to over-trust. Returns None (caller falls back to
# the placeholder) below min_n paired points.
def _paired_correlation(diffs_a, diffs_b, label, min_n=None):
    if min_n is None:
        min_n = MIN_PAIRED_DIFFS
    common_years = sorted(set(diffs_a) & set(diffs_b))
    n = len(common_years)
    if n < min_n:
        print(f"  {label}: only {n} paired year(s) {common_years} -- "
              f"below min_n={min_n}, keeping placeholder")
        return None
    a = np.array([diffs_a[y] for y in common_years])
    b = np.array([diffs_b[y] for y in common_years])
    corr = float(np.corrcoef(a, b)[0, 1])
    print(f"  {label}: n={n} paired years {common_years} -> corr={corr:.2f}")
    return corr


# A 3x3 correlation matrix assembled from three INDEPENDENTLY estimated
# pairwise correlations has no guarantee of being positive semi-definite
# (Cholesky-decomposable, required by sample_correlated_gbm_shocks) the way
# the hand-picked placeholder was. Eigenvalue-clips to the nearest valid
# correlation matrix if needed; a no-op if corr is already valid.
def _nearest_valid_corr(corr):
    try:
        np.linalg.cholesky(corr)
        return corr
    except np.linalg.LinAlgError:
        vals, vecs = np.linalg.eigh(corr)
        vals_clipped = np.clip(vals, 1e-8, None)
        fixed = vecs @ np.diag(vals_clipped) @ vecs.T
        d = np.sqrt(np.diag(fixed))
        fixed = fixed / np.outer(d, d)   # renormalise back to unit diagonal
        print("  assembled matrix wasn't positive semi-definite -- "
              "clipped to the nearest valid correlation matrix")
        return fixed


# Returns (corr_matrix, {pair_name: value_or_None}) -- the 3x3 array is
# always valid (PSD); the dict shows which pairs were actually estimated
# from data vs fell back to PLACEHOLDER_CORR (None = fallback).
def estimate_gbm_shock_corr():
    demand = _load_demand_annual()
    price = _load_price_annual()
    background = _load_generation_annual()

    diffs_demand = _log_diffs_by_year(demand)
    diffs_price = _log_diffs_by_year(price)
    diffs_background = _log_diffs_by_year(background)

    print("GBM shock correlation estimates (Orkney ANM demand/generation + "
          "historical wholesale price, annual log-changes):")
    dp = _paired_correlation(diffs_demand, diffs_price, "demand-price")
    db = _paired_correlation(diffs_demand, diffs_background, "demand-background")
    pb = _paired_correlation(diffs_price, diffs_background, "price-background")
    if db is not None:
        print(f"  demand-background: measured {db:.2f} overridden to "
              f"{DEMAND_BACKGROUND_CORR_OVERRIDE:.2f} (see DEMAND_BACKGROUND_CORR_OVERRIDE)")

    # raw keeps the genuinely MEASURED values (None = fell back to
    # PLACEHOLDER_CORR) for diagnostics/reporting -- the override below is
    # applied only to used, the matrix actually built, so raw stays an
    # honest record of what the data said before the override.
    raw = {"demand_price": dp, "demand_background": db, "price_background": pb}
    used = {k: (v if v is not None else PLACEHOLDER_CORR[k]) for k, v in raw.items()}
    used["demand_background"] = DEMAND_BACKGROUND_CORR_OVERRIDE

    corr = _nearest_valid_corr(np.array([
        [1.00,                    used["demand_price"],      used["demand_background"]],
        [used["demand_price"],    1.00,                       used["price_background"]],
        [used["demand_background"], used["price_background"], 1.00],
    ]))
    return corr, raw


GBM_SHOCK_CORR_ESTIMATED, GBM_SHOCK_CORR_ESTIMATED_RAW = estimate_gbm_shock_corr()


if __name__ == "__main__":
    print("\nGBM_SHOCK_CORR_ESTIMATED (demand, price, background) =")
    print(GBM_SHOCK_CORR_ESTIMATED)
    _n_fallback = sum(1 for v in GBM_SHOCK_CORR_ESTIMATED_RAW.values() if v is None)
    print(f"\n{3 - _n_fallback}/3 pairs estimated from data, "
          f"{_n_fallback}/3 fell back to the placeholder (see MIN_PAIRED_DIFFS)")
