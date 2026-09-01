# Decision_Rules.py — notes

Background, citations, and design rationale pulled out of `Model/Decision_Rules.py`
to keep the module itself readable. Short inline WHY comments (1-2 lines)
stay in the code; this file holds the full references and every longer
rationale block, in source order.

## References and module overview

[1] Henao, A., Sauma, E., Reyes, T., Gonzalez, A. (2017). What is the value of the option to defer an investment in Transmission Expansion Planning? An estimation using Real Options. Energy Economics 65, 194-207.

[2] Nur, G.N., MacKenzie, C.A., Min, K.J. (2026). Valuation of a sequential compound option considering electricity generation and transmission expansions. Journal of Economy and Technology 4, 57-76.

[3] Graça Gomes, J., Cardin, M.-A., Wu, B. (2025). Strategic real options and flexibility analysis for solar PV power plants. IET Powering Net Zero (PNZ 2025), Glasgow, UK.

Flexible-strategy decision rules (Stage 5, Cardin/Graça Gomes framework [3]): pre-specified managerial decision rules combined with Monte Carlo simulation, rather than a backward-induction binomial lattice, are used to price the flexibility to defer/stage each investment — the same rule-based-real-options substitution [3] makes for solar PV capacity expansion. A Rule watches a trailing window of an observable from `Run_Strategy`'s state and, once satisfied, commits capital at the year it fires ("decision year"); capacity lands `lead` years later ("build year"). Forward-only: never looks ahead. See `System_Model.Run_Strategy` for how firing feeds the accounting.

## Staged Link stage design: commitment and thresholds

Staged Link (rule-based, staged interconnector w/ learning curve): Stage 1 is a DELIBERATE unconditional commitment at a fixed year (see `make_staged_link_strategy`) — a committed baseline build, a genuinely different posture from Flexible's fully-optional Main Link.

Stages 2+ trigger on TOTAL GENERATION (`background_gen_mw`, same exogenous DFES signal Main Link uses) — switched from an earlier link-utilisation design after diagnostics showed it collapsing to a near-fixed schedule (wind's peaky profile pinned P90 export near cap within 2yr regardless of scenario noise). Total generation is also Ofgem's own approval-condition metric for this project (see `MAIN_LINK_BG_GEN_THRESHOLD` below).

Each stage's threshold = `MAIN_LINK_BG_GEN_THRESHOLD` (135MW, Ofgem's condition for the full 220MW) scaled by that stage's cumulative share of 220MW, adjusted by `STAGED_LINK_THETA` (1.0 = exact proportional scaling, no independent source beyond the scaling logic — `STAGED_LINK_THETA_SWEEP` tests sensitivity around that anchor).

## Main Link trigger: background_gen_mw threshold

`background_gen_mw` crossing threshold, trailing mean — a decision-rule reading of the same "option to defer a transmission investment until conditions justify it" real-options problem [1] values with a backward-induction binomial tree. Previously used `headroom_p90` (realised surplus), but that's circular — surplus needs wind to exist, and wind is gated on Main Link firing first.

135 MW = Ofgem's actual approved minimum-generation condition for the 220MW link (2019 decision letter; compromise between SHE-T's 70MW break-even and the ESO CBA's 199MW tipping point — [1] in `Options.py`).

## Fix A: composite growth_index observable caveat

Alternative to `background_gen_mw` for `make_main_link_rule` (`observable="growth_index"`). Blends demand's OWN growth (relative to its 2019 base level) with `background_gen_mw`'s growth (relative to `MAIN_LINK_BG_GEN_THRESHOLD`, the same Ofgem-anchored figure the plain trigger uses) so both exogenous DFES drivers register, not only generation. Computed in `System_Model.Run_Strategy` (see `GROWTH_INDEX_*` constants there) — this module only needs its threshold.

CAVEAT (checked against the actual DFES data, not assumed): this does NOT diverge meaningfully earlier than `background_gen_mw` alone — demand's own cross-scenario spread is just as muted before ~2031 (1-2% of its base level) as `background_gen_mw`'s is (2-8% of threshold) over that same window, so blending the two DILUTES the early signal rather than sharpening it. Kept as a toggle because it was asked for, not because it is expected to move ENPV much on its own — `min_decision_year` (below) is the lever that actually forces the trend fit to see post-divergence data.

## Fix A v3: dfes_background_gen_mw threshold

