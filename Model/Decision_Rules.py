# References [1]-[3] and module overview: see docs/notes/Model/Decision_Rules.md#references-and-module-overview

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from Model.Options import (Stage1_Wind_Buildout, Stage2_Wind_Buildout, Extra_Link, NewLink,
                     StagedLinkStage, stage_variable_permw,
                     STAGED_LINK_STAGE_SIZES_DEFAULT, STAGED_LINK_STAGE1_YEAR_DEFAULT,
                     STAGED_LINK_FIXED_PER_STAGE, STAGED_LINK_BASE_PERMW,
                     STAGED_LINK_LEARNING_MODE_DEFAULT, REBASE_2018_TO_2023)

# ---- thresholds, exposed as module constants so they can be swept later ----
STAGE2_WIND_CURTAIL_THRESHOLD = 0.10      # curtail_frac, trailing mean, "below"
EXTRA_LINK_HOURS_THRESHOLD = 1500          # hours_at_cap, trailing mean, "above"

# see docs/notes/Model/Decision_Rules.md#staged-link-stage-design-commitment-and-thresholds
STAGED_LINK_THETA = 1.0
STAGED_LINK_THETA_SWEEP = [0.7, 0.85, STAGED_LINK_THETA, 1.15, 1.3]
STAGED_LINK_M = 3           # consecutive years threshold must hold, stops chattering on one noisy year
STAGED_LINK_LEAD = 3        # years, decision -> build (later stages only; stage 1 uses stage1_year directly)
STAGED_LINK_DEADLINE = 2051

# see docs/notes/Model/Decision_Rules.md#main-link-trigger-background_gen_mw-threshold
MAIN_LINK_BG_GEN_THRESHOLD = 135           # background_gen_mw, trailing mean, "above" ([1] in Options.py, see comment above)

# see docs/notes/Model/Decision_Rules.md#fix-a-composite-growth_index-observable-caveat
GROWTH_INDEX_THRESHOLD = 1.0   # ILLUSTRATIVE calibration point: roughly where background_gen_mw=135MW (bg term=1.0) AND demand~=its 2019 base level (demand term~=1.0) both individually cross their own "1.0" -- not independently sourced, sanity-check before trusting.

# see docs/notes/Model/Decision_Rules.md#fix-a-v3-dfes_background_gen_mw-threshold
DFES_BACKGROUND_THRESHOLD = MAIN_LINK_BG_GEN_THRESHOLD

MAIN_LINK_OBSERVABLES = {
    "background_gen_mw": MAIN_LINK_BG_GEN_THRESHOLD,
    "growth_index": GROWTH_INDEX_THRESHOLD,
    "dfes_background_gen_mw": DFES_BACKGROUND_THRESHOLD,
}

WINDOW = 3   # trailing years, all three rules


# see docs/notes/Model/Decision_Rules.md#fireddecision-read-interface
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
        # see docs/notes/Model/Decision_Rules.md#rulecost_cap_max_defer-fix-b-force-through-ceiling
        self.cost_cap_max_defer = cost_cap_max_defer
        # see docs/notes/Model/Decision_Rules.md#ruleextra_gate-fix-b-alternative-and-gate
        self.extra_gate = extra_gate
        # see docs/notes/Model/Decision_Rules.md#rulemin_decision_year-fix-a-calendar-floor
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

    # see docs/notes/Model/Decision_Rules.md#rulemaybe_fire-evaluation-timing
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
            # see docs/notes/Model/Decision_Rules.md#rulemaybe_fire-cost_cap-and-gate-read
            current_estimate = state["capex_estimate"][t_idx]
            if current_estimate > self.cost_cap:
                if self.cost_cap_max_defer is not None:
                    # see docs/notes/Model/Decision_Rules.md#rulemaybe_fire-fix-b-cost_cap_max_defer-logic
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


# see docs/notes/Model/Decision_Rules.md#trend-projected-trigger-rationale
TREND_WINDOW = 4               # trailing years for the trend fit -- longer than WINDOW(3), a slope estimate is noisier than a mean
TREND_LOOKAHEAD_YEARS = 3      # fire if the trend-projected crossing is within this many years
TREND_MIN_REAL_POINTS = 3      # minimum non-structural-zero points before fitting a trend at all


# see docs/notes/Model/Decision_Rules.md#_trendprojectionmixin-design
class _TrendProjectionMixin:
    def _init_lookahead(self, lookahead_years=None, min_real_points=None):
        self.lookahead_years = TREND_LOOKAHEAD_YEARS if lookahead_years is None else lookahead_years
        # see docs/notes/Model/Decision_Rules.md#_init_lookahead-fix-a-v2-min_real_points
        self.min_real_points = TREND_MIN_REAL_POINTS if min_real_points is None else min_real_points

    def _condition_from_window(self, window_slice):
        years = np.arange(len(window_slice))   # 0 .. window-1, most recent = last
        now = years[-1]
        current_value = window_slice[-1]

        # see docs/notes/Model/Decision_Rules.md#_condition_from_window-excluding-structural-zeros
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
            # see docs/notes/Model/Decision_Rules.md#_condition_from_window-flat-or-wrong-way-trend-fallback
            if self.direction == "below":
                return current_value < self.threshold
            return current_value > self.threshold

        t_cross = (self.threshold - intercept) / slope   # may be negative -- already crossed within the window
        years_until_crossing = t_cross - now
        return years_until_crossing <= self.lookahead_years


