# [1] Henao, Sauma, Reyes, Gonzalez (2017) Value of the option to defer a
#     transmission investment, Energy Economics 65.
# [2] Nur, MacKenzie, Min (2026) Valuation of a sequential compound option for
#     generation/transmission expansion, J. Economy and Technology 4.
# [3] Graca Gomes, Cardin, Wu (2025) Strategic real options for solar PV, IET PNZ 2025.

import csv
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from Model.Options import (NewLink, REBASE_2018_TO_2023, StagedLinkStage, stage_variable_permw, STAGED_LINK_STAGE_SIZES_DEFAULT, STAGED_LINK_STAGE1_YEAR_DEFAULT, STAGED_LINK_FIXED_PER_STAGE)
from Model.Model_Components import Decision, Generation_Capacity, Link_Capacity, LIFETIMES, EXISTING_FLEET_NAMEPLATE
from Model.Decision_Rules import (Rule, make_main_link_rule, make_staged_link_strategy, MAIN_LINK_BG_GEN_THRESHOLD)
from Model.Demand import base, Demand_EE, Demand_HE, Demand_FB, Demand_HT, LEVEL_2019
from Inputs.Data_Processing.CF.PV_CF import PV_CF
from Inputs.Data_Processing.Generation.DFES_Background import BACKGROUND
from Inputs.Data_Processing.Generation.Prices import price_series as _price_series_raw
from Inputs.Data_Processing.Generation.GBM_Calibration import (DEMAND_GBM_SIGMA_ESTIMATED, PRICE_GBM_SIGMA_ESTIMATED, PRICE_GBM_SIGMA_ESTIMATED_EXCL_CRISIS, BACKGROUND_GBM_SIGMA_ESTIMATED)
from Inputs.Data_Processing.Generation.GBM_Correlation import GBM_SHOCK_CORR_ESTIMATED
from functools import lru_cache

# Gates a post-hoc PRIM-input capture block in Results.py, right after the
# headline marginalised MC loop. False: that block is skipped entirely -- no
# file written, no import of anything new, no behaviour change. Never reads
# the PRIM library itself from here or from Results.py -- that stays
# isolated in Scenario_Discovery.py, a standalone file this model never imports.
SCENARIO_DISCOVERY = True

# price_series depends only on (scenario_name, YEARS), never on capex_mult or
# strategy, so it's safe to memoise for the Monte Carlo sweep in Results.py.
@lru_cache(maxsize=None)
def _price_series_cached(scenario_name, years_tuple):
    return _price_series_raw(scenario_name, years_tuple)

def price_series(scenario_name, years):
    return _price_series_cached(scenario_name, tuple(years))

MARINE_CF = 0.30                                    # placeholder, flat

AVAIL = 0.90   # wake + availability + electrical losses; 0.85/0.95 for sensitivity
RATE = 0.035   # social discount rate; swept in Results.py

# HM Treasury Green Book's actual declining long-term discount rate schedule,
# current as of the 2026 Green Book. (year_upper_bound_inclusive, rate)
# pairs, rate applies to appraisal years 1..upper at that band; only the
# first two bands are ever reached by this model's 33-year horizon.
GREEN_BOOK_SCHEDULE = [(30, 0.035), (75, 0.030), (125, 0.025), (200, 0.020), (300, 0.015), (float("inf"), 0.010)]

DISCOUNT_MODE = "flat"   # "flat" (default, unchanged) | "green_book_declining"


# HM Treasury Green Book rate for appraisal year i (i=1 is the year
# immediately after the base year, 2019).
def _green_book_year_rate(i):
    for upper, rate in GREEN_BOOK_SCHEDULE:
        if i <= upper:
            return rate
    return GREEN_BOOK_SCHEDULE[-1][1]

def discount_factor(t):
    if DISCOUNT_MODE == "green_book_declining":
        df = 1.0
        for i in range(1, t + 1):
            df *= (1 + _green_book_year_rate(i))
        return df
    return (1 + RATE) ** t

# £/MWh, on spilled generation -- the interconnector's primary Ofgem
# needs-case benefit, the same role a congestion/deferral penalty plays in
# [1]'s TEP real-options model. £55/MWh = regulator-vetted CENTRAL, GHD
# Western Isles Transmission CBA (Aug 2018); £70 = same source's
# conservative upper; realised Scotland cost was £98/MWh in 2017/18
# (National Grid MBSS), so £55 is conservative. Rebased 2018->2023.
CONSTRAINT_COST = 55 * REBASE_2018_TO_2023

# Sweep for Results.py, single source of truth: 55=central, 70=conservative-upper, 98=realised 2017/18 anchor (MBSS).
CONSTRAINT_COST_SWEEP = [round(v * REBASE_2018_TO_2023, 2) for v in (55, 70, 98)]

# Link Capex() includes the stochastic overrun draw -- crediting residual
# value on that (True) would refund a cost overrun as salvage. Default
# False: residual computed on base capex (capex_mult=1.0). Generation assets
# unaffected -- they never take capex_mult at all.
RESIDUAL_ON_OVERRUN = False

