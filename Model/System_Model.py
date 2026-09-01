# References [1]-[3]: see docs/notes/Model/System_Model.md#references

import csv
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from Model.Options import (NewLink, Stage1_Wind_Buildout, Stage2_Wind_Buildout, REBASE_2018_TO_2023,
                      StagedLinkStage, stage_variable_permw, STAGED_LINK_STAGE_SIZES_DEFAULT,
                      STAGED_LINK_STAGE1_YEAR_DEFAULT, STAGED_LINK_FIXED_PER_STAGE)
from Model.Model_Components import Decision, Generation_Capacity, Link_Capacity, LIFETIMES, EXISTING_FLEET_NAMEPLATE
from Model.Decision_Rules import (Rule, make_main_link_rule, make_stage1_wind_gated_rule, make_stage2_wind_gated_rule,
                             make_staged_link_strategy, MAIN_LINK_BG_GEN_THRESHOLD)
from Model.Demand import base, Demand_EE, Demand_HE, Demand_FB, Demand_HT, LEVEL_2019
from Inputs.Data_Processing.CF.PV_CF import PV_CF
from Inputs.Data_Processing.Generation.DFES_Background import BACKGROUND
from Inputs.Data_Processing.Generation.Prices import price_series as _price_series_raw
from Inputs.Data_Processing.Generation.GBM_Calibration import (DEMAND_GBM_SIGMA_ESTIMATED, PRICE_GBM_SIGMA_ESTIMATED,
                                                           PRICE_GBM_SIGMA_ESTIMATED_EXCL_CRISIS,
                                                           BACKGROUND_GBM_SIGMA_ESTIMATED)
from Inputs.Data_Processing.Generation.GBM_Correlation import GBM_SHOCK_CORR_ESTIMATED
from functools import lru_cache

# see docs/notes/Model/System_Model.md#scenario-discovery-capture-switch-scenario_discovery
SCENARIO_DISCOVERY = True

# see docs/notes/Model/System_Model.md#scope-1-switch-wind_as_option
WIND_AS_OPTION = False

# see docs/notes/Model/System_Model.md#include_wind_buildout-switch
INCLUDE_WIND_BUILDOUT = False

# see docs/notes/Model/System_Model.md#wind-background-capacity-and-build-year-source
_WIND_BG_STAGE1_MW = Stage1_Wind_Buildout().Capacity()
_WIND_BG_STAGE2_MW = Stage2_Wind_Buildout().Capacity()
_WIND_BG_STAGE1_YEAR = 2029
_WIND_BG_STAGE2_YEAR = 2030

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

# see docs/notes/Model/System_Model.md#green-book-discount-rate-schedule
GREEN_BOOK_SCHEDULE = [(30, 0.035), (75, 0.030), (125, 0.025), (200, 0.020), (300, 0.015), (float("inf"), 0.010)]

DISCOUNT_MODE = "flat"   # "flat" (default, unchanged) | "green_book_declining"


# HM Treasury Green Book rate for appraisal year i (i=1 is the year
# immediately after the base year, 2019).
def _green_book_year_rate(i):
    for upper, rate in GREEN_BOOK_SCHEDULE:
        if i <= upper:
            return rate
    return GREEN_BOOK_SCHEDULE[-1][1]


# see docs/notes/Model/System_Model.md#discount_factor-cumulative-discount-logic
def discount_factor(t):
    if DISCOUNT_MODE == "green_book_declining":
        df = 1.0
        for i in range(1, t + 1):
            df *= (1 + _green_book_year_rate(i))
        return df
    return (1 + RATE) ** t

# see docs/notes/Model/System_Model.md#constraint-relief-cost-constraint_cost
CONSTRAINT_COST = 55 * REBASE_2018_TO_2023

# Sweep for Results.py, single source of truth: 55=central, 70=conservative-upper, 98=realised 2017/18 anchor (MBSS).
CONSTRAINT_COST_SWEEP = [round(v * REBASE_2018_TO_2023, 2) for v in (55, 70, 98)]

# see docs/notes/Model/System_Model.md#residual-value-on-capex-overrun-residual_on_overrun
RESIDUAL_ON_OVERRUN = False

# see docs/notes/Model/System_Model.md#corrected-multi-year-wind-library-weather_years
WEATHER_YEARS = [2012, 2013, 2014, 2016, 2017]

