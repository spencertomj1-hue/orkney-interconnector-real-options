# Module purpose: see docs/notes/Inputs/Data_Processing/Generation/GBM_Correlation.md#module-purpose

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import numpy as np
from Inputs.Data_Processing.Generation.GBM_Calibration import (
    _load_demand_annual, _load_price_annual, _load_generation_annual,
)

# Why kept: see docs/notes/Inputs/Data_Processing/Generation/GBM_Correlation.md#placeholder_corr-why-its-kept
PLACEHOLDER_CORR = {"demand_price": 0.30, "demand_background": 0.40, "price_background": 0.15}
PLACEHOLDER_CORR_MATRIX = np.array([
    [1.00, PLACEHOLDER_CORR["demand_price"], PLACEHOLDER_CORR["demand_background"]],
    [PLACEHOLDER_CORR["demand_price"], 1.00, PLACEHOLDER_CORR["price_background"]],
    [PLACEHOLDER_CORR["demand_background"], PLACEHOLDER_CORR["price_background"], 1.00],
])

# Rationale: see docs/notes/Inputs/Data_Processing/Generation/GBM_Correlation.md#min_paired_diffs-rationale
MIN_PAIRED_DIFFS = 3

# Rationale: see docs/notes/Inputs/Data_Processing/Generation/GBM_Correlation.md#demand_background_corr_override-rationale
DEMAND_BACKGROUND_CORR_OVERRIDE = 0.1


# see docs/notes/Inputs/Data_Processing/Generation/GBM_Correlation.md#_log_diffs_by_year
def _log_diffs_by_year(series):
    return {y: np.log(series[y + 1]) - np.log(series[y])
            for y in series if (y + 1) in series}


# see docs/notes/Inputs/Data_Processing/Generation/GBM_Correlation.md#_paired_correlation
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


# see docs/notes/Inputs/Data_Processing/Generation/GBM_Correlation.md#_nearest_valid_corr
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


# Return value: see docs/notes/Inputs/Data_Processing/Generation/GBM_Correlation.md#estimate_gbm_shock_corr-return-value
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

    # raw vs used: see docs/notes/Inputs/Data_Processing/Generation/GBM_Correlation.md#raw-vs-used-honest-record
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
