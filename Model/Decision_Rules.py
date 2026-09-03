# [1] Henao, Sauma, Reyes, Gonzalez (2017) Value of the option to defer a
#     transmission investment, Energy Economics 65.
# [2] Nur, MacKenzie, Min (2026) Valuation of a sequential compound option for
#     generation/transmission expansion, J. Economy and Technology 4.
# [3] Graca Gomes, Cardin, Wu (2025) Strategic real options for solar PV, IET PNZ 2025.
#
# Flexible-strategy decision rules (Cardin/Graca Gomes framework [3]): pre-specified managerial rules combined with Monte Carlo simulation, not a backward-induction binomial lattice, price the flexibility to defer/stage each investment.
# A Rule watches a trailing window of an observable from Run_Strategy's state and, once satisfied, commits capital at the year it fires ("decision year"); capacity lands `lead` years later ("build year"), forward-only, never looking ahead.

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from Model.Options import (NewLink,
                     StagedLinkStage, stage_variable_permw,
                     STAGED_LINK_STAGE_SIZES_DEFAULT, STAGED_LINK_STAGE1_YEAR_DEFAULT,
                     STAGED_LINK_FIXED_PER_STAGE, STAGED_LINK_BASE_PERMW, REBASE_2018_TO_2023)

# Stage 1 is a DELIBERATE unconditional commitment at a fixed year, a genuinely different posture from Flexible's fully-optional Main Link; stages 2+ trigger on TOTAL GENERATION (background_gen_mw), also Ofgem's own approval-condition metric.
# Each stage's threshold = MAIN_LINK_BG_GEN_THRESHOLD scaled by that stage's cumulative share of 220MW, adjusted by STAGED_LINK_THETA (1.0 = exact proportional scaling; STAGED_LINK_THETA_SWEEP tests sensitivity around that anchor).
STAGED_LINK_THETA = 1.0
STAGED_LINK_THETA_SWEEP = [0.7, 0.85, STAGED_LINK_THETA, 1.15, 1.3]
STAGED_LINK_M = 3           # consecutive years threshold must hold, stops chattering on one noisy year
STAGED_LINK_LEAD = 3        # years, decision -> build (later stages only; stage 1 uses stage1_year directly)
STAGED_LINK_DEADLINE = 2051

# 135MW = Ofgem's actual approved minimum-generation condition for the 220MW link (2019 decision letter; compromise between SHE-T's 70MW break-even and the ESO CBA's 199MW tipping point).
# A decision-rule reading of the same "option to defer a transmission investment until conditions justify it" problem [1] values with a backward-induction binomial tree.
MAIN_LINK_BG_GEN_THRESHOLD = 135           # background_gen_mw, trailing mean, "above" ([1] in Options.py, see comment above)

# Alternative observable for make_main_link_rule: blends demand's own growth with background_gen_mw's growth so both exogenous DFES drivers register, not only generation.
# CAVEAT (checked against DFES data): doesn't diverge meaningfully earlier than background_gen_mw alone -- kept as a toggle, not expected to move ENPV much on its own.
GROWTH_INDEX_THRESHOLD = 1.0   # ILLUSTRATIVE calibration point: roughly where background_gen_mw=135MW (bg term=1.0) AND demand~=its 2019 base level (demand term~=1.0) both individually cross their own "1.0" -- not independently sourced, sanity-check before trusting.

# Isolates background_gen_mw's DFES-only component; reuses MAIN_LINK_BG_GEN_THRESHOLD as a placeholder, UNCALIBRATED for this narrower signal (135MW was calibrated as a TOTAL-generation figure).
# Sanity-check before trusting exact crossing years -- the cross-scenario SPREAD this produces is what's actually being tested, not the absolute level.
DFES_BACKGROUND_THRESHOLD = MAIN_LINK_BG_GEN_THRESHOLD

MAIN_LINK_OBSERVABLES = {
    "background_gen_mw": MAIN_LINK_BG_GEN_THRESHOLD,
    "growth_index": GROWTH_INDEX_THRESHOLD,
    "dfes_background_gen_mw": DFES_BACKGROUND_THRESHOLD,
}