# see docs/notes/Model/System_Model.md#compute_wind_cf_by_year-per-year-cf-library
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

# see docs/notes/Model/System_Model.md#weather-year-sampler-iid-vs-ar1-persistence
WX_MODE = "iid"   # "iid" | "ar1"

WIND_AR1_RHO = 0.6   # operating default for the "ar1" sampler, configurable per call

def estimate_wind_ar1_rho():
    m = np.mean(list(_year_means.values()))
    pairs = [(_year_means[yr] - m, _year_means[yr + 1] - m)
             for yr in WEATHER_YEARS if yr + 1 in _year_means]
    if not pairs:
        return 0.0
    x0, x1 = np.array(pairs).T
    denom = np.sum(x0 ** 2)
    return float(np.sum(x1 * x0) / denom) if denom > 0 else 0.0

WIND_AR1_RHO_ESTIMATED = estimate_wind_ar1_rho()


def sample_wx_seq(rng, n_years, mode=None, rho=None):
    if mode is None:
        mode = WX_MODE
    if mode == "iid":
        return rng.choice(WEATHER_YEARS, size=n_years)
    if rho is None:
        rho = WIND_AR1_RHO

    years = np.array(WEATHER_YEARS)
    means = np.array([_year_means[yr] for yr in WEATHER_YEARS])
    anomalies = means - means.mean()
    sigma = anomalies.std()
    innovation_sigma = sigma * np.sqrt(max(0.0, 1 - rho ** 2))

    x = rng.normal(0.0, sigma)   # stationary start
    wx_seq = np.empty(n_years, dtype=years.dtype)
    for t in range(n_years):
        wx_seq[t] = years[np.argmin(np.abs(anomalies - x))]
        x = rho * x + rng.normal(0.0, innovation_sigma)
    return wx_seq


# see docs/notes/Model/System_Model.md#noisy-early-capex_mult-estimate-for-the-cost-aware-rule
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


# see docs/notes/Model/System_Model.md#demand-and-price-noise-anchored-to-the-dfes-and-scenario-backbone
DEMAND_GBM_SIGMA = DEMAND_GBM_SIGMA_ESTIMATED   # SSEN ANM annual demand, n=5 diffs, small sample

# see docs/notes/Model/System_Model.md#price-gbm-sigma-crisis-inclusive-default
PRICE_GBM_SIGMA = PRICE_GBM_SIGMA_ESTIMATED

# see docs/notes/Model/System_Model.md#mean-reversion-half-lives-price_mr-and-demand_mr
PRICE_MR_HALFLIFE_YEARS = 3.0
DEMAND_MR_HALFLIFE_YEARS = 15.0


# see docs/notes/Model/System_Model.md#_ou_mult_seq-mean-reverting-multiplier-path
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


# see docs/notes/Model/System_Model.md#gbm-shock-correlation-gbm_shock_corr
GBM_SHOCK_CORR = GBM_SHOCK_CORR_ESTIMATED


# see docs/notes/Model/System_Model.md#sample_correlated_gbm_shocks
def sample_correlated_gbm_shocks(rng, n_years, corr=None):
    if corr is None:
        corr = GBM_SHOCK_CORR
    L = np.linalg.cholesky(corr)
    z_indep = rng.normal(size=(n_years, 3))
    return z_indep @ L.T


# see docs/notes/Model/System_Model.md#sample_demand_seq
def sample_demand_seq(rng, base_demand, n_years, sigma_d=None, z_seq=None, halflife=None):
    if sigma_d is None:
        sigma_d = DEMAND_GBM_SIGMA
    if halflife is None:
        halflife = DEMAND_MR_HALFLIFE_YEARS
    mult = _ou_mult_seq(rng, n_years, sigma_d, np.log(2) / halflife, z_seq=z_seq)
    return np.asarray(base_demand) * mult


# see docs/notes/Model/System_Model.md#sample_price_seq
def sample_price_seq(rng, base_price, n_years, sigma_p=None, z_seq=None, halflife=None):
    if sigma_p is None:
        sigma_p = PRICE_GBM_SIGMA
    if halflife is None:
        halflife = PRICE_MR_HALFLIFE_YEARS
    mult = _ou_mult_seq(rng, n_years, sigma_p, np.log(2) / halflife, z_seq=z_seq)
    return np.asarray(base_price) * mult