# Bias-corrected Renewables.ninja, restricted to years with matched ANM
# demand data (2015/2018 dropped for coverage gaps). Gross CF only -- AVAIL
# applied once here, not in the dispatch loop.
WEATHER_YEARS = [2012, 2013, 2014, 2016, 2017]

# {year: gross CF array} at the given AVAIL. Factored out of the
# module-level WIND_CF_BY_YEAR computation so Results.py's AVAIL sensitivity
# can recompute the library at an alternate AVAIL and swap it in -- unlike
# CONSTRAINT_COST, WIND_CF_BY_YEAR is baked in once, not read fresh per
# year, so it has to be recomputed wholesale.
def compute_wind_cf_by_year(avail):
    out = {}
    for _yr in WEATHER_YEARS:
        _path = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                 f"Methodology_4/Coding/Inputs/Data/Generation/ninja/wind_cf_corrected_{_yr}.npy")
        _raw_cf = np.load(_path)
        if len(_raw_cf) != 8760:
            raise ValueError(f"wind_cf_corrected_{_yr}.npy has length {len(_raw_cf)}, expected 8760")
        out[_yr] = np.clip(_raw_cf * avail, 0.0, 1.0)
    return out


WIND_CF_BY_YEAR = compute_wind_cf_by_year(AVAIL)

# ANM (SSEN Active Network Management) minute demand data, per year -- same
# years as WIND_CF_BY_YEAR, so wind and demand always match a real year.
DEM_SHAPE_BY_YEAR = {}
for _yr in WEATHER_YEARS:
    _path = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
             f"Methodology_4/Coding/Inputs/Data/Demand/dem_shape/dem_shape_{_yr}.npy")
    _shape = np.load(_path)
    if len(_shape) != 8760:
        raise ValueError(f"dem_shape_{_yr}.npy has length {len(_shape)}, expected 8760")
    DEM_SHAPE_BY_YEAR[_yr] = _shape

# Default weather year: closest mean CF to the library mean -- not an
# average-of-all-years profile, which would flatten peaks and understate curtailment.
_year_means = {yr: WIND_CF_BY_YEAR[yr].mean() for yr in WEATHER_YEARS}
_library_mean = np.mean(list(_year_means.values()))
BASE_WEATHER_YEAR = min(WEATHER_YEARS, key=lambda yr: abs(_year_means[yr] - _library_mean))

def sample_wx_seq(rng, n_years):
    return rng.choice(WEATHER_YEARS, size=n_years)


# make_main_link_rule_cost_aware gates on this: capex_mult is only known
# exactly at build time in reality, so treating it as known from year 0
# would let the rule "see" information the 2019 vantage point doesn't have.
CAPEX_ESTIMATE_SIGMA0 = 0.3         # initial lognormal sigma of the early estimate
CAPEX_ESTIMATE_SHARPEN_YEARS = 5    # sigma shrinks linearly from SIGMA0 at t=0 to 0 by this many years in

def sample_capex_estimate_seq(rng, capex_mult, n_years, sigma0=None, sharpen_years=None):
    #Per-year noisy early estimate of capex_mult, one value per model year.
    if sigma0 is None:
        sigma0 = CAPEX_ESTIMATE_SIGMA0
    if sharpen_years is None:
        sharpen_years = CAPEX_ESTIMATE_SHARPEN_YEARS
    seq = np.empty(n_years)
    for t in range(n_years):
        sigma_t = max(0.0, sigma0 * (1 - t / sharpen_years))
        noise = rng.lognormal(-sigma_t ** 2 / 2, sigma_t) if sigma_t > 0 else 1.0
        seq[t] = capex_mult * noise
    return seq


# Demand.py and Prices.py are both deterministic; multiplying each by its
# own cumulative unit-mean mean-reverting multiplier (_ou_mult_seq, below)
# adds persistent, year-to-year-correlated spread while leaving the
# deterministic backbone as the exact expected path. Follows [2]'s
# multiplicative demand-uncertainty treatment and the same construction [3]
# uses for its uncertain driver -- cited for the multiplicative-anchoring
# IDEA, not mean reversion specifically (see _ou_mult_seq for why that was
# added). Sigmas calibrated in GBM_Calibration.py from measured data.
DEMAND_GBM_SIGMA = DEMAND_GBM_SIGMA_ESTIMATED   # SSEN ANM annual demand, n=5 diffs, small sample

# Crisis-inclusive (2001-2023) by default -- a Monte Carlo risk model
# arguably should see the 2021-23 gas-price shock's tail rather than assume
# it away. Swap in PRICE_GBM_SIGMA_ESTIMATED_EXCL_CRISIS (2001-2020 only,
# ~0.34 vs ~0.46) for a "normal times" volatility assumption instead.
PRICE_GBM_SIGMA = PRICE_GBM_SIGMA_ESTIMATED