`"dfes_background_gen_mw"` isolates `background_gen_mw`'s DFES-only component — see `System_Model.Run_Strategy` for where it's computed and why (the exogenous Stage1/2 wind background that's also folded into plain `background_gen_mw` is a FIXED, scenario-invariant schedule that empirically dominates the combined signal's early trajectory, checked directly: by 2030 it alone contributes ~131.5MW, more than the entire DFES pipeline in ANY of the 4 scenarios at that point (52-59MW) — so a trigger reading combined `background_gen_mw` is mostly reacting to a committed wind rollout, not to DFES uncertainty, in exactly the years it would fire).

Threshold reuses `MAIN_LINK_BG_GEN_THRESHOLD` (135MW) as a placeholder — UNCALIBRATED for this narrower, wind-excluded signal (135MW was calibrated as a TOTAL-generation figure per Ofgem's condition, and this series never includes the `wind_bg` component at all) — sanity-check before trusting the exact crossing years, though the CROSS-SCENARIO SPREAD this produces is the thing actually being tested here, not the absolute threshold level.

## FiredDecision: read interface

Result of a Rule firing. Same read interface as `Model_Components.Decision` (`Asset`/`BuildYear`/`IsBuilt`), plus `CapexYear()` since capex and capacity land in different years.

## Rule.cost_cap_max_defer: Fix B force-through ceiling

Fix B (de-myopify cost-aware): optional force-through ceiling on years blocked BY `cost_cap` specifically — distinct from `max_defer`, which only counts years the PHYSICAL condition itself was false (see `maybe_fire`). None (default): unchanged behaviour — a `cost_cap` block can defer forever if the estimate never sharpens below it.

## Rule.extra_gate: Fix B alternative AND-gate

Fix B alternative: an optional `callable(state, t_idx, Year, build_year) -> bool`, checked after `cost_cap`, for a richer AND-gate than a bare cost ceiling (see `make_npv_gate` below). None (default): no extra gate, unchanged behaviour.

## Rule.min_decision_year: Fix A calendar floor

Fix A: earliest calendar year this rule may fire at all, regardless of window/prereq eligibility. None (default): unchanged behaviour. Lets a trend fit be forced to wait until scenarios have actually started to diverge instead of committing on a still-flat window.

## Rule.maybe_fire: evaluation timing

Evaluate at the end of simulation year `Year` (`t_idx = Year - start`). Reads only `state[observable][t_idx - window + 1 : t_idx + 1]` — never an index beyond the current year.

## Rule.maybe_fire: cost_cap AND-gate read

AND-gate on the current (possibly noisy, sharpening over time — see `System_Model.sample_capex_estimate_seq`) `capex_mult` estimate, read directly at this year, not trailing-averaged like the physical observables. Too expensive right now -> defer, not a permanent block: re-evaluated fresh next year.

## Rule.maybe_fire: Fix B cost_cap_max_defer logic

Fix B: unlike `max_defer` above (which only counts years the PHYSICAL condition was false), this counts years the physical condition WAS true but `cost_cap` blocked anyway — so a persistently-expensive draw still forces a build eventually instead of deferring to the deadline (or forever, if the deadline is never reached).

## Trend-projected trigger: rationale

`MAIN_LINK_BG_GEN_THRESHOLD` (135MW) is Ofgem's approval condition, almost certainly used as a FORECAST justification, not a real-time gate. A plain trailing-mean trigger implements the stricter reading; checked directly, that leaves Main Link firing at a mean build year of 2041.8 — 69% of the model horizon elapsed on average, vs the real project's 2028 target.

## _TrendProjectionMixin: design

Provides the trend-projected `_condition_from_window`: fires when a linear-trend PROJECTION of the observable is on track to cross `threshold` within `lookahead_years`, rather than waiting for the trailing mean to have already crossed it. Trend fit ONLY on already-realized years (no lookahead), least-squares over the trailing `window` years, extrapolated to find the crossing year.

A mixin, not a Rule subclass, so the SAME trend logic combines with either `Rule` (-> `TrendProjectedRule`) or `StagedLinkRule` (-> `TrendProjectedStagedLinkRule`) without duplicating it. First in the MRO so `_condition_from_window` overrides the base class's trailing-mean one.

## _init_lookahead: Fix A v2 min_real_points

Fix A (v2): how many REAL (non-structural-zero) points must exist before the rule will even attempt a trend fit — default (`TREND_MIN_REAL_POINTS=3`) lets it fit off the earliest possible data. Raising this (paired with a wider `window`) makes the rule wait for MORE realised years before it can project a crossing at all — an information-driven delay, not an artificial calendar floor (contrast `min_decision_year`, which forces a wait regardless of what's been observed and was found to just relocate the same zero-variance collapse to the new floor — see the `min_decision_year` comment on `Rule`). Since `background_gen_mw`'s DFES scenarios only start materially diverging from ~2032 (see `GROWTH_INDEX_*` in `System_Model.py` for the numbers), a large enough `min_real_points` forces the fit to actually include post-divergence years before it's willing to commit.

## _condition_from_window: excluding structural zeros

Exclude structural zeros before fitting: a 0.0 usually means the series hasn't started yet (e.g. `background_gen_mw` is genuinely 0 before DFES data begins in 2026), not a real data point at the origin — a window straddling that boundary would fit a straight line across a kink. Fits once >=`min_real_points` real points exist (growing from `min_real_points` up to the full window), enough to average out noise without necessarily forcing every draw to wait for a full window (unless `min_real_points == window`).

## _condition_from_window: flat or wrong-way trend fallback

Flat/wrong-way trend — no meaningful crossing time. Fall back to "is the current level already past threshold" (the plain Rule behaviour), rather than projecting nonsense.

## TrendProjectedRule: class design

Trend-projected Main Link trigger (see `_TrendProjectionMixin`). Only overrides `_condition_from_window` — everything else (eligibility, prereq/max_defer/cost_cap gating, deadline, firing) is inherited unchanged from `Rule`, a small surgical variant (contrast `StagedLinkRule`, which needs a different `asset_factory` signature and prereq mechanism and so duplicates the whole of `maybe_fire`).

## StagedLinkRule: class design

One stage of a rule-based staged interconnector build (see `make_staged_link_strategy`). Subclasses `Rule` so `Run_Strategy`'s isinstance sift still picks it up, but the eligibility/firing logic is a self-contained copy of `Rule`'s, not an extension.

Two differences from `Rule`: (1) prereq is a direct reference to the PREVIOUS stage's `StagedLinkRule` (every stage shares the same `StagedLinkStage` class, so a type-name string can't tell stages apart); (2) `asset_factory` is called as `asset_factory(build_year, state)`, so it can size this stage's capex from `state['capex_estimate']` at its own build year rather than a fixed `capex_mult` baked in upfront.

## StagedLinkRule._eligible: full trailing window requirement

The FULL trailing window must sit after the prereq stage went live, not just the current year — so "M consecutive years" only counts years where this stage's own prereq configuration was actually active, not years evaluated before it existed (matters most for an observable that DOES depend on installed capacity, e.g. the earlier `link_util_p90`-based design this replaced — `background_gen_mw` is purely exogenous so isn't affected either way, but the eligibility semantics should stay consistent regardless of which observable a stage reads). `window=1` rules (the gated wind rules) don't need this since there's no averaging to contaminate.