# see docs/notes/Model/System_Model.md#background_gbm_sigma-calibration
BACKGROUND_GBM_SIGMA = BACKGROUND_GBM_SIGMA_ESTIMATED

# see docs/notes/Model/System_Model.md#background_mr_halflife_years
BACKGROUND_MR_HALFLIFE_YEARS = 8.0


# see docs/notes/Model/System_Model.md#sample_background_seq
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

# see docs/notes/Model/System_Model.md#cfd-strike-and-price_base_year
PRICE_BASE_YEAR = 2023

# see docs/notes/Model/System_Model.md#cpi_path-index-source-and-extrapolation
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

# see docs/notes/Model/System_Model.md#stochastic-link-capex-calibration-capex_median-and-capex_sigma
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

# see docs/notes/Model/System_Model.md#main-link-cost-aware-trigger-cap-main_link_cost_cap
MAIN_LINK_COST_CAP = CAPEX_MEDIAN

# see docs/notes/Model/System_Model.md#fix-a-composite-growth_index-observable
GROWTH_INDEX_BLEND_WEIGHT = 0.5
GROWTH_INDEX_DEMAND_REF = LEVEL_2019               # demand's own 2019 base level, GWh
GROWTH_INDEX_BG_REF = MAIN_LINK_BG_GEN_THRESHOLD   # 135MW, Ofgem's condition -- reused, not reinvented


def set_rate(r): # Rebind the discount rate. Used by the sensitivity sweep in Results
    global RATE
    RATE = r

G = Generation_Capacity()
L = Link_Capacity()

# see docs/notes/Model/System_Model.md#strategy-factories-wind-gating-on-wind_as_option
def _baseline(capex_mult=1.0):
    decisions = [Decision(NewLink(capex_mult), 2028)]
    if WIND_AS_OPTION and INCLUDE_WIND_BUILDOUT:
        decisions += [Decision(Stage1_Wind_Buildout(), 2029),
                      Decision(Stage2_Wind_Buildout(), 2030)]
    return decisions

# see docs/notes/Model/System_Model.md#_staged-fixed-schedule-staged-interconnector-twin
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
    if WIND_AS_OPTION and INCLUDE_WIND_BUILDOUT:
        decisions.append(Decision(Stage1_Wind_Buildout(), 2029))
        decisions.append(Decision(Stage2_Wind_Buildout(), 2030))
    return decisions

Strategies_2 = {
    "Baseline"     : _baseline,
    "Fixed 4-Stage": _staged,
}

# see docs/notes/Model/System_Model.md#rigid-vs-flexible-strategy-taxonomy

# see docs/notes/Model/System_Model.md#flexible-strategies-wind-gating-stage-5
def _flexible(capex_mult=1.0, observable=None, trend_window=None, lookahead_years=None,
              min_decision_year=None, min_real_points=None):
    # see docs/notes/Model/System_Model.md#_flexible-fix-a-knobs
    opts = [make_main_link_rule(capex_mult, observable=observable, trend_window=trend_window,
                                 lookahead_years=lookahead_years, min_decision_year=min_decision_year,
                                 min_real_points=min_real_points)]
    if WIND_AS_OPTION and INCLUDE_WIND_BUILDOUT:
        opts += [make_stage1_wind_gated_rule(), make_stage2_wind_gated_rule()]
    return opts

# see docs/notes/Model/System_Model.md#_flexible_cost_aware-cost-aware-trigger
def _flexible_cost_aware(capex_mult=1.0, cost_cap=MAIN_LINK_COST_CAP,
                          observable=None, trend_window=None, lookahead_years=None,
                          min_decision_year=None, min_real_points=None,
                          cost_cap_max_defer=None, gate_mode="capex_screen", npv_margin=0.0):
    # see docs/notes/Model/System_Model.md#_flexible_cost_aware-fix-a-and-fix-b-knobs
    opts = [make_main_link_rule(capex_mult, cost_cap=cost_cap, observable=observable,
                                 trend_window=trend_window, lookahead_years=lookahead_years,
                                 min_decision_year=min_decision_year, min_real_points=min_real_points,
                                 cost_cap_max_defer=cost_cap_max_defer, gate_mode=gate_mode,
                                 npv_margin=npv_margin)]
    if WIND_AS_OPTION and INCLUDE_WIND_BUILDOUT:
        opts += [make_stage1_wind_gated_rule(), make_stage2_wind_gated_rule()]
    return opts

