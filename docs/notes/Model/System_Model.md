# System_Model.py — notes

Background, citations, and design rationale pulled out of `Model/System_Model.py`
(the main simulation entry point) to keep the module itself readable. Short
inline citation tags and one/two-line WHY comments stay in the code; this
file holds the full references and every longer rationale block, in the
order they appear in the source.

## References

[1] Henao, A., Sauma, E., Reyes, T., Gonzalez, A. (2017). What is the value of the option to defer an investment in Transmission Expansion Planning? An estimation using Real Options. Energy Economics 65, 194-207.

[2] Nur, G.N., MacKenzie, C.A., Min, K.J. (2026). Valuation of a sequential compound option considering electricity generation and transmission expansions. Journal of Economy and Technology 4, 57-76.

[3] Graça Gomes, J., Cardin, M.-A., Wu, B. (2025). Strategic real options and flexibility analysis for solar PV power plants. IET Powering Net Zero (PNZ 2025), Glasgow, UK.

## Scenario discovery capture switch: SCENARIO_DISCOVERY

Gates a post-hoc PRIM-input capture block in `Results.py`, added right after the headline marginalised MC loop (`System_Model.py` itself has no MC loop to hook into — `Results.py`'s `run_marginalised()` is where per-draw NPV is produced, see `Scenario_Discovery.py`'s own header comment for the full pipeline).

False: `Results.py`'s capture block is skipped entirely — no file written, no import of anything new (not even pandas, which the capture block imports only inside its own `if` branch), no behaviour change anywhere in this file or `Results.py`. Never read the PRIM library itself from here or from `Results.py` — that stays isolated in `Scenario_Discovery.py`, a standalone file this model never imports.

Turned ON (True): so a future full `Results.py` run keeps `Extra/ScenarioDiscovery/mc_draws.csv` in sync with `headline_mc.pkl` automatically, rather than the two silently drifting apart the way `headline_mc.pkl` itself once did against a stale `INCLUDE_WIND_BUILDOUT` assumption. The CSV was regenerated for the current link-only, no-wind default via a standalone replay (matching every other cache-replay script this session), not by running `Results.py` in full — the stale (with-wind, pre-`INCLUDE_WIND_BUILDOUT`-flip, pre-`npv_proxy`-fix) CSV was backed up to `Extra/ScenarioDiscovery/mc_draws_stale_withwind_aug20.csv.bak` first.

## Green Book discount rate schedule

HM Treasury Green Book's actual declining long-term discount rate schedule, current as of the 2026 Green Book (a rate review is underway but the 2026 edition retains this schedule pending its outcome). `(year_upper_bound_inclusive, rate)` pairs, rate applies to appraisal years 1..upper at that band; only the first two bands are ever reached by this model's 33-year (2019-2051) horizon.

## discount_factor: cumulative discount logic

Cumulative discount factor at year-index t (t=0 = base year 2019, undiscounted). `DISCOUNT_MODE="flat"` (default): `(1+RATE)**t`, one rate throughout. `"green_book_declining"`: a cumulative PRODUCT of each year's own Green Book rate (`GREEN_BOOK_SCHEDULE`), not just a different `RATE` plugged into the same flat formula.

## Constraint-relief cost: CONSTRAINT_COST

£/MWh, on spilled generation — the interconnector's primary Ofgem needs-case benefit, and the same role a congestion/deferral penalty plays in [1]'s TEP real-options model: a strictly positive cost charged while the network stays congested, so it accrues fastest under the rigid/deferred strategies here and drops out once capacity is built.

£55/MWh = regulator-vetted CENTRAL, GHD Western Isles Transmission CBA (Aug 2018, §6.2.2); £70 = same source's conservative upper; realised Scotland cost was £98/MWh in 2017/18 (National Grid MBSS), so £55 is conservative. Rebased 2018->2023.

## Residual value on capex overrun: RESIDUAL_ON_OVERRUN

Link `Capex()` includes the stochastic overrun draw — crediting residual value on that (`RESIDUAL_ON_OVERRUN=True`) would refund a cost overrun as salvage. Default False: residual computed on base capex (`capex_mult=1.0`). Generation assets unaffected — they never take `capex_mult` at all.