# Half-lives, years, for the mean-reverting demand/price paths: how long an
# above/below-backbone deviation takes to decay halfway back toward the
# deterministic DFES/scenario path. ILLUSTRATIVE, not data-calibrated --
# nowhere near enough historical data to fit a reversion rate for any of
# these drivers. The DIFFERENCE between them is a real judgement call
# though: wholesale prices are routinely modelled as mean-reverting on a
# timescale of a few years in the energy-economics literature, reverting
# much faster than demand -- demand shocks are closer to a persistent
# random walk in standard macro treatments.
PRICE_MR_HALFLIFE_YEARS = 3.0
DEMAND_MR_HALFLIFE_YEARS = 15.0


# Mean-reverting (Ornstein-Uhlenbeck, in log-space) multiplier path, shared
# by sample_demand_seq/sample_price_seq/sample_background_seq. log_m[t]
# pulls back toward mu_target at rate theta each year instead of
# random-walking freely -- unlike a pure random walk, whose log-variance
# grows LINEARLY and unboundedly with horizon, this converges to a
# STATIONARY level. Adopted project-wide after an earlier pure-random-walk
# version produced implausible tails over 26-33yr horizons (one draw's
# terminal price reached >£8000/MWh, ~15000x its deterministic backbone).
# Uses the EXACT OU transition (not Euler), so stationary variance is hit
# exactly regardless of step size. mu_target is set so the lognormal
# stationary distribution's mean is exactly 1 (a martingale property around
# the deterministic backbone): mu_target = -sigma^2/(4*theta). z_seq: optional
# pre-drawn standard-normal shocks, one per year, to correlate this path with
# another (see sample_correlated_gbm_shocks); None draws independent shocks.
def _ou_mult_seq(rng, n_years, sigma, theta, dt=1.0, z_seq=None):
    decay = np.exp(-theta * dt)
    stationary_var = sigma ** 2 / (2 * theta) if theta > 0 else float("inf")
    mu_target = -stationary_var / 2
    step_sigma = sigma * np.sqrt((1 - decay ** 2) / (2 * theta)) if theta > 0 else sigma * np.sqrt(dt)

    seq = np.empty(n_years)
    seq[0] = 1.0
    log_m = 0.0
    for t in range(1, n_years):
        z = z_seq[t] if z_seq is not None else rng.normal()
        log_m = mu_target + (log_m - mu_target) * decay + step_sigma * z
        seq[t] = np.exp(log_m)
    return seq


# Demand, price and background-generation GBM shocks are correlated, not
# independent -- a cold winter plausibly drives higher demand AND higher gas
# prices together; independent draws a "diversification benefit" between
# them that wouldn't really exist, understating tail risk. Estimated from
# measured data (see GBM_Correlation.py) rather than the original hand-picked
# placeholder. demand-background measured -0.51 but is DELIBERATELY
# OVERRIDDEN to +0.10 (5 years judged too thin to trust the sign flip).
# Results.py's GBM_SHOCK_CORR sensitivity runs the placeholder alongside this.
GBM_SHOCK_CORR = GBM_SHOCK_CORR_ESTIMATED


# Draw correlated standard-normal shock paths for demand, price and
# background-generation GBM noise JOINTLY (via Cholesky decomposition of
# corr), instead of each sampler drawing its own independent shocks.
# Returns (n_years, 3), columns [demand, price, background], row t aligned
# to calendar year YEARS[t] -- callers must slice consistently with their
# own year range (background_gen_mw's own series is shorter, starting 2026).
def sample_correlated_gbm_shocks(rng, n_years, corr=None):
    if corr is None:
        corr = GBM_SHOCK_CORR
    L = np.linalg.cholesky(corr)
    z_indep = rng.normal(size=(n_years, 3))
    return z_indep @ L.T


# DFES demand path times a cumulative unit-mean mean-reverting multiplier --
# DFES stays the exact expected path, the multiplier only adds persistent
# spread around it. Pass z_seq to correlate with sample_price_seq/
# sample_background_seq's shocks.
def sample_demand_seq(rng, base_demand, n_years, sigma_d=None, z_seq=None, halflife=None):
    if sigma_d is None:
        sigma_d = DEMAND_GBM_SIGMA
    if halflife is None:
        halflife = DEMAND_MR_HALFLIFE_YEARS
    mult = _ou_mult_seq(rng, n_years, sigma_d, np.log(2) / halflife, z_seq=z_seq)
    return np.asarray(base_demand) * mult


# Scenario price path times a cumulative unit-mean mean-reverting multiplier
# -- same anchored construction as sample_demand_seq.
def sample_price_seq(rng, base_price, n_years, sigma_p=None, z_seq=None, halflife=None):
    if sigma_p is None:
        sigma_p = PRICE_GBM_SIGMA
    if halflife is None:
        halflife = PRICE_MR_HALFLIFE_YEARS
    mult = _ou_mult_seq(rng, n_years, sigma_p, np.log(2) / halflife, z_seq=z_seq)
    return np.asarray(base_price) * mult