# see docs/notes/Model/System_Model.md#_flexible_staged-rule-based-staged-interconnector
def _flexible_staged(capex_mult=1.0, fixed_per_stage=None, theta=None):
    opts = list(make_staged_link_strategy(fixed_per_stage=fixed_per_stage, theta=theta))
    if WIND_AS_OPTION and INCLUDE_WIND_BUILDOUT:
        opts += [make_stage1_wind_gated_rule(prereq="StagedLinkStage"),
                 make_stage2_wind_gated_rule(prereq="StagedLinkStage")]
    return opts

Strategies_Flex = {
    "Flexible 1-Stage"             : _flexible,
    "Flexible 4-Stage"             : _flexible_staged,
    # see docs/notes/Model/System_Model.md#flexible-1-stage-cost-aware-npv_proxy-gate_mode-pin
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
    # see docs/notes/Model/System_Model.md#lcot-tracking-link_cost_t-and-pv_link_export
    link_cost_t = 0       # discounted cost, £, Link-classified assets only
    pv_link_export = 0    # discounted energy exported through the link, GWh

    # see docs/notes/Model/System_Model.md#run_strategy-price_seq-override
    PRICE_YR = price_series(scenario_name, YEARS) if price_seq is None else price_seq

    # Options may contain Decisions (fixed build year) and/or Rules (build
    # year set at runtime). Rigid strategies: `rules` is empty, fixed_decisions == Options.
    fixed_decisions = [d for d in Options if isinstance(d, Decision)]
    rules = [d for d in Options if isinstance(d, Rule)]
    fired_decisions = []   # FiredDecision instances, appended as rules fire
    fired_names = set()    # defensive guard: a rule must fire at most once
    rule_log = {r.name: {"fired": False, "decision_year": None, "build_year": None, "capex": None}
                for r in rules}

    # see docs/notes/Model/System_Model.md#headroom_p90-computed-only-if-needed
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

        # see docs/notes/Model/System_Model.md#dfes-background-existing-fleet-nameplate-subtraction
        bg = background_seq if background_seq is not None else BACKGROUND.get(scenario_name)
        if bg is not None and Year in bg.index:
            for tech, mw in bg.loc[Year].items():
                bg_net = max(0.0, mw - EXISTING_FLEET_NAMEPLATE.get(tech, 0.0))
                caps[tech] = caps.get(tech, 0.0) + bg_net
                state["background_gen_mw"][t] += bg_net
                # see docs/notes/Model/System_Model.md#fix-a-v3-dfes_background_gen_mw-isolation
                state["dfes_background_gen_mw"][t] += bg_net

        # see docs/notes/Model/System_Model.md#scope-1-wind-as-exogenous-background-in-run_strategy
        if not WIND_AS_OPTION and INCLUDE_WIND_BUILDOUT:
            wind_bg_mw = 0.0
            if Year >= _WIND_BG_STAGE1_YEAR:
                wind_bg_mw += _WIND_BG_STAGE1_MW
            if Year >= _WIND_BG_STAGE2_YEAR:
                wind_bg_mw += _WIND_BG_STAGE2_MW
            if wind_bg_mw > 0:
                caps["Wind"] = caps.get("Wind", 0.0) + wind_bg_mw
                state["background_gen_mw"][t] += wind_bg_mw

        # see docs/notes/Model/System_Model.md#growth_index-per-year-computation
        if "growth_index" in _needed_observables:
            bg_val = state["background_gen_mw"][t]
            if bg_val > 0:
                demand_term = Demand[t] / GROWTH_INDEX_DEMAND_REF
                bg_term = bg_val / GROWTH_INDEX_BG_REF
                state["growth_index"][t] = (GROWTH_INDEX_BLEND_WEIGHT * demand_term
                                             + (1 - GROWTH_INDEX_BLEND_WEIGHT) * bg_term)
            # see docs/notes/Model/System_Model.md#growth_index-zero-convention-pre-2026

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
        # see docs/notes/Model/System_Model.md#price_gbp_mwh-fix-b-storage-rationale
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

    # see docs/notes/Model/System_Model.md#run_strategy-return-stashed-lcot-fields
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