## Corrected multi-year wind library: WEATHER_YEARS

Bias-corrected Renewables.ninja. Restricted to years with matched ANM demand data (`DEM_SHAPE_BY_YEAR`) — 2015/2018 dropped for coverage gaps. Gross CF only — `AVAIL` applied here once, not in the dispatch loop.

## compute_wind_cf_by_year: per-year CF library

`{year: gross CF array}` for every `WEATHER_YEARS`, at the given `AVAIL` (wake + availability + electrical losses). Factored out of the module-level `WIND_CF_BY_YEAR` computation so `Results.py`'s `AVAIL` sensitivity can recompute the library at an alternate `AVAIL` and swap it in — unlike `CONSTRAINT_COST`, `WIND_CF_BY_YEAR` is baked in once, not read fresh per year, so it has to be recomputed wholesale.

## Noisy early capex_mult estimate for the cost-aware rule

`make_main_link_rule_cost_aware` gates on this: `capex_mult` is only known exactly at build time in reality, so treating it as known from year 0 would let the rule "see" information the 2019 vantage point doesn't have.

## Demand and price noise: anchored to the DFES and scenario backbone

`Demand.py` and `Prices.py` are both deterministic. Multiplying each by its own cumulative unit-mean mean-reverting multiplier path (`_ou_mult_seq`, below) adds persistent, year-to-year-correlated spread while leaving the deterministic backbone as the exact expected path.

Modelling electricity demand this way as a multiplicative shock around a deterministic backbone follows [2]'s demand-uncertainty treatment for its own binomial-lattice real-options model, and is the same multiplicative-shock construction (`y(t) = y(t-1)*eps(t)`) [3] uses for its uncertain driver (there, PV effective availability) — both cited for the multiplicative-anchoring IDEA, not for mean reversion specifically, which this project adopted afterwards (see `_ou_mult_seq`'s own comment for why).

Opposite structure from `sample_capex_estimate_seq` above: that draws independent shocks with variance shrinking to 0 over time; this accumulates as a bounded mean-reverting process instead. Sigmas calibrated in `GBM_Calibration.py` — that calibration (year-on-year log-difference volatility from measured data) is a property of the DATA, not of any particular downstream process, so it stays valid input to a mean-reverting process, not just a random walk.

## Price GBM sigma: crisis-inclusive default

Crisis-inclusive (2001-2023) by default — a Monte Carlo risk model arguably should see the 2021-23 gas-price shock's tail rather than assume it away. Swap in `PRICE_GBM_SIGMA_ESTIMATED_EXCL_CRISIS` (2001-2020 only, ~0.34 vs ~0.46) for a "normal times" volatility assumption instead.

## Mean-reversion half-lives: PRICE_MR and DEMAND_MR

Half-lives, years, for the mean-reverting demand/price paths (see `_ou_mult_seq`): how long an above/below-backbone deviation takes to decay halfway back toward the deterministic DFES/scenario path. ILLUSTRATIVE, not data-calibrated (same caveat as `WIND_AR1_RHO`/`BACKGROUND_MR_HALFLIFE_YEARS`: nowhere near enough historical data to fit a reversion rate for any of these three drivers).

The DIFFERENCE between them is a real-world judgement call, though, not arbitrary: wholesale electricity/commodity prices are routinely modelled as mean-reverting on a timescale of a few years in the energy-economics literature (e.g. Schwartz-style single-factor mean-reverting price models used for commodity real options), reverting much faster than demand — output/demand shocks are closer to a persistent random walk in standard macro treatments, so a longer half-life reflects that relative persistence.

## _ou_mult_seq: mean-reverting multiplier path

Mean-reverting (Ornstein-Uhlenbeck, in log-space) multiplier path: shared by `sample_demand_seq`, `sample_price_seq` and `sample_background_seq`. `log_m[t]` pulls back toward `mu_target` at rate `theta` each year (decay = `exp(-theta*dt)`) instead of random-walking freely — unlike a pure random walk, whose log-variance grows LINEARLY and unboundedly with horizon, this process's variance converges to a STATIONARY level.

