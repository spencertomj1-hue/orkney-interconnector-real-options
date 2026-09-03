# System_Model.py — key points (line directory)

Quick-navigation index for `Model/System_Model.py` (402 lines). Line numbers are a snapshot as of this session's cleanup/split (Uncertainty.py + Strategies.py factored out) — re-check after any further edits to the file, since inserting/deleting lines above an entry shifts everything below it.

## Imports & setup — lines 1-32
| Line | What |
|---|---|
| 1-5 | Citation header ([1]-[3]) |
| 7-10 | Stdlib imports + sys.path bootstrap |
| 13-16 | Options / Model_Components / Decision_Rules / Demand imports |
| 19-25 | Re-imports from `Uncertainty.py` (weather, GBM sampling, capex calibration) |
| 28 | Re-imports from `Strategies.py` (`Strategies_2`, `Strategies_Flex`, `_flexible_cost_aware`, `_flexible_staged`) |
| 29-32 | Data-processing imports (`PV_CF`, `BACKGROUND`, `price_series`) + `lru_cache` |

## Module flags & constants — lines 34-132
| Line | What |
|---|---|
| 36 | `SCENARIO_DISCOVERY` — gates Results.py's PRIM-capture block |
| 40-45 | `price_series()` / `_price_series_cached()` — memoised price lookup |
| 47 | `MARINE_CF` |
| 49 | `RATE` — default discount rate |
| 51-53 | `GREEN_BOOK_SCHEDULE` — declining-rate table |
| 55 | `DISCOUNT_MODE` — `"flat"` \| `"green_book_declining"` |
| 60-64 | `_green_book_year_rate(i)` |
| 66-72 | `discount_factor(t)` |
| 76 | `CONSTRAINT_COST` — £/MWh spill cost |
| 79 | `CONSTRAINT_COST_SWEEP` |
| 83 | `RESIDUAL_ON_OVERRUN` |
| 85-90 | `PROFILES` — PV + synthetic Marine tidal profile |
| 92-93 | `YEARS`, `END_YEAR` |
| 97 | `PRICE_BASE_YEAR` |
| 101-103 | `CPI_PATH`, `CPI_FLAT_ASSUMPTION_RATE` |
| 105-114 | `_load_cpi_by_year()` |
| 116 | `CPI_BY_YEAR` |
| 118 | `CFD_STRIKE` |
| 122-124 | `GROWTH_INDEX_BLEND_WEIGHT` / `GROWTH_INDEX_DEMAND_REF` / `GROWTH_INDEX_BG_REF` |
| 127-129 | `set_rate(r)` — rebinds `RATE`, used by Sensitivities.py |
| 131-132 | `G`, `L` — the module-level `Generation_Capacity`/`Link_Capacity` instances `Run_Strategy` mutates |

## `Run_Strategy(...)` — lines 134-349 (the core simulation loop)
| Line | What |
|---|---|
| 134 | Signature |
| 137-143 | Defaults: `wx_seq` -> `BASE_WEATHER_YEAR`, `capex_estimate_seq` -> flat `capex_mult` |
| 145-146 | `G.RESET()` / `L.RESET()` |
| 148-155 | Cost/energy accumulators + LCOT trackers (`link_cost_t`, `pv_link_export`) |
| 159 | `PRICE_YR` — deterministic lookup or injected `price_seq` |
| 163-168 | Split `Options` into `fixed_decisions` / `rules`; init `rule_log` |
| 173 | `_needed_observables` — skip-if-unneeded set |
| 177-187 | `state` dict — per-year observables rules read from |
| 189-193 | `is_live(asset_name, yr)` helper (prereq gating) |
| 195-198 | Year loop starts; `discount_factor(t)` per year |
| 200-210 | Fixed `Decision`s: charge capex, add capacity (Generation vs Link) |
| 212-221 | Fired rule `Decision`s: same, for rules that already fired |
| 223-224 | Opex (total + Link-only) |
| 226-239 | Generation capacity for the year + DFES background addition (existing-fleet nameplate subtracted) |
| 241-252 | `growth_index` computation (Fix A composite observable) |
| 254-261 | Dispatch: `profiles` (incl. `WIND_CF_BY_YEAR[wx_seq[t]]`), `gen_by_tech`, `gen_h` |
| 263-269 | `dem_h`, `link` capacity, `local`/`surplus`/`export` split |
| 271-276 | `delivered`, `pv_energy`, curtailment (`spilled`), constraint-relief cost |
| 278-293 | CFD share calc + blended price + `pv_revenue` |
| 295-305 | Per-year observable storage (`curtail_frac`, `headroom_p90`, `delivered`, `gen_total`, `price_gbp_mwh`) |
| 307-325 | Rule evaluation loop — `maybe_fire`, fired-rule bookkeeping, same-year build charge |
| 327-340 | Residual value credited at horizon (`END_YEAR`) |
| 342 | `npv = pv_revenue - total_cost_t` |
| 344-349 | Stash LCOT fields into `state`; return `(total_cost_t, pv_energy, total_curtail, npv, state, rule_log)` |

## Scenario data — lines 352-369
| Line | What |
|---|---|
| 352-358 | `Scenarios` dict — name -> demand path |
| 360 | `DFES_ONLY` |
| 364-369 | `SCENARIO_WEIGHTS` — `"Equal"` / `"NetZero_Tilt"` |

## Where the rest of the model lives
- Weather library, GBM demand/price/background sampling, capex cost-overrun calibration -> `Model/Uncertainty.py`
- Rigid/flexible strategy factories (`Strategies_2`, `Strategies_Flex`) -> `Model/Strategies.py`
- `Rule`/`FiredDecision`/trigger factories -> `Model/Decision_Rules.py`
- Asset classes (`NewLink`, `StagedLinkStage`, ...) -> `Model/Options.py`
- `Decision`, `Generation_Capacity`, `Link_Capacity`, existing fleet -> `Model/Model_Components.py`