# see docs/notes/Model/Decision_Rules.md#trendprojectedrule-class-design
class TrendProjectedRule(_TrendProjectionMixin, Rule):
    def __init__(self, *args, lookahead_years=None, min_real_points=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_lookahead(lookahead_years, min_real_points)


# see docs/notes/Model/Decision_Rules.md#stagedlinkrule-class-design
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
            # see docs/notes/Model/Decision_Rules.md#stagedlinkrule_eligible-full-trailing-window-requirement
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


# see docs/notes/Model/Decision_Rules.md#trendprojectedstagedlinkrule
class TrendProjectedStagedLinkRule(_TrendProjectionMixin, StagedLinkRule):
    def __init__(self, *args, lookahead_years=None, min_real_points=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_lookahead(lookahead_years, min_real_points)


# see docs/notes/Model/Decision_Rules.md#rule-factories-design

def make_stage2_wind_rule():
    return Rule(
        name="Stage 2 Wind",
        observable="curtail_frac",
        window=WINDOW,
        threshold=STAGE2_WIND_CURTAIL_THRESHOLD,
        direction="below",
        asset_factory=lambda: Stage2_Wind_Buildout(),
        lead=2,
        deadline=2051,
        prereq="Stage1_Wind_Buildout",
    )


def make_extra_link_rule(capex_mult=1.0):
    return Rule(
        name="Extra Link",
        observable="hours_at_cap",
        window=WINDOW,
        threshold=EXTRA_LINK_HOURS_THRESHOLD,
        direction="above",
        asset_factory=lambda: Extra_Link(30, capex_mult),
        lead=4,
        deadline=2051,
        prereq="NewLink",
    )


# see docs/notes/Model/Decision_Rules.md#fix-b-npv-proxy-gate-design-and-assumptions
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
    # see docs/notes/Model/Decision_Rules.md#make_main_link_rule-headline-design-and-fix-ab-knobs
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
        # see docs/notes/Model/Decision_Rules.md#make_main_link_rule-npv_proxy-replaces-cost_cap-screen
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


def make_main_link_rule_mandated(capex_mult=1.0, max_defer=5):
    # Sensitivity only: force-builds by deadline regardless of signal -- a
    # build-mandate constraint, not the EOA recommendation.
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
        max_defer=max_defer,
    )


def make_main_link_rule_cost_aware(capex_mult=1.0, cost_cap=2.0,
                                    min_decision_year=None, cost_cap_max_defer=None,
                                    gate_mode="capex_screen", npv_margin=0.0):
    # see docs/notes/Model/Decision_Rules.md#make_main_link_rule_cost_aware-design
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


def make_stage1_wind_gated_rule(prereq="NewLink"):
    # see docs/notes/Model/Decision_Rules.md#make_stage1_wind_gated_rule-design
    return Rule(
        name="Stage1 Wind",
        observable="delivered",
        window=1,
        threshold=-1.0,
        direction="above",
        asset_factory=lambda: Stage1_Wind_Buildout(),
        lead=1,
        deadline=2051,
        prereq=prereq,
    )


def make_stage2_wind_gated_rule(prereq="NewLink"):
    # Same as make_stage1_wind_gated_rule, lead=2 to preserve Stage1/Stage2
    # spacing -- keyed off NewLink directly, not chained off Stage 1.
    return Rule(
        name="Stage2 Wind",
        observable="delivered",
        window=1,
        threshold=-1.0,
        direction="above",
        asset_factory=lambda: Stage2_Wind_Buildout(),
        lead=2,
        deadline=2051,
        prereq=prereq,
    )


# see docs/notes/Model/Decision_Rules.md#make_staged_link_strategy-design
def make_staged_link_strategy(stage_sizes=None, stage1_year=None, stage1_conditional=True,
                               fixed_per_stage=None, base_permw=None,
                               learning_mode=None, learning_param=None,
                               theta=None, M=None, lead=None, deadline=None):
    if stage_sizes is None:
        stage_sizes = STAGED_LINK_STAGE_SIZES_DEFAULT
    if stage1_year is None:
        stage1_year = STAGED_LINK_STAGE1_YEAR_DEFAULT
    if fixed_per_stage is None:
        fixed_per_stage = STAGED_LINK_FIXED_PER_STAGE
    if base_permw is None:
        base_permw = STAGED_LINK_BASE_PERMW
    if learning_mode is None:
        learning_mode = STAGED_LINK_LEARNING_MODE_DEFAULT
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
    # see docs/notes/Model/Decision_Rules.md#make_staged_link_strategy-total_mw-note

    rules = []
    prev_rule = None
    cum_mw_before = 0.0
    for n, mw in enumerate(stage_sizes, start=1):
        variable_permw = stage_variable_permw(n, cum_mw_before, stage_sizes,
                                               base_permw=base_permw,
                                               mode=learning_mode,
                                               learning_param=learning_param)

        def _asset_factory(build_year, state, _mw=mw, _vpermw=variable_permw):
            # see docs/notes/Model/Decision_Rules.md#_asset_factory-realised-capex-multiplier
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
                # see docs/notes/Model/Decision_Rules.md#make_staged_link_strategy-unconditional-stage-1-fallback
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
            # see docs/notes/Model/Decision_Rules.md#make_staged_link_strategy-ofgem-style-threshold-scaling
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
    # see docs/notes/Model/Decision_Rules.md#__main__-self-test-overview
    import numpy as np

    def make_state(n_years, **series):
        state = {k: np.zeros(n_years) for k in
                  ["curtail_frac", "hours_at_cap", "headroom_p90", "background_gen_mw"]}
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
    r_look = make_stage2_wind_rule()
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