That was the motivation for adopting it project-wide: an earlier pure-random-walk version of these three samplers produced implausible tails over this model's 26-33 year horizons (one draw's `price_terminal_gbp_mwh` reached over £8000/MWh, ~15000x its deterministic backbone; background generation similarly reached 7739 MW vs a ~370 MW backbone) purely from ordinary compounding, not from any extreme single-year shock.

Discretisation uses the EXACT OU transition (not an Euler approximation), so the stationary variance is hit exactly regardless of step size. `mu_target` is deliberately NOT 0: the deterministic backbone should stay the exact EXPECTED path (a martingale property), so `mu_target` is set so the STATIONARY distribution's mean is exactly 1 — for a lognormal `exp(X)` with `X~N(mu, v)`, `E[exp(X)]=1` requires `mu=-v/2`, and this process's stationary log-variance is `sigma^2/(2*theta)`, giving `mu_target = -sigma^2/(4*theta)`. Path starts at `log_m=0` (multiplier=1, exactly on the backbone). `z_seq`: optional pre-drawn standard-normal shocks, one per year, lets a caller correlate this path with another such path (see `sample_correlated_gbm_shocks`); None (default) draws independent N(0,1) shocks from `rng` itself.

## GBM shock correlation: GBM_SHOCK_CORR

Demand, price and background-generation GBM shocks are correlated, not independent — a cold winter plausibly drives higher demand AND higher gas prices together; independent draws a "diversification benefit" between them that wouldn't really exist, understating tail risk.

Estimated from measured data (see `GBM_Correlation.py` for the full derivation) rather than guessed — replaces the original hand-picked placeholder (demand-price=0.30, demand-background=0.40, price-background=0.15). demand-price=+0.15 and price-background=-0.48 are the measured values (small sample, only 5 paired years); demand-background measured -0.51 but is DELIBERATELY OVERRIDDEN to +0.10 in `GBM_Correlation.py` (`DEMAND_BACKGROUND_CORR_OVERRIDE`) — 5 years judged too thin to trust the sign flip, so a mild positive co-movement is kept instead. `Results.py`'s `GBM_SHOCK_CORR` sensitivity section runs the original placeholder alongside this.

## sample_correlated_gbm_shocks

