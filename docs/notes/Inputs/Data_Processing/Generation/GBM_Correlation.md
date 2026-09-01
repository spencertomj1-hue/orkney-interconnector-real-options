# GBM_Correlation.py — notes

Background pulled out of `Inputs/Data_Processing/Generation/GBM_Correlation.py` to keep the module itself short.

## Module purpose

Calibrates `GBM_SHOCK_CORR` (`System_Model.py`'s correlated demand/price/
background-generation GBM noise) from measured data, rather than the
unsourced placeholder [demand-price=0.30, demand-background=0.40,
price-background=0.15] it started as. Kept separate from
`GBM_Calibration.py` (pairwise correlation BETWEEN series, not one series'
own volatility) but reuses that file's per-series admitted-year loaders.

## PLACEHOLDER_CORR: why it's kept

`System_Model.py`'s original hand-picked placeholders — used as a fallback
wherever a pairwise sample is too small to estimate at all, or the assembled
matrix turns out not to be a valid correlation matrix (see
`_nearest_valid_corr`). Kept available as its own matrix
(`PLACEHOLDER_CORR_MATRIX`) too, since `System_Model.GBM_SHOCK_CORR` itself
now points at `GBM_SHOCK_CORR_ESTIMATED` below — `Results.py`'s
placeholder-vs-measured sensitivity needs a reference to the ORIGINAL guess
that isn't just "whatever the active default currently is".

## MIN_PAIRED_DIFFS rationale

Below this many paired (i.e. present in both series, consecutive-year)
diffs, a correlation estimate is closer to noise than signal — fall back to
the placeholder rather than report a number built on 1-2 points.

## DEMAND_BACKGROUND_CORR_OVERRIDE rationale

Demand-background measures at -0.51 (n=5 paired years) — overridden here to
a small POSITIVE value instead. This is a judgement call, not a data
problem: 5 years of Orkney annual data isn't judged a reliable guide to the
future demand/generation relationship, so a mild positive co-movement
(shared underlying economic-activity driver, the same reasoning
`System_Model`'s original placeholder used) is kept over the small sample's
sign flip. demand-price and price-background are NOT overridden — this
applies to demand-background only.

## _log_diffs_by_year

Returns `{year: log(series[year+1]) - log(series[year])}` for every
consecutive pair present in `series`, keyed by the FIRST year of the pair —
so two series' diffs can be matched by that key directly (same y -> y+1
transition).

## _paired_correlation

Pearson correlation of two `{year: log-diff}` dicts, restricted to years
present in BOTH. Small-sample estimates (Orkney annual data, ~10 years
total) — not a number to over-trust. Returns `None` (caller falls back to
the placeholder) below `min_n` paired points.

## _nearest_valid_corr

A 3x3 correlation matrix assembled from three INDEPENDENTLY estimated
pairwise correlations has no guarantee of being positive semi-definite
(Cholesky-decomposable, required by
`System_Model.sample_correlated_gbm_shocks`) the way the hand-picked
placeholder was. Eigenvalue-clips to the nearest valid correlation matrix if
needed; a no-op if `corr` is already valid.

## estimate_gbm_shock_corr: return value

Returns `(corr_matrix, {pair_name: value_or_None})` — the 3x3 array is
always valid (PSD); the dict shows which pairs were actually estimated from
data vs fell back to `PLACEHOLDER_CORR` (`None` = fallback).

## raw vs used: honest record

`raw` keeps the genuinely MEASURED values (`None` = fell back to
`PLACEHOLDER_CORR`) for diagnostics/reporting — the override below is
applied only to `used`, the matrix actually built, so `raw` stays an honest
record of what the data said before the override.