WINDOW = 3   # trailing years, all three rules


# Result of a Rule firing. Same read interface as Model_Components.Decision
# (Asset/BuildYear/IsBuilt), plus CapexYear() since capex and capacity land
# in different years.
class FiredDecision:
    def __init__(self, asset, decision_year, build_year):
        self._asset = asset
        self._decision_year = decision_year
        self._build_year = build_year

    def Asset(self):
        return self._asset

    def BuildYear(self):
        return self._build_year

    def CapexYear(self):
        return self._decision_year

    def IsBuilt(self, Year):
        return Year >= self._build_year


class Rule:
    def __init__(self, name, observable, window, threshold, direction,
                 asset_factory, lead, deadline, prereq=None, max_defer=None,
                 cost_cap=None, cost_cap_max_defer=None, extra_gate=None,
                 min_decision_year=None):
        assert direction in ("above", "below"), direction
        self.name = name
        self.observable = observable
        self.window = window
        self.threshold = threshold
        self.direction = direction
        self.asset_factory = asset_factory
        self.lead = lead
        self.deadline = deadline
        self.prereq = prereq
        self.max_defer = max_defer
        self.cost_cap = cost_cap   # optional AND-gate: current capex estimate must be <= this
        # Optional force-through ceiling on years blocked BY cost_cap specifically, distinct from max_defer, which only counts years the PHYSICAL condition was false.
        # None (default): a cost_cap block can defer forever if the estimate never sharpens below it.
        self.cost_cap_max_defer = cost_cap_max_defer
        # Optional callable(state, t_idx, Year, build_year) -> bool, checked
        # after cost_cap, for a richer AND-gate than a bare cost ceiling (see
        # make_npv_gate below). None (default): no extra gate.
        self.extra_gate = extra_gate
        # Earliest calendar year this rule may fire at all, regardless of window/prereq eligibility.
        # None (default): unchanged behaviour -- lets a trend fit be forced to wait until scenarios have actually started to diverge instead of committing on a still-flat window.
        self.min_decision_year = min_decision_year

        self.fired = False
        self.decision_year = None
        self.build_year = None
        self._defer_count = 0
        self._cost_defer_count = 0

    def _eligible(self, Year, t_idx, is_live_fn):
        if self.fired:
            return False
        if t_idx + 1 < self.window:            # need `window` full years of data
            return False
        if self.min_decision_year is not None and Year < self.min_decision_year:
            return False
        if self.prereq is not None and not is_live_fn(self.prereq, Year):
            return False
        return True

    # Trailing-mean vs threshold. Override for a different read of the
    # window -- e.g. TrendProjectedRule's linear-trend projection.
    def _condition_from_window(self, window_slice):
        trailing_mean = window_slice.mean()
        if self.direction == "below":
            return trailing_mean < self.threshold
        return trailing_mean > self.threshold

    # Evaluated at the end of simulation year Year (t_idx = Year - start).
    # Reads only state[observable][t_idx-window+1 : t_idx+1] -- never an
    # index beyond the current year.
    def maybe_fire(self, Year, t_idx, state, is_live_fn):
        if not self._eligible(Year, t_idx, is_live_fn):
            return None

        lo = t_idx - self.window + 1
        hi = t_idx + 1   # slice end, exclusive
        assert lo >= 0
        assert hi - 1 <= t_idx, "rule must not read state beyond the current year"
        window_slice = state[self.observable][lo:hi]
        assert len(window_slice) == self.window
        condition = self._condition_from_window(window_slice)

        if not condition and self.max_defer is not None:
            self._defer_count += 1
            if self._defer_count >= self.max_defer:
                condition = True   # deferral limit reached: force-fire

        if condition and self.cost_cap is not None:
            # AND-gate on the current (possibly noisy, sharpening over time) capex_mult estimate, read directly at this year, not trailing-averaged like the physical observables.
            # Too expensive right now means defer, not a permanent block: re-evaluated next year.
            current_estimate = state["capex_estimate"][t_idx]
            if current_estimate > self.cost_cap:
                if self.cost_cap_max_defer is not None:
                    # Unlike max_defer above (which only counts years the PHYSICAL condition was false), this counts years the physical condition WAS true but cost_cap blocked anyway.
                    # So a persistently-expensive draw still forces a build eventually instead of deferring forever.
                    self._cost_defer_count += 1
                    if self._cost_defer_count < self.cost_cap_max_defer:
                        condition = False
                    # else: deferral limit reached -- fall through and fire
                    # despite the cost estimate still being over cost_cap.
                else:
                    condition = False

        if condition and self.extra_gate is not None:
            # Fix B alternative to cost_cap: a richer AND-gate (e.g. an NPV
            # proxy, see make_npv_gate) instead of a bare cost ceiling.
            build_year_candidate = Year + self.lead
            if not self.extra_gate(state, t_idx, Year, build_year_candidate):
                condition = False

        if not condition:
            return None

        build_year = Year + self.lead
        if build_year > self.deadline:
            # Firing now would breach the deadline. Year only increases from
            # here, so build_year only gets larger -- this rule never fires.
            return None

        self.fired = True
        self.decision_year = Year
        self.build_year = build_year
        asset = self.asset_factory()
        return FiredDecision(asset, self.decision_year, self.build_year)


