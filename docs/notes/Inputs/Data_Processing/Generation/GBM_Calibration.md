# GBM_Calibration.py — notes

Background pulled out of `Inputs/Data_Processing/Generation/GBM_Calibration.py` to keep the module itself short.

## Purpose: calibrating GBM parameters from data

Calibrates `DEMAND_GBM_SIGMA`, `PRICE_GBM_SIGMA` and `BACKGROUND_GBM_SIGMA`
(`System_Model.py`'s GBM samplers) from measured data rather than unsourced
placeholders. Imported once at `System_Model.py` load time; kept out of that
file since it reaches into the separate Forecasting project folder.

## Demand sigma: data source

Same raw source as `System_Model.py`'s `dem_shape_*.npy` hourly shapes (see
`Inputs/Data_Processing/CF/Hourly_For_CF.py`), just the annual totals rather
than the hourly shape normalised to sum to 1.

## estimate_demand_gbm_sigma: methodology

Std of annual log-changes in the measured ANM demand series (SSEN Orkney).
Restricted to `status=='complete'` years, diffed only across CONSECUTIVE
complete years so a diff never spans a gap year (2015/2018/2022). Caveat:
this uses raw measured demand, not the weather-corrected series `Demand.py`'s
TREND was fit on — treated as acceptable, that's the kind of unmodelled
variation GBM noise is meant to capture anyway.

## Price sigma: historical actuals definition

`Prices.py`'s Low/Central/High scenario variants only fan out once
projections start, so the years where all three columns agree are the
historical actuals block, not an arbitrarily chosen variant.

## _load_price_annual: what counts as historical

Returns `{year: historical wholesale baseload price, GBP/MWh real}` for
years where `Prices.py`'s Low/Central/High columns all agree, i.e. the
historical-actuals block, not a scenario projection. Factored out so
`GBM_Correlation.py` can reuse the same historical series.

## estimate_price_gbm_sigma: what it does

Std of annual log-changes in DESNZ Annex M's historical wholesale baseload
price (GBP/MWh, real). `exclude_years` drops given years before differencing
— e.g. `PRICE_CRISIS_YEARS` — for a "normal times" estimate instead.

## Background generation sigma: what it proxies for

Not a literal match for what `BACKGROUND_GBM_SIGMA` models (the DFES
background-generation PIPELINE's build-out noise, not the existing fleet's
output) — there's no historical track record for that specific forecast
pipeline (see the TODO this replaces, in `System_Model.py`). This is the
closest measured Orkney generation series available, the same role as
`PRICE_GBM_SIGMA`'s UK-wholesale proxy standing in for a local price series
that doesn't exist.

## GENERATION_COVERAGE_THRESHOLD rationale

`generation_annual_clean.csv`'s own `status` flag is far stricter than
demand's (coverage >= ~0.92, keeping only 3 of 10 years: 2012/2020/2021 — a
single consecutive pair) than demand's own flag (8 of 10 years). Using a
day-coverage THRESHOLD instead admits partial-coverage years too, annualised
by dividing by their coverage fraction — a crude uniform-rate backfill
(cruder than demand's own month-aware `annual_GWh_bf`, but the best
available without redoing the cleaning pipeline). 0.75 sits exactly between
the weakest year worth keeping (2015=0.649) and the run of partial-but-usable
years above it (2013=0.764 ... 2019=0.877), with 2018 (0.085) and 2022
(0.066) excluded either way — checked directly against the file (see
coverage column), not tuned to hit a target sample size.

## _load_generation_annual: coverage-based admission

Returns `{year: annualised generation energy, MWh}` for every year at/above
`threshold` day-coverage. See "GENERATION_COVERAGE_THRESHOLD rationale"
above for why 0.75 and why coverage-based admission beats the file's
`complete` flag.

## estimate_background_gbm_sigma: diff rule

Std of annual log-changes in measured Orkney generation output (see
"Background generation sigma: what it proxies for" above for the caveat on
what this proxies for). Diffed only across consecutive admitted years — same
no-diff-spans-a-gap rule as `estimate_demand_gbm_sigma` — e.g. 2015 (below
threshold) breaks the 2014-2016 pair even though both individually clear the
bar.
