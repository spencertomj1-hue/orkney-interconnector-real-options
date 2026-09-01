# Purpose: see docs/notes/Inputs/Data_Processing/Generation/GBM_Calibration.md#purpose-calibrating-gbm-parameters-from-data

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import csv
import numpy as np
from Inputs.Data_Processing.Generation.Prices import PRICES as _HIST_PRICE_TABLE

# Demand sigma data source: see docs/notes/Inputs/Data_Processing/Generation/GBM_Calibration.md#demand-sigma-data-source
DEMAND_ANNUAL_CSV = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                      "Forecasting - Week 1/Data/demand_annual_clean.csv")


# {year: backfilled annual demand, GWh} for status=='complete' years.
# Factored out so GBM_Correlation.py can reuse the same admitted-year series.
def _load_demand_annual(path=None):
    if path is None:
        path = DEMAND_ANNUAL_CSV
    out = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["status"] == "complete":
                out[int(row["year"])] = float(row["annual_GWh_bf"])
    return out


# Methodology: see docs/notes/Inputs/Data_Processing/Generation/GBM_Calibration.md#estimate_demand_gbm_sigma-methodology
def estimate_demand_gbm_sigma(path=None):
    complete = _load_demand_annual(path)
    years = sorted(complete)
    diffs = [np.log(complete[y + 1]) - np.log(complete[y])
             for y in years if (y + 1) in complete]
    return float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0


DEMAND_GBM_SIGMA_ESTIMATED = estimate_demand_gbm_sigma()   # SSEN ANM annual demand, complete years 2012-2021 -- n=5 consecutive-pair diffs, small sample


# Price sigma: see docs/notes/Inputs/Data_Processing/Generation/GBM_Calibration.md#price-sigma-historical-actuals-definition
PRICE_CRISIS_YEARS = range(2021, 2024)   # gas-price shock, excluded from the "normal times" estimate below


# What counts as historical: see docs/notes/Inputs/Data_Processing/Generation/GBM_Calibration.md#_load_price_annual-what-counts-as-historical
def _load_price_annual(exclude_years=None):
    hist = _HIST_PRICE_TABLE[(_HIST_PRICE_TABLE["Low"] == _HIST_PRICE_TABLE["Central"]) &
                              (_HIST_PRICE_TABLE["Central"] == _HIST_PRICE_TABLE["High"])]["Central"]
    if exclude_years:
        hist = hist[~hist.index.isin(exclude_years)]
    return hist.to_dict()


# What it does: see docs/notes/Inputs/Data_Processing/Generation/GBM_Calibration.md#estimate_price_gbm_sigma-what-it-does
def estimate_price_gbm_sigma(exclude_years=None):
    hist = _load_price_annual(exclude_years)
    years = sorted(hist)
    diffs = [np.log(hist[y + 1]) - np.log(hist[y]) for y in years if (y + 1) in hist]
    return float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0


PRICE_GBM_SIGMA_ESTIMATED = estimate_price_gbm_sigma()                                               # crisis-inclusive, 2001-2023
PRICE_GBM_SIGMA_ESTIMATED_EXCL_CRISIS = estimate_price_gbm_sigma(exclude_years=PRICE_CRISIS_YEARS)   # 2001-2020 only


# What this proxies for: see docs/notes/Inputs/Data_Processing/Generation/GBM_Calibration.md#background-generation-sigma-what-it-proxies-for
GENERATION_ANNUAL_CSV = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                          "Forecasting - Week 1/Data/generation_annual_clean.csv")

# Rationale: see docs/notes/Inputs/Data_Processing/Generation/GBM_Calibration.md#generation_coverage_threshold-rationale
GENERATION_COVERAGE_THRESHOLD = 0.75


# Coverage-based admission: see docs/notes/Inputs/Data_Processing/Generation/GBM_Calibration.md#_load_generation_annual-coverage-based-admission
def _load_generation_annual(path=None, threshold=None):
    if path is None:
        path = GENERATION_ANNUAL_CSV
    if threshold is None:
        threshold = GENERATION_COVERAGE_THRESHOLD
    out = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            coverage = float(row["coverage"])
            if coverage >= threshold:
                out[int(row["year"])] = float(row["energy_mwh"]) / coverage
    return out


# Diff rule: see docs/notes/Inputs/Data_Processing/Generation/GBM_Calibration.md#estimate_background_gbm_sigma-diff-rule
def estimate_background_gbm_sigma(path=None, threshold=None):
    gen = _load_generation_annual(path, threshold)
    years = sorted(gen)
    diffs = [np.log(gen[y + 1]) - np.log(gen[y]) for y in years if (y + 1) in gen]
    return float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0


BACKGROUND_GBM_SIGMA_ESTIMATED = estimate_background_gbm_sigma()   # n=5 diffs at threshold=0.75 -- small sample, see estimate_background_gbm_sigma


if __name__ == "__main__":
    print(f"DEMAND_GBM_SIGMA_ESTIMATED             = {DEMAND_GBM_SIGMA_ESTIMATED:.4f}")
    print(f"PRICE_GBM_SIGMA_ESTIMATED (crisis-in)  = {PRICE_GBM_SIGMA_ESTIMATED:.4f}")
    print(f"PRICE_GBM_SIGMA_ESTIMATED (excl-crisis)= {PRICE_GBM_SIGMA_ESTIMATED_EXCL_CRISIS:.4f}")
    _gen = _load_generation_annual()
    _n_diffs = sum(1 for y in _gen if (y + 1) in _gen)
    print(f"BACKGROUND_GBM_SIGMA_ESTIMATED         = {BACKGROUND_GBM_SIGMA_ESTIMATED:.4f} "
          f"(n={_n_diffs} consecutive-pair diffs from {len(_gen)} admitted years, "
          f"threshold={GENERATION_COVERAGE_THRESHOLD})")