## TrendProjectedStagedLinkRule

`StagedLinkRule` stage using the trend-projected trigger instead of a trailing-mean one — used for Stage 1 when `stage1_conditional=True`, on the same `background_gen_mw` signal Main Link's own `TrendProjectedRule` reads.

## Rule factories: design

Factories, not pre-built instances: each call returns a fresh Rule/asset so no state leaks between Monte Carlo draws or strategies.

## Fix B: NPV-proxy gate design and assumptions

De-myopifies the cost-aware trigger: instead of screening on `capex_mult` alone (`cost_cap` AND-gate in `Rule.maybe_fire`), compares a forward-only NPV PROXY — discounted benefit of removing TODAY's trailing congestion, projected flat for the remaining horizon, against the capex the model would actually charge at the CURRENT noisy estimate — and only blocks the build if that proxy is negative. Forward-only: reads only state already observed up to `t_idx` (`curtail_frac`, `gen_total`, `price_gbp_mwh`, `capex_estimate`), no lookahead, same invariant as every other Rule read.

Benefit per currently-curtailed MWh = `CONSTRAINT_COST` (the spill cost avoided) PLUS the trailing market/CfD price (what that MWh earns once it's deliverable instead of spilled) — both terms are the correct marginal benefit of un-curtailing it, not double-counting: today that MWh earns £0 and costs `constraint_cost`; once deliverable it earns price and costs nothing. An EARLIER version of this gate priced `constraint_cost` only and was checked against a `capex_mult=1.9` deterministic single-scenario test — it never fired even once congestion reached 50-65%, because £30-47m/yr of constraint-cost-avoidance alone can't clear a ~£600m capex bar. Adding the revenue term was a direct fix to that finding, not a tuning choice.

ASSUMPTIONS, flagged:

1. "Flat continuation" — assumes TODAY's trailing congestion rate (`curtail_frac * gen_total`) and TODAY's trailing price hold unchanged for every remaining year to `horizon_deadline`. Congestion trends UP in every DFES scenario (background generation keeps growing against a fixed pre-link cap), so the congestion side UNDERSTATES future savings — a bias AGAINST building. Price has no such directional bias here (it's mean-reverting around the scenario backbone, not trending).
2. `discount_rate`/`constraint_cost` mirror `System_Model.RATE`'s default (0.035) and `CONSTRAINT_COST`'s central GHD-sourced value (£55/MWh, 2018->2023 rebased) as separately-defined constants here, DUPLICATED rather than imported to avoid a Decision_Rules<->System_Model circular import (`System_Model` imports this module). They will NOT track `System_Model.set_rate()` or `CONSTRAINT_COST_SWEEP` if those are changed elsewhere for a sensitivity run — re-check before comparing against a non-default-rate/cost run.
3. `asset_capex_base` is passed in by the caller (`NewLink(1.0).Capex()`) — single source of truth for the £ figure, not duplicated here.
4. Still a PROXY, not the model's actual dispatch: it treats ALL currently curtailed energy as becoming deliverable, which overstates benefit if the new link capacity wouldn't clear 100% of today's spill, and doesn't account for opex/CFD-lifetime timing. Directionally sound, not exact.

## make_main_link_rule: headline design and Fix A/B knobs

Headline: fires when `background_gen_mw` is trend-projected to cross threshold within `TREND_LOOKAHEAD_YEARS` (see `TrendProjectedRule`) — anticipates the crossing rather than waiting for it to have already happened, matching how the real 135MW condition was almost certainly actually used (a forecast justification, not a real-time gate). No `max_defer` — never firing is a valid EOA-at-2019 result, not a bug (see `make_main_link_rule_mandated` for the forced variant).

`cost_cap=None` (default) reproduces the headline demand-only trigger exactly. Passing a value adds `Rule`'s `cost_cap` AND-gate (see `maybe_fire`) on TOP OF the same trend-projected demand trigger — defers a demand-justified build if the noisy early `capex_mult` estimate looks like an overrun — so `System_Model._flexible_cost_aware` can be compared against `_flexible` on an identical demand trigger, isolating cost-awareness's own marginal effect. See `make_main_link_rule_cost_aware` below for the earlier, plain trailing-mean version of the same idea (kept for its own self-test, superseded here by pairing `cost_cap` with the trend-projected trigger).

Fix A knobs (all default None -> exactly the behaviour above):
- `observable`: `"background_gen_mw"` (default) or `"growth_index"` (see `MAIN_LINK_OBSERVABLES` / `GROWTH_INDEX_*` — CAVEAT documented there).
- `trend_window`: overrides `TREND_WINDOW` — a longer window lets the trend fit reach further back, but doesn't by itself force it to wait for post-divergence data.
- `min_decision_year`: an artificial calendar floor — checked directly and found COUNTERPRODUCTIVE for plain Flexible (collapses the build-year distribution to a single value at the floor, since the trend condition is typically ALREADY satisfied before the floor and just waits there instead of gaining information — pure delay cost, no option value). Kept as a toggle, not recommended.
- `min_real_points` (Fix A v2, the one actually worth using): how many REAL trailing years the trend fit needs before it will even attempt a crossing projection (see `_TrendProjectionMixin._init_lookahead`) — an INFORMATION-driven delay rather than a calendar one. Pair with a wider `trend_window` (`min_real_points` should be `<= trend_window`).

Fix B knobs (all default to today's plain `cost_cap` screen):
- `cost_cap_max_defer`: force-fire ceiling on years blocked BY `cost_cap` specifically (see `Rule.maybe_fire`) — None (default) unchanged.
- `gate_mode`: `"capex_screen"` (default, today's plain `cost_cap` AND-gate) or `"npv_proxy"` (`make_npv_gate`, replaces the screen entirely — `cost_cap` is ignored in that mode, `npv_margin` is the threshold instead).

## make_main_link_rule: npv_proxy replaces cost_cap screen

Replaces the plain screen rather than stacking with it — the whole point is comparing against a benefit estimate instead of a bare cost ceiling. `cost_cap` (if passed) is ignored in this mode.

## make_main_link_rule_cost_aware: design

Fires only if `background_gen_mw` exceeds threshold AND the `capex_mult` estimate (`state["capex_estimate"]`, sharpens to true value by year 5) is `<= cost_cap` — defers a congestion-justified build if the cost estimate looks like an overrun. No `max_defer`, same reasoning as the headline. Fix A/B knobs: same meaning and defaults as `make_main_link_rule`'s (this is the earlier plain trailing-mean variant — kept for its own self-test, not the one `System_Model._flexible_cost_aware` calls, but given the same knobs for consistency).

## make_stage1_wind_gated_rule: design

Builds once Main Link is live (prereq), not on a fixed year. Physical condition is a dummy (delivered always >-1) — the real gate is prereq; `window=1` minimises added delay. `lead=1`: online 1yr after the link. `prereq` is overridable (e.g. `"StagedLinkStage"` for `make_staged_link_strategy`, where the link isn't a single `NewLink`) — default unchanged for every existing caller. The prereq gate chains this generation option onto the transmission option firing first — the same sequential-compound-option dependency as [2], just with generation and transmission run in the opposite order.

## make_staged_link_strategy: design

Rule-based staged interconnector — the phased-deployment design alternative to a single fixed-year block, evaluated against it the same way [3] compares phased against fixed PV capacity deployment. Stage 1 gates on `background_gen_mw` like Main Link via `TrendProjectedRule`'s trend-projected trigger (fires when generation is projected to cross `MAIN_LINK_BG_GEN_THRESHOLD` within `TREND_LOOKAHEAD_YEARS`) — an unconditional fixed year is still available via `stage1_conditional=False`. Each later stage is a `StagedLinkRule` gated on (a) the previous stage being live and (b) total generation exceeding a threshold scaled from `MAIN_LINK_BG_GEN_THRESHOLD` by that stage's cumulative share of 220MW, for `M` consecutive years (`theta` multiplies that scaled threshold, 1.0 = exact proportional scaling). Stages build in strict order and the strategy stops once every `stage_sizes` entry has fired. Returns a flat list of `StagedLinkRule` instances — Options-list compatible, drop straight into a strategy factory's return list.

## make_staged_link_strategy: total_mw note

`total_mw` need NOT equal `NewLink`'s 220MW — it's whatever this strategy's own `stage_sizes` sum to (e.g. a scaled-up variant). The generation-threshold scaling below uses `total_mw` itself, not a hardcoded 220, so "each stage's cumulative share of the total" stays correct regardless of what that total is.

## _asset_factory: realised capex multiplier

Realised capex multiplier for THIS stage = the noisy early estimate at ITS OWN build year — reused, not redrawn (see `System_Model.sample_capex_estimate_seq`); deferred stages inherit the sharpened, lower-variance estimate.

## make_staged_link_strategy: unconditional stage 1 fallback

Default: unconditional fixed-year build — dummy always-true condition on `"delivered"` (always >=0, always computed), same pattern `make_stage1_wind_gated_rule` uses for its own non-physical gate.

## make_staged_link_strategy: Ofgem-style threshold scaling

Ofgem-style total-generation threshold: `MAIN_LINK_BG_GEN_THRESHOLD` (135MW, Ofgem's condition for the full 220MW `NewLink`) scaled by this stage's cumulative share of THIS STRATEGY'S OWN `total_mw` (not a hardcoded 220 — see the comment above the `total_mw` assert), then adjusted by `theta` (1.0 = exact proportional scaling). For the default 220MW `stage_sizes` this is identical to the original hardcoded behaviour; for a scaled variant (e.g. `total_mw=264`) the last stage still reaches exactly `135*theta` once 100% of ITS OWN total is built, rather than comparing against the unrelated 220MW reference.

## __main__: self-test overview

Self-contained unit tests: synthetic state, no `System_Model` dependency. Verifies lead-time accounting (`CapexYear`=decision year, `BuildYear`=decision year+lead, charged at `BuildYear` to match rigid Decisions), deadline enforcement, `max_defer`, prereq gating, no-lookahead.