# DFES background generation is a forecast pipeline with no historical
# track record, so this is calibrated instead from measured Orkney
# generation OUTPUT (ANM) as the closest available proxy. Lands at ~0.185,
# between DEMAND_GBM_SIGMA (~0.062) and PRICE_GBM_SIGMA (~0.34-0.46), same
# ordering the old unsourced 0.12 placeholder assumed.
BACKGROUND_GBM_SIGMA = BACKGROUND_GBM_SIGMA_ESTIMATED

# ILLUSTRATIVE, not data-calibrated -- only ~5 paired years of Orkney
# background-generation data exist, nowhere near enough to fit a reversion
# rate. 8 years is a rough guess at grid-connection-queue/planning-cycle
# timescales, not a fitted value.
BACKGROUND_MR_HALFLIFE_YEARS = 8.0


# DFES background generation path times a cumulative unit-mean mean-reverting
# multiplier. ONE shared multiplier per year across every tech column (a
# "DFES pipeline running ahead of/behind schedule" shock), not independent
# per-technology noise. Only spans base_background's own index (2026-2051).
def sample_background_seq(rng, base_background, sigma_bg=None, z_seq=None, halflife=None):
    if sigma_bg is None:
        sigma_bg = BACKGROUND_GBM_SIGMA
    if halflife is None:
        halflife = BACKGROUND_MR_HALFLIFE_YEARS
    n_years = len(base_background.index)
    mult = _ou_mult_seq(rng, n_years, sigma_bg, np.log(2) / halflife, z_seq=z_seq)
    return base_background.multiply(mult, axis=0)


PROFILES = {"PV": PV_CF}

TIDAL_PERIOD = 12.42                                  # hours, M2 lunar semi-diurnal
_h = np.arange(8760)
_raw = np.abs(np.sin(2 * np.pi * _h / TIDAL_PERIOD)) ** 3   # power ~ velocity^3
PROFILES["Marine"] = np.clip(_raw * (MARINE_CF / _raw.mean()), 0.0, 1.0)

YEARS = list(range(2019, 2052))          # limit of Demand.py / DFES data
END_YEAR = YEARS[-1]

# CfD strike held FLAT in real terms -- model is real-terms throughout, so
# CPI-indexing the strike keeps it constant in real money (rebasing 39.65,
# £2012/MWh, to PRICE_BASE_YEAR once, rather than escalating it nominally
# every year). PRICE_BASE_YEAR must match capex/price_series's price base --
# both UNVERIFIED; 2023 is a working assumption pending that check.
PRICE_BASE_YEAR = 2023

# ONS CPI annual index (2015=100), 2012-2025, from commonly-cited ONS rates
# (not a live ONS query) -- verify against published series D7BT/L522 before
# submission. Beyond 2025, extended flat at CPI_FLAT_ASSUMPTION_RATE.
CPI_PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
            "Methodology_4/Coding/Inputs/Data/cpi_index.csv")
CPI_FLAT_ASSUMPTION_RATE = 0.02   # assumed CPI growth beyond the CSV's last historical year

def _load_cpi_by_year():
    cpi = {}
    with open(CPI_PATH, newline="") as f:
        for row in csv.DictReader(f):
            cpi[int(row["year"])] = float(row["cpi_index"])
    last_year = max(cpi)
    for yr in YEARS:
        if yr not in cpi:
            cpi[yr] = cpi[last_year] * (1 + CPI_FLAT_ASSUMPTION_RATE) ** (yr - last_year)
    return cpi

CPI_BY_YEAR = _load_cpi_by_year()
# strike quoted in 2012 money, rebased once to PRICE_BASE_YEAR, flat thereafter
CFD_STRIKE = 39.65 * CPI_BY_YEAR[PRICE_BASE_YEAR] / CPI_BY_YEAR[2012]

