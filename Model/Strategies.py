# The candidate interconnector strategies: rigid (Strategies_2, fixed-year Decisions) and flexible (Strategies_Flex, Rule-gated).
# Split out of System_Model.py, which owns the simulation engine (Run_Strategy) that scores whichever strategy is passed to it; nothing here runs a simulation, these are just Options-list factories.
#
# [3] Graca Gomes, Cardin, Wu (2025) Strategic real options for solar PV, IET PNZ 2025.

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Model.Options import (NewLink, StagedLinkStage, stage_variable_permw,
                            STAGED_LINK_STAGE_SIZES_DEFAULT, STAGED_LINK_STAGE1_YEAR_DEFAULT,
                            STAGED_LINK_FIXED_PER_STAGE)
from Model.Model_Components import Decision
from Model.Decision_Rules import make_main_link_rule, make_staged_link_strategy
from Model.Uncertainty import MAIN_LINK_COST_CAP


def _baseline(capex_mult=1.0):
    return [Decision(NewLink(capex_mult), 2028)]

# Fixed-schedule twin of the rule-based staged interconnector build: same 4 blocks, same per-stage costs, same architecture, just dropped as fixed-year Decisions instead of gated on background_gen_mw.
# capex_mult is the single passed-in project-wide draw, applied identically to every stage (rigid strategies don't read state["capex_estimate"], a rule-only mechanism).
def _staged(capex_mult=1.0):
    stage_sizes = STAGED_LINK_STAGE_SIZES_DEFAULT
    decisions = []
    cum_mw_before = 0.0
    for n, mw in enumerate(stage_sizes, start=1):
        variable_permw = stage_variable_permw(n, cum_mw_before, stage_sizes)
        year = STAGED_LINK_STAGE1_YEAR_DEFAULT + 2 * (n - 1)
        asset = StagedLinkStage(mw, STAGED_LINK_FIXED_PER_STAGE, variable_permw, capex_mult)
        decisions.append(Decision(asset, year))
        cum_mw_before += mw
    return decisions

Strategies_2 = {
    "Baseline"     : _baseline,
    "Fixed 4-Stage": _staged,
}

# Fixed/staged (rigid, Strategies_2) vs flexible (Strategies_Flex, below) is
# the same three-way design taxonomy -- fixed, phased, flexible -- [3]
# compares for PV capacity expansion, applied here to the interconnector.

def _flexible(capex_mult=1.0, observable=None, trend_window=None, lookahead_years=None,
              min_decision_year=None, min_real_points=None):
    # All knobs default None -> exactly today's make_main_link_rule() call, unchanged.
    # min_real_points (paired with a wider trend_window) is the one that actually helped in testing; min_decision_year was checked and found counterproductive (see that function's own comment).
    return [make_main_link_rule(capex_mult, observable=observable, trend_window=trend_window,
                                 lookahead_years=lookahead_years, min_decision_year=min_decision_year,
                                 min_real_points=min_real_points)]

# Same demand-side trend-projected trigger as _flexible, plus an AND-gate on the noisy early capex_mult estimate -- defers a demand-justified Main Link build if the cost estimate looks like an overrun.
# Results.py's cost_cap sensitivity sweep calls this directly with other values, same pattern as _flexible_staged's fixed_per_stage/theta overrides.
def _flexible_cost_aware(capex_mult=1.0, cost_cap=MAIN_LINK_COST_CAP,
                          observable=None, trend_window=None, lookahead_years=None,
                          min_decision_year=None, min_real_points=None,
                          cost_cap_max_defer=None, gate_mode="capex_screen", npv_margin=0.0):
    # Fix A knobs: same as _flexible above.
    # Fix B knobs (cost_cap_max_defer, gate_mode, npv_margin): see make_main_link_rule/make_npv_gate; all default to today's exact behaviour (plain cost_cap screen).
    return [make_main_link_rule(capex_mult, cost_cap=cost_cap, observable=observable,
                                 trend_window=trend_window, lookahead_years=lookahead_years,
                                 min_decision_year=min_decision_year, min_real_points=min_real_points,
                                 cost_cap_max_defer=cost_cap_max_defer, gate_mode=gate_mode,
                                 npv_margin=npv_margin)]

# make_staged_link_strategy replaces the single 220MW NewLink block with N stages, individually priced with a learning-curve discount on later stages' £/MW; stage 1 builds unconditionally at a fixed year (2028), stages 2+ gate on total generation (background_gen_mw), genuinely reactive.
# capex_mult is unused -- each stage's realised multiplier comes from state["capex_estimate"] at its own build year instead; fixed_per_stage/theta are override hooks for Results.py's sensitivity sweeps.
def _flexible_staged(capex_mult=1.0, fixed_per_stage=None, theta=None):
    return list(make_staged_link_strategy(fixed_per_stage=fixed_per_stage, theta=theta))

Strategies_Flex = {
    "Flexible 1-Stage"             : _flexible,
    "Flexible 4-Stage"             : _flexible_staged,
    # gate_mode="npv_proxy" pinned here (not as _flexible_cost_aware's own default) -- checked directly: the default plain cost_cap screen is myopic, refusing to build even where still strongly NPV-positive, while npv_proxy recovered real ENPV in testing.
    # Pinned via a lambda rather than changing _flexible_cost_aware's own default, because Sensitivities.py's cost_cap sweep calls _flexible_cost_aware directly and relies on its default staying "capex_screen" (npv_proxy mode ignores cost_cap entirely).
    "Flexible 1-Stage (Cost-Aware)": lambda capex_mult=1.0: _flexible_cost_aware(capex_mult, gate_mode="npv_proxy"),
}
