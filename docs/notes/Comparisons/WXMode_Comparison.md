# WXMode_Comparison.py — notes

Background, citations, and rationale pulled out of `Comparisons/WXMode_Comparison.py` to
keep the module itself short.

## Purpose, replay mechanics, and expected effects

Tests `System_Model.WX_MODE="ar1"` vs the default `"iid"` — does weather persistence
change anything, given the headline no-wind default (`INCLUDE_WIND_BUILDOUT=False`)?

MECHANICAL NOTE: this is the one comparison in this session that CANNOT be a pure
replay. `draw_wx_seq` in the cache was already sampled under `"iid"` — reusing it as-is
is a no-op regardless of what `WX_MODE` is set to now, since `WX_MODE` only affects the
SAMPLING PROCESS (`sample_wx_seq`), not something `Run_Strategy` reads independently at
replay time. So weather sequences are freshly redrawn here (deterministic per-draw seed,
for reproducibility) while capex/scenario/price/demand/background-GBM draws are all
still reused unchanged from the cache — only the weather axis is genuinely new.

WHY THIS MIGHT MATTER (checked analytically first, not assumed): `wx_seq` feeds
`Run_Strategy` in exactly two places — `WIND_CF_BY_YEAR[wx_seq[t]]` (the wind
capacity-factor profile) and `DEM_SHAPE_BY_YEAR[wx_year]` (demand's hourly SHAPE, paired
to the same real weather year). `background_gen_mw` — what the Main Link trigger
actually reads — never touches `wx_seq` at all. So:

- Flexible/Baseline/Staged's TRIGGER TIMING should NOT move under AR1 (the observable it
  watches is weather-independent by construction).
- Flexible 1-Stage (Cost-Aware)'s `npv_proxy` gate IS weather-sensitive (reads
  `curtail_frac`/`gen_total`/`price_gbp_mwh`, all downstream of the wind CF draw) — its
  build decision could genuinely shift.
- Every strategy's NPV distribution SHAPE should widen under AR1: IID lets 33
  independent yearly draws average out (law of large numbers); AR1 persistence creates
  multi-year runs of good/bad wind (and correspondingly good/bad demand shape) that
  don't cancel out. A tail-risk/CVaR effect, not a mean-shift, is the expected
  signature.

## sys path setup for Comparisons scripts

Lives in `Comparisons/` — put `Coding/` (1 level up) back on `sys.path` so the
package-qualified imports below (`Model.System_Model` etc.) still resolve regardless of
invocation cwd.