# CAPEX_MEDIAN reverts to the original provisional/unsourced 1.4x -- an
# outright 4x median overrun (an earlier version, taken directly from the
# SHET sample below) was judged implausible as a CENTRAL estimate even
# though it's what that sample's own median/P90 literally say. CAPEX_SIGMA
# keeps the SPREAD from that sample: the dispersion of real cost-forecast
# revisions is still better evidence than an old single-point-derived
# sigma, even if the sample's absolute level isn't trusted as central.
#
# Sample: SHET's cost-forecast revisions across its 8-project ASTI
# portfolio (Ofgem, "Statutory consultation on eight SHET Early
# Construction Funding applications...", 5 March 2026, Table 1) -- SHET is
# the transmission owner actually building the Orkney-Caithness link.
# Table 1 gives the ECF request as a % of the 2022 licence cost and as a %
# of SHET's updated cost forecast, for the SAME £ ECF amount, so the ratio
# of those two percentages is that project's cost-forecast multiplier.
# Verified independently: the mean of the 8 multipliers below (3.835x,
# +283.5%) exactly reproduces the headline figure reported in secondary
# coverage of this consultation. Caveat: same-company, same-ASTI-programme
# evidence, not the Orkney project's own outturn, and these are SHET's
# current forecasts, not Ofgem-audited final costs.
_SHET_ASTI_COST_MULTIPLIERS = [
    30 / 7,    # BLN4:  Beauly to Loch Buidhe 400kV Reinforcement
    34 / 6,    # SLU4:  Loch Buidhe to Spittal 400kV Reinforcement
    14 / 5,    # BBNC:  Beauly to Blackhillock 400kV Double Circuit
    27 / 7,    # BPNC:  Blackhillock to Peterhead 400kV Double Circuit
    44 / 10,   # BDUP:  Beauly to Denny 275kV Circuit to 400kV
    20 / 4,    # TKUP:  East Coast Onshore 400kV Phase 2 (SHET share)
    19 / 9,    # PSDC:  Spittal to Peterhead 2GW HVDC Subsea link
    23 / 9,    # WI:    Arnish to Beauly (Western Isles) HVDC link
]
CAPEX_MEDIAN = 1.4      # median overrun multiplier -- reverted, provisional, unsourced (see comment above)
# sigma of log-multipliers, ddof=1 (small-sample estimator, same convention
# as GBM_Calibration.py's DEMAND_GBM_SIGMA/PRICE_GBM_SIGMA/BACKGROUND_GBM_SIGMA)
CAPEX_SIGMA = float(np.std(np.log(_SHET_ASTI_COST_MULTIPLIERS), ddof=1))
CAPEX_MU = np.log(CAPEX_MEDIAN)
CAPEX_P90 = float(np.exp(CAPEX_MU + 1.2816 * CAPEX_SIGMA))   # derived, not an independent anchor -- ~2.19x

# Main Link's cost-aware trigger: defer a demand-justified build if the
# noisy early capex_mult estimate looks worse than expected. No independent
# real-world anchor -- set equal to CAPEX_MEDIAN itself (the natural "no
# worse than expected" reference point) rather than a sweep's own noisy
# peak, to avoid overfitting the headline default to one draw sample.
MAIN_LINK_COST_CAP = CAPEX_MEDIAN

# Alternative to background_gen_mw for make_main_link_rule
# (observable="growth_index", default OFF). Blends demand's OWN growth
# (relative to its 2019 base level) with background_gen_mw's growth
# (relative to MAIN_LINK_BG_GEN_THRESHOLD), so both exogenous DFES drivers
# register instead of only generation -- checked against DFES data: does
# NOT diverge meaningfully earlier than background_gen_mw alone.
# GROWTH_INDEX_BLEND_WEIGHT: arbitrary 50/50 split, no independent
# justification for this weighting, tune directly.
GROWTH_INDEX_BLEND_WEIGHT = 0.5
GROWTH_INDEX_DEMAND_REF = LEVEL_2019               # demand's own 2019 base level, GWh
GROWTH_INDEX_BG_REF = MAIN_LINK_BG_GEN_THRESHOLD   # 135MW, Ofgem's condition -- reused, not reinvented


def set_rate(r): # Rebind the discount rate. Used by the sensitivity sweep in Results
    global RATE
    RATE = r

G = Generation_Capacity()
L = Link_Capacity()

def _baseline(capex_mult=1.0):
    return [Decision(NewLink(capex_mult), 2028)]

# Fixed-schedule twin of the rule-based staged interconnector build: same 4
# blocks, same per-stage costs, same architecture -- just dropped as
# fixed-year Decisions instead of gated on background_gen_mw. capex_mult is
# the single passed-in project-wide draw, applied identically to every
# stage (rigid strategies don't read state["capex_estimate"], a rule-only mechanism).
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
    # All knobs default None -> exactly today's make_main_link_rule() call,
    # unchanged. min_real_points (paired with a wider trend_window) is the
    # one that actually helped in testing -- min_decision_year was checked
    # and found counterproductive (see that function's own comment).
    return [make_main_link_rule(capex_mult, observable=observable, trend_window=trend_window,
                                 lookahead_years=lookahead_years, min_decision_year=min_decision_year,
                                 min_real_points=min_real_points)]

# Same demand-side trend-projected trigger as _flexible, plus an AND-gate on
# the noisy early capex_mult estimate -- defers a demand-justified Main Link
# build if the cost estimate looks like an overrun. Results.py's cost_cap
# sensitivity sweep calls this directly with other values, same pattern as
# _flexible_staged's fixed_per_stage/theta overrides.
def _flexible_cost_aware(capex_mult=1.0, cost_cap=MAIN_LINK_COST_CAP,
                          observable=None, trend_window=None, lookahead_years=None,
                          min_decision_year=None, min_real_points=None,
                          cost_cap_max_defer=None, gate_mode="capex_screen", npv_margin=0.0):
    # Fix A knobs: same as _flexible above. Fix B knobs (cost_cap_max_defer,
    # gate_mode, npv_margin): see make_main_link_rule/make_npv_gate. All
    # default to today's exact behaviour (plain cost_cap screen).
    return [make_main_link_rule(capex_mult, cost_cap=cost_cap, observable=observable,
                                 trend_window=trend_window, lookahead_years=lookahead_years,
                                 min_decision_year=min_decision_year, min_real_points=min_real_points,
                                 cost_cap_max_defer=cost_cap_max_defer, gate_mode=gate_mode,
                                 npv_margin=npv_margin)]

