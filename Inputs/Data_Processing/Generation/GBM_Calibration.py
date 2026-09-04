# Calibrates DEMAND_GBM_SIGMA, PRICE_GBM_SIGMA and BACKGROUND_GBM_SIGMA
# (System_Model.py's GBM samplers) from measured data rather than unsourced
# placeholders. Imported once at System_Model.py load time; kept out of that
# file since it reaches into the separate Forecasting project folder.

import os
import sys
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))   # .../Coding
PROJECT_ROOT = os.path.abspath(os.path.join(REPO_ROOT, "..", ".."))                       # .../Strategic_Engineering_Project
sys.path.insert(0, REPO_ROOT)

import csv
import numpy as np
from Inputs.Data_Processing.Generation.Prices import PRICES as _HIST_PRICE_TABLE

# Same raw source as System_Model.py's dem_shape_*.npy hourly shapes (see
# Hourly_For_CF.py), just the annual totals rather than the hourly shape
# normalised to sum to 1.
DEMAND_ANNUAL_CSV = os.path.join(PROJECT_ROOT, "Forecasting - Week 1", "Data", "demand_annual_clean.csv")


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


# Std of annual log-changes in the measured ANM demand series (SSEN Orkney).
# Restricted to status=='complete' years, diffed only across consecutive
# complete years so a diff never spans a gap year (2015/2018/2022). Uses raw
# measured demand, not the weather-corrected series Demand.py's trend was fit
# on -- acceptable, that's the kind of unmodelled variation GBM noise is
# meant to capture anyway.
def estimate_demand_gbm_sigma(path=None):
    complete = _load_demand_annual(path)
    years = sorted(complete)
    diffs = [np.log(complete[y + 1]) - np.log(complete[y])
             for y in years if (y + 1) in complete]
    return float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0


DEMAND_GBM_SIGMA_ESTIMATED = estimate_demand_gbm_sigma()   # SSEN ANM annual demand, complete years 2012-2021 -- n=5 consecutive-pair diffs, small sample


# Prices.py's Low/Central/High scenario variants only fan out once
# projections start, so the years where all three columns agree are the
# historical actuals block, not an arbitrarily chosen variant.
PRICE_CRISIS_YEARS = range(2021, 2024)   # gas-price shock, excluded from the "normal times" estimate below


# Returns {year: historical wholesale baseload price, GBP/MWh real} for years
# where Prices.py's Low/Central/High columns all agree, i.e. the
# historical-actuals block, not a scenario projection. Factored out so
# GBM_Correlation.py can reuse the same historical series.
def _load_price_annual(exclude_years=None):
    hist = _HIST_PRICE_TABLE[(_HIST_PRICE_TABLE["Low"] == _HIST_PRICE_TABLE["Central"]) &
                              (_HIST_PRICE_TABLE["Central"] == _HIST_PRICE_TABLE["High"])]["Central"]
    if exclude_years:
        hist = hist[~hist.index.isin(exclude_years)]
    return hist.to_dict()


# Std of annual log-changes in DESNZ Annex M's historical wholesale baseload
# price (GBP/MWh, real). exclude_years drops given years (e.g.
# PRICE_CRISIS_YEARS) before differencing, for a "normal times" estimate.
def estimate_price_gbm_sigma(exclude_years=None):
    hist = _load_price_annual(exclude_years)
    years = sorted(hist)
    diffs = [np.log(hist[y + 1]) - np.log(hist[y]) for y in years if (y + 1) in hist]
    return float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0


PRICE_GBM_SIGMA_ESTIMATED = estimate_price_gbm_sigma()                                               # crisis-inclusive, 2001-2023
PRICE_GBM_SIGMA_ESTIMATED_EXCL_CRISIS = estimate_price_gbm_sigma(exclude_years=PRICE_CRISIS_YEARS)   # 2001-2020 only


# Not a literal match for what BACKGROUND_GBM_SIGMA models (the DFES
# background-generation pipeline's build-out noise, not the existing fleet's
# output) -- there's no historical track record for that specific forecast
# pipeline. This is the closest measured Orkney generation series available,
# the same role PRICE_GBM_SIGMA's UK-wholesale proxy plays for a local price
# series that doesn't exist.
GENERATION_ANNUAL_CSV = os.path.join(PROJECT_ROOT, "Forecasting - Week 1", "Data", "generation_annual_clean.csv")

# generation_annual_clean.csv's own status flag is far stricter than
# demand's (coverage >= ~0.92, keeping only 3 of 10 years: 2012/2020/2021 --
# a single consecutive pair) than demand's own flag (8 of 10 years). A
# day-coverage threshold instead admits partial-coverage years too,
# annualised by dividing by their coverage fraction -- cruder than demand's
# own month-aware backfill, but the best available without redoing the
# cleaning pipeline. 0.75 sits exactly between the weakest year worth
# keeping (2015=0.649) and the run of partial-but-usable years above it
# (2013=0.764 ... 2019=0.877), with 2018 (0.085) and 2022 (0.066) excluded
# either way -- checked directly against the file, not tuned to hit a target
# sample size.
GENERATION_COVERAGE_THRESHOLD = 0.75


# Returns {year: annualised generation energy, MWh} for every year at/above
# threshold day-coverage -- see GENERATION_COVERAGE_THRESHOLD above for why
# 0.75 and why coverage-based admission beats the file's complete flag.
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


# Std of annual log-changes in measured Orkney generation output (see the
# proxy caveat above GENERATION_ANNUAL_CSV). Diffed only across consecutive
# admitted years -- same no-diff-spans-a-gap rule as estimate_demand_gbm_sigma
# -- e.g. 2015 (below threshold) breaks the 2014-2016 pair even though both
# individually clear the bar.
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