Draw correlated standard-normal shock paths for demand, price and background-generation GBM noise JOINTLY (via Cholesky decomposition of `corr`), instead of each sampler drawing its own independent shocks. Returns an `(n_years, 3)` array, columns `[demand, price, background]`, row t aligned to calendar year `System_Model.YEARS[t]` — callers must slice consistently with their own year range (`background_gen_mw`'s own series is shorter, starting 2026 not `YEARS[0]=2019` — see `Results.py` for the slicing that keeps calendar-year alignment).

## sample_demand_seq

DFES demand path times a cumulative unit-mean mean-reverting multiplier (`_ou_mult_seq`) — DFES stays the exact expected path, the multiplier only adds persistent spread around it. Pass `z_seq` (e.g. `sample_correlated_gbm_shocks(...)[:, 0]`) to correlate this path with `sample_price_seq`/`sample_background_seq`'s shocks. `halflife`: None (default) reads the module-level `DEMAND_MR_HALFLIFE_YEARS`.

## sample_price_seq

Scenario price path times a cumulative unit-mean mean-reverting multiplier — same anchored construction as `sample_demand_seq` (see `PRICE_MR_HALFLIFE_YEARS`). Pass `z_seq` to correlate with `sample_demand_seq`/`sample_background_seq`'s shocks.

## BACKGROUND_GBM_SIGMA calibration

DFES background generation is a forecast pipeline with no historical track record, so this is calibrated instead from measured Orkney generation OUTPUT (ANM, same source as `DEMAND_GBM_SIGMA`) as the closest available proxy — see `GBM_Calibration.estimate_background_gbm_sigma`. Lands at ~0.185, between `DEMAND_GBM_SIGMA` (~0.062) and `PRICE_GBM_SIGMA` (~0.34-0.46), same ordering the old unsourced 0.12 placeholder assumed.

## BACKGROUND_MR_HALFLIFE_YEARS

Half-life, years, for the mean-reverting background sampler: how long an above/below-backbone deviation takes to decay halfway back toward the deterministic DFES path. ILLUSTRATIVE, not data-calibrated — same caveat as `WIND_AR1_RHO`: only ~5 paired years of Orkney background-generation data exist, nowhere near enough to fit a reversion rate from data. 8 years is a rough guess at grid-connection-queue/planning-cycle timescales, not a fitted value — treat as a tunable assumption, not an estimated constant.

A pure-random-walk version of this sampler was tried first and abandoned: its unbounded compounding produced `background_terminal_mw` draws as high as 7739 MW against a ~370 MW deterministic backbone (one draw's 26 yearly shocks happened to average +0.68 instead of the ~0 a random sequence should average to) — an ordinary consequence of a random walk's linearly growing variance over a 26-year horizon, not an extreme single-year event.

## sample_background_seq

DFES background generation path (`base_background = BACKGROUND[scenario]`, a DataFrame indexed by year with one MW column per tech) times a cumulative unit-mean mean-reverting multiplier (`_ou_mult_seq`). ONE shared multiplier per year across every tech column (a "DFES pipeline running ahead of/behind schedule" shock), not independent per-technology noise. Only spans `base_background`'s own index (2026-2051, DFES background starts later than `YEARS[0]`). Pass `z_seq` (already sliced/aligned to `base_background`'s own index) to correlate with `sample_demand_seq`/`sample_price_seq`'s shocks. `halflife`: None (default) reads the module-level `BACKGROUND_MR_HALFLIFE_YEARS`.

## CfD strike and PRICE_BASE_YEAR

CfD strike, £/MWh, held FLAT in real terms — model is real-terms throughout, so CPI-indexing the strike keeps it constant in real money (rebasing 39.65, £2012/MWh, to `PRICE_BASE_YEAR` once, rather than escalating it nominally every year and overstating CfD revenue). `PRICE_BASE_YEAR` must match capex/`price_series`'s price base — both UNVERIFIED; 2023 is a working assumption pending that check.

## CPI_PATH: index source and extrapolation

ONS CPI annual index (2015=100), 2012-2025, from commonly-cited ONS rates (not a live ONS query) — verify against published series D7BT/L522 before submission. Beyond 2025, extended flat at `CPI_FLAT_ASSUMPTION_RATE`.

## Stochastic link capex calibration: CAPEX_MEDIAN and CAPEX_SIGMA

`CAPEX_MEDIAN` reverts to the original provisional/unsourced 1.4x — an outright 4x median overrun (this file's previous version, median/P90 both taken directly from the SHET sample below) was judged implausible as a CENTRAL estimate even though it's what that sample's own median/P90 literally say. `CAPEX_SIGMA` keeps the SPREAD from that sample rather than reverting too — the dispersion of real cost-forecast revisions is still better evidence than the old single-point-derived sigma, even if the sample's absolute level isn't trusted as the central case.

Sample: SHET's cost-forecast revisions across its 8-project ASTI portfolio (Ofgem, "Statutory consultation on eight SHET Early Construction Funding applications...", 5 March 2026, Table 1) — SHET is the transmission owner actually building the Orkney-Caithness link. Table 1 gives, per project, the ECF request as a % of the 2022 licence cost and as a % of SHET's updated cost forecast, for the SAME £ ECF amount — so the ratio of those two percentages is that project's cost-forecast multiplier, without needing to trust anyone's summary arithmetic. Verified independently: the mean of the 8 multipliers below (3.835x, +283.5%) exactly reproduces the headline figure reported in secondary coverage of this consultation — that figure is confirmed, not merely repeated. Caveat: same-company, same-ASTI-programme evidence, not the Orkney project's own outturn, and these are SHET's current forecasts, not Ofgem-audited final costs (efficiency review is still pending at Project Assessment stage for all 8).

## Main Link cost-aware trigger cap: MAIN_LINK_COST_CAP

Main Link's cost-aware trigger (`_flexible_cost_aware`): defer a demand-justified build if the noisy early `capex_mult` estimate looks worse than the expected outcome. No independent real-world anchor — set equal to `CAPEX_MEDIAN` itself (the natural "no worse than expected" reference point) rather than the exact value a `Results.py` N=500 `cost_cap` sweep happened to maximise ENPV at (1.6, statistically indistinguishable at that N from 1.4 — see `Cost_Aware_Flexible_Strategy_Investigation.md`); picking the sweep's own noisy peak would risk overfitting the headline default to one draw sample.

## Fix A: composite growth_index observable

An alternative to `background_gen_mw` for `Decision_Rules.make_main_link_rule` (`observable="growth_index"`, default OFF — default stays `background_gen_mw`, unchanged). Blends demand's OWN growth (relative to its 2019 base level, `LEVEL_2019`) with `background_gen_mw`'s growth (relative to `MAIN_LINK_BG_GEN_THRESHOLD`, the same Ofgem-anchored figure the plain trigger uses), so both exogenous DFES drivers register instead of only generation. See `Decision_Rules.GROWTH_INDEX_THRESHOLD` for the caveat this was checked against: it does NOT diverge meaningfully earlier than `background_gen_mw` alone in the actual DFES data.

`GROWTH_INDEX_BLEND_WEIGHT`: arbitrary 50/50 split between the two terms — no independent justification for this weighting, tune directly.

## _staged: fixed-schedule staged interconnector twin

Fixed-schedule twin of the rule-based staged interconnector build (see `_flexible_staged` / `Decision_Rules.make_staged_link_strategy`): same 4 blocks, same per-stage costs (`fixed_per_stage` + learning-curve-discounted `variable_permw`), same architecture — just dropped as fixed-year Decisions instead of gated on `background_gen_mw`. `capex_mult` is the single passed-in project-wide draw, applied identically to every stage (rigid strategies don't read `state["capex_estimate"]` — that's a rule-only mechanism, see `StagedLinkRule`).

## Rigid vs flexible strategy taxonomy

Fixed/staged (rigid, `Strategies_2`) vs flexible (`Strategies_Flex`, below) is the same three-way design taxonomy — fixed, phased, flexible — [3] compares for PV capacity expansion, applied here to the interconnector instead.

## Flexible strategies

Factories, same reasoning as `Strategies_2` (fresh instances per call, no state leaks between draws).

## _flexible: Fix A knobs

Fix A knobs, all default None -> exactly today's `make_main_link_rule()` call, unchanged. See `Decision_Rules.make_main_link_rule` for what each does; `min_real_points` (paired with a wider `trend_window`) is the one that actually helped in testing — `min_decision_year` was checked and found counterproductive (see that function's own comment).

## _flexible_cost_aware: cost-aware trigger

Same demand-side trend-projected trigger as `_flexible`, plus an AND-gate on the noisy early `capex_mult` estimate (see `make_main_link_rule`'s `cost_cap` param) — defers a demand-justified Main Link build if the cost estimate looks like an overrun. `cost_cap` default (`MAIN_LINK_COST_CAP`) has no independent real-world anchor — see that constant's comment. `Results.py`'s `cost_cap` sensitivity sweep calls this directly with other values, same pattern as `_flexible_staged`'s `fixed_per_stage`/`theta` overrides.

## _flexible_cost_aware: Fix A and Fix B knobs

Fix A knobs: see `_flexible` above. Fix B knobs (`cost_cap_max_defer`, `gate_mode`, `npv_margin`): see `Decision_Rules.make_main_link_rule` / `make_npv_gate`. All default to today's exact behaviour (plain `cost_cap` screen, no forced defer, no NPV gate).

## _flexible_staged: rule-based staged interconnector

`Decision_Rules.make_staged_link_strategy`: replaces the single 220MW `NewLink` block with N stages, individually priced with a learning-curve discount on later stages' £/MW. Stage 1 builds unconditionally at a fixed year (2028); stages 2+ gate on TOTAL GENERATION (`background_gen_mw`, same exogenous DFES signal Main Link uses), genuinely reactive. `capex_mult` is unused here — each stage's realised multiplier comes from `state["capex_estimate"]` at its own build year instead (see `StagedLinkRule`). Wind gates on the shared `"StagedLinkStage"` class name, so it goes live once the FIRST stage is online. `fixed_per_stage`/`theta` are override hooks for `Results.py`'s sensitivity sweeps (neither constant has a real-world anchor).

## Flexible 1-Stage Cost-Aware: npv_proxy gate_mode pin

`gate_mode="npv_proxy"` pinned here (not as `_flexible_cost_aware`'s own default) — checked directly this session: the default plain `cost_cap` screen (`"capex_screen"`) is myopic, refusing to build even in draws where building is still strongly NPV-positive (only weighs `capex_mult` against a fixed ceiling, never the benefit side); the `npv_proxy` gate (`make_npv_gate`) compares a forward-only NPV proxy instead and recovered real ENPV in testing. Pinned via a lambda, NOT by changing `_flexible_cost_aware`'s own `gate_mode` default, because `Sensitivities.py`'s `cost_cap` sweep calls `_flexible_cost_aware(capex_mult, cost_cap=cc)` directly and relies on that function's own default staying `"capex_screen"` for `cost_cap` to mean anything — `npv_proxy` mode ignores `cost_cap` entirely (see `make_main_link_rule`), so changing the function's own default would have silently broken that sweep.

## LCOT tracking: link_cost_t and pv_link_export

LCOT (Levelised Cost of Transmission): Link-only discounted cost (capex + opex, residual-credited the same way `total_cost_t` is) and discounted energy actually exported THROUGH the link — a subset of `total_cost_t`/`pv_energy` above, tracked in parallel, not derived from them after the fact (Generation capex/opex/CFD and constraint-cost never enter `link_cost_t`; local-only delivered energy never enters `pv_link_export`). Stashed into `state` before return (see bottom of this function) rather than added to the return tuple, so every existing exact-arity `Run_Strategy(...)` unpack site stays valid.

## Run_Strategy: price_seq override

`price_seq` lets the MC loop inject a noisy (GBM) price path drawn from its own rng; None keeps the deterministic scenario lookup, unchanged for every non-MC call site.

## headroom_p90: computed only if needed

`headroom_p90` costs a full `np.percentile` (sort over 8760 hours) every year — worth skipping unless a rule actually reads it (none do currently). Snapshot from `rules` before the year loop starts mutating it: conservative (keeps computing even after the last relevant rule fires) but simple and correct.

## DFES background: existing fleet nameplate subtraction

DFES background, excluding Decision-modelled assets. Subtract the existing fleet's original nameplate PERMANENTLY (not life-gated) so it's represented once and retires once — a life-gated subtraction would let the immortal DFES base silently re-add retired capacity. `background_seq` lets the MC loop inject a noisy (GBM) path; None keeps the deterministic `BACKGROUND[scenario]` lookup.

## Fix A v3: dfes_background_gen_mw isolation

The DFES-only component of `background_gen_mw`, BEFORE the exogenous Stage1/2 wind background (below) is added. That wind addition is a FIXED, scenario-invariant schedule (same 2029/2030 MW in every strategy, every draw) that empirically dominates `background_gen_mw`'s own early trajectory — by 2030 it alone contributes ~131.5MW, more than the entire DFES pipeline across ANY of the 4 scenarios at that point (52-59MW), so it swamps the genuinely-uncertain DFES signal in exactly the years the Main Link trigger would fire. This series isolates the part that actually carries cross-scenario information.

## growth_index: per-year computation

Fix A composite observable (see `GROWTH_INDEX_*` above) — only computed if some rule actually reads it, same skip-if-unneeded pattern as `headroom_p90`. `background_gen_mw[t]` is fully finalised above this point (DFES + exogenous wind background both added), so this reads the final per-year value.

## growth_index: zero convention pre-2026

Else leave at 0 — matches `background_gen_mw`'s own structural-zero convention pre-2026 (DFES data starts 2026), so `TrendProjectedRule`'s kink-avoidance (`real = window_slice > 0`) still works correctly for this observable too.

## price_gbp_mwh: Fix B storage rationale

Fix B (`make_npv_gate`): the price the CURRENTLY-delivered mix earns, used as a proxy for what NEWLY-deliverable (currently-curtailed) energy would earn once the link removes the constraint — unconditional, already computed above, no extra cost to store.

## Run_Strategy return: stashed LCOT fields

Stashed rather than added to the return tuple, so every existing exact-arity `Run_Strategy(...)` unpack site (e.g. `Results.py`'s `_, _, _, _, _, _lead_log = Run_Strategy(...)`) stays valid unchanged.