# make_staged_link_strategy: replaces the single 220MW NewLink block with N
# stages, individually priced with a learning-curve discount on later
# stages' £/MW. Stage 1 builds unconditionally at a fixed year (2028);
# stages 2+ gate on TOTAL GENERATION (background_gen_mw), genuinely
# reactive. capex_mult is unused -- each stage's realised multiplier comes
# from state["capex_estimate"] at its own build year instead. fixed_per_stage/
# theta are override hooks for Results.py's sensitivity sweeps.
def _flexible_staged(capex_mult=1.0, fixed_per_stage=None, theta=None):
    return list(make_staged_link_strategy(fixed_per_stage=fixed_per_stage, theta=theta))

Strategies_Flex = {
    "Flexible 1-Stage"             : _flexible,
    "Flexible 4-Stage"             : _flexible_staged,
    # gate_mode="npv_proxy" pinned here (not as _flexible_cost_aware's own
    # default) -- checked directly: the default plain cost_cap screen is
    # myopic, refusing to build even where building is still strongly
    # NPV-positive; npv_proxy recovered real ENPV in testing. Pinned via a
    # lambda, not by changing _flexible_cost_aware's own default, because
    # Sensitivities.py's cost_cap sweep calls _flexible_cost_aware directly
    # and relies on its default staying "capex_screen" for cost_cap to mean
    # anything (npv_proxy mode ignores cost_cap entirely).
    "Flexible 1-Stage (Cost-Aware)": lambda capex_mult=1.0: _flexible_cost_aware(capex_mult, gate_mode="npv_proxy"),
}