# MAIN_LINK_BG_GEN_THRESHOLD is almost certainly a FORECAST justification, not a real-time gate -- a plain trailing-mean trigger implements the stricter reading, checked directly to leave Main Link firing at a mean build year of 2041.8 (69% of the horizon elapsed) vs the real project's 2028 target.
# This trend-projected version instead fires when a linear-trend PROJECTION of the observable is on track to cross threshold within lookahead_years, rather than waiting for the trailing mean to have already crossed it.
TREND_WINDOW = 4               # trailing years for the trend fit -- longer than WINDOW(3), a slope estimate is noisier than a mean
TREND_LOOKAHEAD_YEARS = 3      # fire if the trend-projected crossing is within this many years
TREND_MIN_REAL_POINTS = 3      # minimum non-structural-zero points before fitting a trend at all


# A mixin, not a Rule subclass, so the SAME trend logic combines with either Rule (-> TrendProjectedRule) or StagedLinkRule (-> TrendProjectedStagedLinkRule) without duplicating it.
# First in the MRO so _condition_from_window overrides the base class's trailing-mean one.
class _TrendProjectionMixin:
    def _init_lookahead(self, lookahead_years=None, min_real_points=None):
        self.lookahead_years = TREND_LOOKAHEAD_YEARS if lookahead_years is None else lookahead_years
        # How many REAL (non-structural-zero) points must exist before the rule will even attempt a trend fit.
        # Raising this (paired with a wider window) makes the rule wait for MORE realised years before it can project a crossing -- an information-driven delay, not an artificial calendar floor like min_decision_year.
        self.min_real_points = TREND_MIN_REAL_POINTS if min_real_points is None else min_real_points

    def _condition_from_window(self, window_slice):
        years = np.arange(len(window_slice))   # 0 .. window-1, most recent = last
        now = years[-1]
        current_value = window_slice[-1]

        # A 0.0 usually means the series hasn't started yet (e.g. background_gen_mw is genuinely 0 before DFES data begins in 2026), not a real data point at the origin.
        # A window straddling that boundary would fit a straight line across a kink.
        real = window_slice > 0
        if real.sum() < self.min_real_points:
            # Not enough real data yet to fit a trend -- fall back to the
            # plain level check rather than projecting off too few points.
            if self.direction == "below":
                return current_value < self.threshold
            return current_value > self.threshold

        slope, intercept = np.polyfit(years[real], window_slice[real], 1)

        moving_toward_threshold = slope > 0 if self.direction == "above" else slope < 0
        if not moving_toward_threshold:
            # Flat/wrong-way trend -- no meaningful crossing time. Fall back
            # to "is the current level already past threshold" rather than
            # projecting nonsense.
            if self.direction == "below":
                return current_value < self.threshold
            return current_value > self.threshold

        t_cross = (self.threshold - intercept) / slope   # may be negative -- already crossed within the window
        years_until_crossing = t_cross - now
        return years_until_crossing <= self.lookahead_years