def Run_Strategy(Strategy,Demand,scenario_name,wx_seq=None,capex_mult=1.0,capex_estimate_seq=None,price_seq=None,background_seq=None):
    Name, Options = Strategy

    if wx_seq is None:
        wx_seq = [BASE_WEATHER_YEAR] * len(YEARS)   # one weather year, held fixed

    if capex_estimate_seq is None:
        # No noisy sequence supplied -- exact capex_mult every year (fine
        # wherever nothing reads state["capex_estimate"] anyway).
        capex_estimate_seq = np.full(len(YEARS), capex_mult)

    G.RESET()
    L.RESET()

    total_cost_t = 0   # discounted cost, £
    pv_energy = 0      # discounted delivered energy, GWh
    pv_revenue = 0     # discounted revenue, £
    total_curtail = 0  # undiscounted curtailment, GWh
    # LCOT (Levelised Cost of Transmission): Link-only discounted cost and
    # discounted energy actually exported THROUGH the link -- a subset of
    # total_cost_t/pv_energy above, tracked in parallel, not derived from
    # them after the fact.
    link_cost_t = 0       # discounted cost, £, Link-classified assets only
    pv_link_export = 0    # discounted energy exported through the link, GWh

    # price_seq lets the MC loop inject a noisy (GBM) price path drawn from
    # its own rng; None keeps the deterministic scenario lookup.
    PRICE_YR = price_series(scenario_name, YEARS) if price_seq is None else price_seq

    # Options may contain Decisions (fixed build year) and/or Rules (build
    # year set at runtime). Rigid strategies: `rules` is empty, fixed_decisions == Options.
    fixed_decisions = [d for d in Options if isinstance(d, Decision)]
    rules = [d for d in Options if isinstance(d, Rule)]
    fired_decisions = []   # FiredDecision instances, appended as rules fire
    fired_names = set()    # defensive guard: a rule must fire at most once
    rule_log = {r.name: {"fired": False, "decision_year": None, "build_year": None, "capex": None}
                for r in rules}

    # headroom_p90 costs a full np.percentile (sort over 8760 hours) every
    # year -- worth skipping unless a rule actually reads it (none do
    # currently).
    _needed_observables = {getattr(r, "observable", None) for r in rules}

    # Per-year diagnostics the rules read from (instrumentation only -- does
    # not feed back into total_cost_t / pv_revenue / total_curtail / npv).
    state = {
        "curtail_frac": np.zeros(len(YEARS)),
        "hours_at_cap": np.zeros(len(YEARS)),
        "headroom_p90": np.zeros(len(YEARS)),
        "delivered": np.zeros(len(YEARS)),
        "gen_total": np.zeros(len(YEARS)),
        "background_gen_mw": np.zeros(len(YEARS)),
        "dfes_background_gen_mw": np.zeros(len(YEARS)),  # Fix A (v3) -- background_gen_mw's DFES-only component, see comment where it's set
        "growth_index": np.zeros(len(YEARS)),   # Fix A composite observable, see GROWTH_INDEX_* above -- 0 unless a rule actually reads it
        "price_gbp_mwh": np.zeros(len(YEARS)),  # Fix B (make_npv_gate) -- see comment where it's set
        "capex_estimate": np.asarray(capex_estimate_seq),
    }

    def is_live(asset_name, yr):
        for d in fixed_decisions + fired_decisions:
            if type(d.Asset()).__name__ == asset_name and d.IsBuilt(yr):
                return True
        return False

    for Year in YEARS:

        t = Year - 2019
        df = discount_factor(t)   # discount factor for this year -- flat RATE by default, or Green Book's declining schedule (DISCOUNT_MODE)

        for d in fixed_decisions: # Sifts through each option checking if excercised

            if d.IsBuilt(Year) is True and d.BuildYear() == Year: # If built, added year checker to avoid multiple counting
                total_cost_t += d.Asset().Capex() / df# discounted capex

                if d.Asset().Classification() == 'Generation': # Then add capacity to generation if generator
                    G.Add_Asset(d.Asset(), Year)

                else:
                    L.Add_Asset(d.Asset(), Year) # Then add capacity to link if a link in MW
                    link_cost_t += d.Asset().Capex() / df   # LCOT numerator, Link-only

        for fd in fired_decisions: # Capacity from a rule that already fired
            if fd.BuildYear() == Year:
                # Charged at build year, matching fixed_decisions -- not decision
                # year, which would under-discount vs a rigid Decision (RATE>0).
                total_cost_t += fd.Asset().Capex() / df
                if fd.Asset().Classification() == 'Generation':
                    G.Add_Asset(fd.Asset(), fd.BuildYear())
                else:
                    L.Add_Asset(fd.Asset(), fd.BuildYear())
                    link_cost_t += fd.Asset().Capex() / df   # LCOT numerator, Link-only

        total_cost_t += (G.Opex(Year) + L.Opex(Year)) / df
        link_cost_t += L.Opex(Year) / df   # LCOT numerator, Link-only opex

        gen_h = np.zeros(8760)
        caps = G.Capacity_By_Type(Year)

        # Subtract the existing fleet's original nameplate PERMANENTLY (not
        # life-gated) so it's represented once and retires once -- a
        # life-gated subtraction would let the immortal DFES base silently
        # re-add retired capacity. background_seq lets the MC loop inject a
        # noisy (GBM) path; None keeps the deterministic BACKGROUND[scenario] lookup.
        bg = background_seq if background_seq is not None else BACKGROUND.get(scenario_name)
        if bg is not None and Year in bg.index:
            for tech, mw in bg.loc[Year].items():
                bg_net = max(0.0, mw - EXISTING_FLEET_NAMEPLATE.get(tech, 0.0))
                caps[tech] = caps.get(tech, 0.0) + bg_net
                state["background_gen_mw"][t] += bg_net
                # dfes_background_gen_mw and background_gen_mw are updated
                # identically here -- DFES is the only source feeding either
                # one now that the exogenous wind-buildout background was
                # removed. Kept as a separate observable (rather than
                # collapsed into background_gen_mw) since Decision_Rules.py
                # still offers it as a distinct trigger observable choice.
                state["dfes_background_gen_mw"][t] += bg_net

        # Fix A composite observable -- only computed if some rule actually
        # reads it, same skip-if-unneeded pattern as headroom_p90.
        if "growth_index" in _needed_observables:
            bg_val = state["background_gen_mw"][t]
            if bg_val > 0:
                demand_term = Demand[t] / GROWTH_INDEX_DEMAND_REF
                bg_term = bg_val / GROWTH_INDEX_BG_REF
                state["growth_index"][t] = (GROWTH_INDEX_BLEND_WEIGHT * demand_term
                                             + (1 - GROWTH_INDEX_BLEND_WEIGHT) * bg_term)
            # Else leave at 0 -- matches background_gen_mw's own
            # structural-zero convention pre-2026, so TrendProjectedRule's
            # kink-avoidance still works correctly for this observable too.

        profiles = dict(PROFILES) # local copy each year, do not mutate module-level PROFILES
        profiles["Wind"] = WIND_CF_BY_YEAR[wx_seq[t]]

        gen_by_tech = {}
        for tech, mw in caps.items():
            g = mw * profiles[tech]
            gen_by_tech[tech] = g
            gen_h += g

        wx_year = wx_seq[t]
        dem_h = Demand[t] * 1000 * DEM_SHAPE_BY_YEAR[wx_year]   # GWh -> MWh per hour
        link  = L.Current_Total_Capacity(Year)         # MW = MWh/h cap

        local   = np.minimum(gen_h, dem_h)
        surplus = np.maximum(gen_h - dem_h, 0)
        export  = np.minimum(surplus, link)

        delivered = (local.sum() + export.sum()) / 1000       # GWh
        pv_energy += delivered / df
        pv_link_export += (export.sum() / 1000) / df   # LCOT denominator -- energy THROUGH the link only, not local consumption
        spilled = (surplus - export).sum() / 1000              # GWh, disjoint from delivered
        total_curtail += spilled
        total_cost_t += spilled * 1000 * CONSTRAINT_COST / df   # constraint-relief cost, £, discounted

        cfd_mw = 0
        for d in fixed_decisions + fired_decisions: # Sifts through each option checking if it's still earning CFD
            if d.BuildYear() is not None and d.IsBuilt(Year) is True: # If built
                if d.Asset().Classification() == 'Generation': # Only generation carries a CFD
                    if Year - d.BuildYear() < d.Asset().CFD_Lifetime(): # Still within CFD lifetime
                        cfd_mw += d.Asset().Capacity()

        wind_mw, tot_e = caps.get("Wind", 0.0), gen_h.sum()

        if wind_mw > 0 and tot_e > 0: # Avoid divide-by-zero when nothing is built yet
            cfd_share = gen_by_tech["Wind"].sum() * cfd_mw / wind_mw / tot_e
        else:
            cfd_share = 0.0

        price = cfd_share * CFD_STRIKE + (1 - cfd_share) * PRICE_YR[t]
        pv_revenue += delivered * 1000 * price / df

        # per-year observables for decision rules
        # Does not feed back into total_cost_t / pv_revenue / total_curtail / npv.
        state["curtail_frac"][t] = ((surplus - export).sum() / gen_h.sum()
                                     if gen_h.sum() > 0 else 0.0)
        state["hours_at_cap"][t] = (export >= link * 0.99).sum()
        if "headroom_p90" in _needed_observables:
            state["headroom_p90"][t] = np.percentile(surplus, 90) - link
        state["delivered"][t] = delivered
        state["gen_total"][t] = gen_h.sum()
        # Fix B (make_npv_gate): the price the CURRENTLY-delivered mix
        # earns, used as a proxy for what NEWLY-deliverable (currently
        # curtailed) energy would earn once the link removes the
        # constraint -- unconditional, already computed above, no extra cost.
        state["price_gbp_mwh"][t] = price

        # rule evaluation: single forward pass, no lookahead
        for r in list(rules):
            fired = r.maybe_fire(Year, t, state, is_live)
            if fired is None:
                continue
            assert r.name not in fired_names, f"rule {r.name!r} fired twice"
            fired_names.add(r.name)
            fired_decisions.append(fired)
            rules.remove(r)
            rule_log[r.name] = {"fired": True, "decision_year": fired.CapexYear(),
                                 "build_year": fired.BuildYear(), "capex": fired.Asset().Capex()}
            if fired.BuildYear() == Year:   # lead==0: fired_decisions block above already
                # ran this year, so it missed this build -- charge it here instead.
                total_cost_t += fired.Asset().Capex() / df
                if fired.Asset().Classification() == 'Generation':
                    G.Add_Asset(fired.Asset(), Year)
                else:
                    L.Add_Asset(fired.Asset(), Year)
                    link_cost_t += fired.Asset().Capex() / df   # LCOT numerator, Link-only

    # residual value: credit unused asset life remaining at horizon
    df_end = discount_factor(END_YEAR - 2019)
    for d in fixed_decisions + fired_decisions:
        if d.BuildYear() is None:
            continue
        life = LIFETIMES[d.Asset().Classification()]
        used = END_YEAR - d.BuildYear() + 1
        remaining = max(0.0, (life - used) / life)
        residual_capex = d.Asset().Capex()
        if not RESIDUAL_ON_OVERRUN and hasattr(d.Asset(), "Capex_Mult"):
            residual_capex = residual_capex / d.Asset().Capex_Mult()   # base capex, overrun excluded
        total_cost_t -= residual_capex * remaining / df_end
        if d.Asset().Classification() == 'Link':
            link_cost_t -= residual_capex * remaining / df_end   # LCOT numerator, same residual credit

    npv = pv_revenue - total_cost_t

    # Stashed rather than added to the return tuple, so every existing
    # exact-arity Run_Strategy(...) unpack site stays valid unchanged.
    state["link_cost_total"] = link_cost_t          # discounted £, Link-only (LCOT numerator)
    state["pv_link_export_gwh"] = pv_link_export    # discounted GWh, through the link only (LCOT denominator)

    return total_cost_t, pv_energy, total_curtail, npv, state, rule_log


Scenarios = {
    "Base": base,
    "Electric Engagement": Demand_EE,
    "Hydrogen Evolution": Demand_HE,
    "Falling Behind": Demand_FB,
    "Holistic Transition": Demand_HT,
}

DFES_ONLY = [s for s in Scenarios if s != "Base"]

# DFES publishes no scenario probabilities. Equal weight is an assumption,
# stated as such; alternative weightings run as sensitivity.
SCENARIO_WEIGHTS = {
    "Equal":        {"Electric Engagement": 0.25, "Hydrogen Evolution": 0.25,
                     "Falling Behind": 0.25, "Holistic Transition": 0.25},
    "NetZero_Tilt": {"Electric Engagement": 0.20, "Hydrogen Evolution": 0.15,
                     "Falling Behind": 0.15, "Holistic Transition": 0.50},
}