# Trend-projected Main Link trigger; only overrides _condition_from_window, everything else (eligibility, prereq/max_defer/cost_cap gating, deadline, firing) is inherited unchanged from Rule.
# A small surgical variant, contrasting StagedLinkRule, which needs a different asset_factory signature and prereq mechanism and so duplicates the whole of maybe_fire.
class TrendProjectedRule(_TrendProjectionMixin, Rule):
    def __init__(self, *args, lookahead_years=None, min_real_points=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_lookahead(lookahead_years, min_real_points)


# One stage of a rule-based staged interconnector build; subclasses Rule so Run_Strategy's isinstance sift still picks it up, but the eligibility/firing logic is a self-contained copy of Rule's, not an extension.
# Two differences from Rule: prereq is a direct reference to the PREVIOUS stage's StagedLinkRule (every stage shares one class, so a type-name string can't tell stages apart), and asset_factory is called as asset_factory(build_year, state) so it can size this stage's capex from state['capex_estimate'] at its own build year.
class StagedLinkRule(Rule):
    def __init__(self, name, window, threshold, prereq_rule, asset_factory,
                 lead, deadline, observable):
        super().__init__(name=name, observable=observable, window=window,
                          threshold=threshold, direction="above",
                          asset_factory=None, lead=lead, deadline=deadline)
        self._prereq_rule = prereq_rule
        self._stage_asset_factory = asset_factory

    def _eligible(self, Year, t_idx, is_live_fn):
        if self.fired:
            return False
        if t_idx + 1 < self.window:
            return False
        if self._prereq_rule is not None:
            if not self._prereq_rule.fired:
                return False
            # The FULL trailing window must sit after the prereq stage went live, not just the current year.
            # So "M consecutive years" only counts years this stage's own prereq was actually active.
            if Year - self.window + 1 < self._prereq_rule.build_year:
                return False
        return True

    def maybe_fire(self, Year, t_idx, state, is_live_fn):
        if not self._eligible(Year, t_idx, is_live_fn):
            return None

        lo = t_idx - self.window + 1
        hi = t_idx + 1
        assert lo >= 0
        assert hi - 1 <= t_idx, "rule must not read state beyond the current year"
        window_slice = state[self.observable][lo:hi]
        assert len(window_slice) == self.window
        if not self._condition_from_window(window_slice):
            return None

        build_year = Year + self.lead
        if build_year > self.deadline:
            return None

        self.fired = True
        self.decision_year = Year
        self.build_year = build_year
        asset = self._stage_asset_factory(build_year, state)
        return FiredDecision(asset, self.decision_year, self.build_year)


# StagedLinkRule stage using the trend-projected trigger instead of a
# trailing-mean one -- used for Stage 1 when stage1_conditional=True, on the
# same background_gen_mw signal Main Link's own TrendProjectedRule reads.
class TrendProjectedStagedLinkRule(_TrendProjectionMixin, StagedLinkRule):
    def __init__(self, *args, lookahead_years=None, min_real_points=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_lookahead(lookahead_years, min_real_points)


# Factories, not pre-built instances: each call returns a fresh Rule/asset so
# no state leaks between Monte Carlo draws or strategies.

# De-myopifies the cost-aware trigger: compares a forward-only NPV PROXY (discounted benefit of removing today's trailing congestion, projected flat to horizon_deadline) against the capex the model would actually charge at the current noisy estimate, blocking the build only if that proxy is negative.
# PROXY, not exact -- benefit/MWh = CONSTRAINT_COST + trailing price (an earlier constraint-cost-only version never fired even at 50-65% congestion); flagged assumptions include flat continuation (understates savings, since congestion trends up in every DFES scenario) and discount_rate/constraint_cost duplicated from System_Model's defaults to avoid a circular import.
NPV_GATE_DISCOUNT_RATE = 0.035
NPV_GATE_CONSTRAINT_COST = 55 * REBASE_2018_TO_2023
NPV_GATE_HORIZON_DEADLINE = 2051
NPV_GATE_TRAILING_WINDOW = 3   # years of curtail_frac/gen_total/price trailing-averaged for the "current congestion rate" estimate

def make_npv_gate(asset_capex_base, discount_rate=None, constraint_cost=None,
                   horizon_deadline=None, trailing_window=None, margin=0.0):
    r = NPV_GATE_DISCOUNT_RATE if discount_rate is None else discount_rate
    cc = NPV_GATE_CONSTRAINT_COST if constraint_cost is None else constraint_cost
    deadline = NPV_GATE_HORIZON_DEADLINE if horizon_deadline is None else horizon_deadline
    win = NPV_GATE_TRAILING_WINDOW if trailing_window is None else trailing_window

    def _gate(state, t_idx, Year, build_year):
        lo = max(0, t_idx - win + 1)
        cf = state["curtail_frac"][lo:t_idx + 1]
        gt = state["gen_total"][lo:t_idx + 1]
        px = state["price_gbp_mwh"][lo:t_idx + 1]
        benefit_per_mwh = cc + float(np.mean(px))   # avoided spill cost + revenue newly-deliverable energy would earn
        curtailed_mwh = float(np.mean(cf) * np.mean(gt))
        annual_saving = curtailed_mwh * benefit_per_mwh   # £/yr
        remaining_years = max(0, deadline - build_year)
        annuity_factor = ((1 - (1 + r) ** (-remaining_years)) / r
                           if r > 0 else float(remaining_years))
        pv_savings = annual_saving * annuity_factor
        capex_now = asset_capex_base * state["capex_estimate"][t_idx]
        return (pv_savings - capex_now) > margin

    return _gate


def make_main_link_rule(capex_mult=1.0, cost_cap=None,
                         observable=None, trend_window=None, lookahead_years=None,
                         min_decision_year=None, min_real_points=None,
                         cost_cap_max_defer=None, gate_mode="capex_screen", npv_margin=0.0):
    # Headline: fires when background_gen_mw is trend-projected to cross threshold within TREND_LOOKAHEAD_YEARS, anticipating the crossing rather than waiting for it (matching how the real 135MW condition was likely used, as a forecast justification, not a real-time gate); cost_cap=None reproduces this trigger exactly, a value adds an AND-gate on top of it.
    # Fix A knobs (trend_window; min_decision_year, checked and found COUNTERPRODUCTIVE, kept only as a toggle; min_real_points, the one actually worth using) and Fix B knobs (cost_cap_max_defer; gate_mode="capex_screen"/"npv_proxy" via make_npv_gate; npv_margin) all default to unchanged behaviour.
    if observable is None:
        observable = "background_gen_mw"
    if observable not in MAIN_LINK_OBSERVABLES:
        raise ValueError(f"unknown observable {observable!r}, expected one of {list(MAIN_LINK_OBSERVABLES)}")
    threshold = MAIN_LINK_OBSERVABLES[observable]
    window = TREND_WINDOW if trend_window is None else trend_window

    assert gate_mode in ("capex_screen", "npv_proxy"), gate_mode
    effective_cost_cap = cost_cap
    extra_gate = None
    if gate_mode == "npv_proxy":
        # Replaces the plain screen rather than stacking with it -- the
        # whole point is comparing against a benefit estimate instead of a
        # bare cost ceiling. cost_cap (if passed) is ignored in this mode.
        effective_cost_cap = None
        extra_gate = make_npv_gate(NewLink(1.0).Capex(), margin=npv_margin)

    return TrendProjectedRule(
        name="Main Link",
        observable=observable,
        window=window,
        threshold=threshold,
        direction="above",
        asset_factory=lambda: NewLink(capex_mult),
        lead=4,
        deadline=2051,
        prereq=None,
        cost_cap=effective_cost_cap,
        cost_cap_max_defer=cost_cap_max_defer,
        extra_gate=extra_gate,
        min_decision_year=min_decision_year,
        lookahead_years=lookahead_years,
        min_real_points=min_real_points,
    )


def make_main_link_rule_cost_aware(capex_mult=1.0, cost_cap=2.0,
                                    min_decision_year=None, cost_cap_max_defer=None,
                                    gate_mode="capex_screen", npv_margin=0.0):
    # Fires only if background_gen_mw exceeds threshold AND the capex_mult estimate is <= cost_cap, deferring a congestion-justified build if the cost estimate looks like an overrun (no max_defer, same reasoning as the headline).
    # This is the earlier plain trailing-mean variant, kept for its own self-test rather than the trend-projected one System_Model._flexible_cost_aware actually calls, given the same Fix A/B knobs for consistency.
    assert gate_mode in ("capex_screen", "npv_proxy"), gate_mode
    effective_cost_cap = cost_cap
    extra_gate = None
    if gate_mode == "npv_proxy":
        effective_cost_cap = None
        extra_gate = make_npv_gate(NewLink(1.0).Capex(), margin=npv_margin)
    return Rule(
        name="Main Link",
        observable="background_gen_mw",
        window=WINDOW,
        threshold=MAIN_LINK_BG_GEN_THRESHOLD,
        direction="above",
        asset_factory=lambda: NewLink(capex_mult),
        lead=4,
        deadline=2051,
        prereq=None,
        cost_cap=effective_cost_cap,
        cost_cap_max_defer=cost_cap_max_defer,
        extra_gate=extra_gate,
        min_decision_year=min_decision_year,
    )


# Rule-based staged interconnector, the phased-deployment design alternative to a single fixed-year block, evaluated against it the same way [3] compares phased against fixed PV capacity deployment; Stage 1 gates on background_gen_mw like Main Link via TrendProjectedRule (or an unconditional fixed year via stage1_conditional=False).
# Each later stage is a StagedLinkRule gated on the previous stage being live and total generation exceeding a scaled MAIN_LINK_BG_GEN_THRESHOLD for M consecutive years; stages build in strict order, returning a flat list of StagedLinkRule instances.
def make_staged_link_strategy(stage_sizes=None, stage1_year=None, stage1_conditional=True,
                               fixed_per_stage=None, base_permw=None, learning_param=None,
                               theta=None, M=None, lead=None, deadline=None):
    if stage_sizes is None:
        stage_sizes = STAGED_LINK_STAGE_SIZES_DEFAULT
    if stage1_year is None:
        stage1_year = STAGED_LINK_STAGE1_YEAR_DEFAULT
    if fixed_per_stage is None:
        fixed_per_stage = STAGED_LINK_FIXED_PER_STAGE
    if base_permw is None:
        base_permw = STAGED_LINK_BASE_PERMW
    if theta is None:
        theta = STAGED_LINK_THETA
    if M is None:
        M = STAGED_LINK_M
    if lead is None:
        lead = STAGED_LINK_LEAD
    if deadline is None:
        deadline = STAGED_LINK_DEADLINE

    total_mw = sum(stage_sizes)
    assert total_mw > 0 and all(mw > 0 for mw in stage_sizes), (
        f"stage_sizes must be a list of positive MW values, got {stage_sizes}")
    # total_mw need NOT equal NewLink's 220MW -- it's whatever this strategy's own stage_sizes sum to.
    # The threshold scaling below uses total_mw itself, not a hardcoded 220, so "each stage's cumulative share of the total" stays correct regardless of what that total is.

    rules = []
    prev_rule = None
    cum_mw_before = 0.0
    for n, mw in enumerate(stage_sizes, start=1):
        variable_permw = stage_variable_permw(n, cum_mw_before, stage_sizes,
                                               base_permw=base_permw,
                                               learning_param=learning_param)

        def _asset_factory(build_year, state, _mw=mw, _vpermw=variable_permw):
            # Realised capex multiplier for THIS stage = the noisy early
            # estimate at ITS OWN build year -- reused, not redrawn; deferred
            # stages inherit the sharpened, lower-variance estimate.
            stage_capex_mult = state["capex_estimate"][build_year - 2019]
            return StagedLinkStage(_mw, fixed_per_stage, _vpermw, stage_capex_mult)

        if n == 1:
            if stage1_conditional:
                # Default: same trend-projected trigger as Main Link (see
                # TrendProjectedRule / docstring above).
                rule = TrendProjectedStagedLinkRule(
                    name="Staged Link Stage 1",
                    window=TREND_WINDOW, threshold=MAIN_LINK_BG_GEN_THRESHOLD,
                    prereq_rule=None,
                    asset_factory=_asset_factory,
                    lead=lead,
                    deadline=deadline,
                    observable="background_gen_mw",
                )
            else:
                # Unconditional fixed-year build -- dummy always-true
                # condition on "delivered" (always >=0, always computed).
                rule = StagedLinkRule(
                    name="Staged Link Stage 1",
                    window=1, threshold=-1.0,
                    prereq_rule=None,
                    asset_factory=_asset_factory,
                    lead=stage1_year - 2019,
                    deadline=deadline,
                    observable="delivered",
                )
        else:
            # Ofgem-style total-generation threshold: MAIN_LINK_BG_GEN_THRESHOLD scaled by this stage's cumulative share of THIS STRATEGY'S OWN total_mw (not a hardcoded 220), then adjusted by theta.
            # For the default 220MW stage_sizes this is identical to the original hardcoded behaviour; for a scaled variant the last stage still reaches exactly 135*theta once 100% of its own total is built.
            cum_mw_after = cum_mw_before + mw
            bg_threshold = MAIN_LINK_BG_GEN_THRESHOLD * (cum_mw_after / total_mw) * theta
            rule = StagedLinkRule(
                name=f"Staged Link Stage {n}",
                window=M, threshold=bg_threshold,
                prereq_rule=prev_rule,
                asset_factory=_asset_factory,
                lead=lead,
                deadline=deadline,
                observable="background_gen_mw",
            )
        rules.append(rule)
        prev_rule = rule
        cum_mw_before += mw

    return rules


if __name__ == "__main__":
    # Self-contained unit tests: synthetic state, no System_Model dependency.
    # Verifies lead-time accounting (CapexYear=decision year, BuildYear=decision year+lead, charged at BuildYear to match rigid Decisions), deadline enforcement, max_defer, prereq gating, and no-lookahead.
    import numpy as np

    def make_state(n_years, **series):
        state = {k: np.zeros(n_years) for k in
                  ["curtail_frac", "headroom_p90", "background_gen_mw"]}
        state.update(series)
        return state

    START = 2019

    # 1. basic fire + lead time
    r = make_main_link_rule()
    n = 10
    state = make_state(n, background_gen_mw=np.full(n, 150.0))   # always above MAIN_LINK_BG_GEN_THRESHOLD (135)
    fired = None
    for t in range(n):
        Year = START + t
        f = r.maybe_fire(Year, t, state, is_live_fn=lambda name, yy: False)
        if f is not None:
            fired = f
            break
    assert fired is not None, "expected Main Link rule to fire"
    # assert against the rule's own window (TrendProjectedRule uses
    # TREND_WINDOW, not the plain-Rule WINDOW) so this stays correct if that changes again
    assert fired.CapexYear() == START + (r.window - 1), (
        f"expected decision year {START + r.window - 1}, got {fired.CapexYear()}")
    assert fired.BuildYear() == fired.CapexYear() + 4, "lead time not applied"
    assert fired.IsBuilt(fired.BuildYear()) is True
    assert fired.IsBuilt(fired.BuildYear() - 1) is False
    print(f"PASS: basic fire + lead time (decision {fired.CapexYear()}, build {fired.BuildYear()})")

    # 2. never fires twice
    f2 = r.maybe_fire(fired.CapexYear() + 1, WINDOW, state, is_live_fn=lambda name, yy: False)
    assert f2 is None, "rule fired a second time"
    print("PASS: rule does not re-fire once exercised")

    # 3. deadline enforcement: lead pushes build year past deadline -> never fires
    r_dead = Rule(name="deadline-test", observable="headroom_p90", window=1,
                  threshold=0.0, direction="above",
                  asset_factory=lambda: NewLink(), lead=100, deadline=2025)
    state2 = make_state(5, headroom_p90=np.full(5, 5.0))
    out = r_dead.maybe_fire(START, 0, state2, is_live_fn=lambda name, yy: False)
    assert out is None and r_dead.fired is False
    print("PASS: firing suppressed when decision_year + lead > deadline")

    # 4. max_defer forces a fire even though the threshold is never met
    r_defer = Rule(name="defer-test", observable="headroom_p90", window=1,
                   threshold=1e9, direction="above",   # never naturally true
                   asset_factory=lambda: NewLink(), lead=0, deadline=2100,
                   max_defer=3)
    state3 = make_state(10, headroom_p90=np.zeros(10))
    fired_year = None
    for t in range(10):
        f = r_defer.maybe_fire(START + t, t, state3, is_live_fn=lambda name, yy: False)
        if f is not None:
            fired_year = START + t
            break
    assert fired_year is not None, "max_defer should have forced a fire"
    print(f"PASS: max_defer forced a fire at year {fired_year}")

    # 5. prereq gating
    r_prereq = Rule(name="prereq-test", observable="headroom_p90", window=1,
                    threshold=0.0, direction="above",
                    asset_factory=lambda: NewLink(), lead=0, deadline=2100,
                    prereq="NewLink")
    state4 = make_state(5, headroom_p90=np.full(5, 5.0))
    blocked = r_prereq.maybe_fire(START, 0, state4, is_live_fn=lambda name, yy: False)
    assert blocked is None, "rule fired despite unmet prereq"
    unblocked = r_prereq.maybe_fire(START, 0, state4, is_live_fn=lambda name, yy: True)
    assert unblocked is not None, "rule failed to fire once prereq satisfied"
    print("PASS: prereq gating")

    # 6. no-lookahead: repeated calls at increasing t never raise the
    # out-of-bounds assert inside maybe_fire
    r_look = Rule(name="lookahead-test", observable="curtail_frac", window=WINDOW,
                  threshold=0.10, direction="below", asset_factory=lambda: NewLink(),
                  lead=2, deadline=2051)
    n2 = 8
    state5 = make_state(n2, curtail_frac=np.linspace(0.5, 0.01, n2))
    for t in range(n2):
        r_look.maybe_fire(START + t, t, state5, is_live_fn=lambda name, yy: True)
    print("PASS: no rule evaluation read state beyond its own year")

    # 7. cost_cap AND-gate: physical condition always true, but capex_estimate
    # starts over cost_cap and drops partway through -- must not fire until both hold.
    r_cost = make_main_link_rule_cost_aware(cost_cap=2.0)
    n3 = 6
    state6 = make_state(
        n3,
        background_gen_mw=np.full(n3, 150.0),                           # always well above threshold=135
        capex_estimate=np.array([3.0, 3.0, 3.0, 3.0, 1.5, 1.5]),         # over cap until t=4
    )
    results = []
    for t in range(n3):
        f = r_cost.maybe_fire(START + t, t, state6, is_live_fn=lambda name, yy: False)
        results.append(f is not None)
    # t=0,1 ineligible (window=3 not yet filled). t=2,3: physical condition
    # true but capex_estimate=3.0 > cost_cap=2.0 -> must not fire.
    assert results[2] is False and results[3] is False, (
        "fired despite capex estimate over cost_cap")
    assert any(results), "cost-aware rule never fired once both conditions were met"
    first_fire_t = results.index(True)
    assert first_fire_t == 4, f"expected first fire at t=4 (once estimate drops to 1.5), got t={first_fire_t}"
    assert state6["capex_estimate"][first_fire_t] <= 2.0, (
        "fired while the capex estimate was over cost_cap")
    print(f"PASS: cost_cap AND-gate (blocked while estimate > cap, fired at t={first_fire_t})")

    print("\nAll Decision_Rules.py self-tests passed.")
