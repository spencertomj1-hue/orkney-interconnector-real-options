# Stochastic drivers: how the model's uncertain per-draw inputs are calibrated and sampled -- weather, GBM demand/price/background paths, capex cost-overrun, and the noisy early estimate of it a cost-aware rule sees.
# Split out of System_Model.py, which owns the simulation engine (Run_Strategy) that consumes these; nothing here reads or mutates Run_Strategy's own state.
#
# [2] Nur, MacKenzie, Min (2026) Valuation of a sequential compound option for
#     generation/transmission expansion, J. Economy and Technology 4.
# [3] Graca Gomes, Cardin, Wu (2025) Strategic real options for solar PV, IET PNZ 2025.

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from Inputs.Data_Processing.Generation.GBM_Calibration import (DEMAND_GBM_SIGMA_ESTIMATED, PRICE_GBM_SIGMA_ESTIMATED, PRICE_GBM_SIGMA_ESTIMATED_EXCL_CRISIS, BACKGROUND_GBM_SIGMA_ESTIMATED)
from Inputs.Data_Processing.Generation.GBM_Correlation import GBM_SHOCK_CORR_ESTIMATED


# Weather: which historical year's hourly wind-CF / demand-shape library a simulated year draws.

AVAIL = 0.90   # wake + availability + electrical losses; 0.85/0.95 for sensitivity

# Bias-corrected Renewables.ninja, restricted to years with matched ANM demand data (2015/2018 dropped for coverage gaps).
# Gross CF only -- AVAIL applied once here, not in the dispatch loop.
WEATHER_YEARS = [2012, 2013, 2014, 2016, 2017]

# {year: gross CF array} at the given AVAIL, factored out of WIND_CF_BY_YEAR so Results.py's AVAIL sensitivity can recompute the library and swap it in.
# Unlike CONSTRAINT_COST, WIND_CF_BY_YEAR is baked in once rather than read fresh per year, so it must be recomputed wholesale.
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

# ANM (SSEN Active Network Management) minute demand data, per year -- same years as WIND_CF_BY_YEAR, so wind and demand always match a real year.
DEM_SHAPE_BY_YEAR = {}
for _yr in WEATHER_YEARS:
    _path = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
             f"Methodology_4/Coding/Inputs/Data/Demand/dem_shape/dem_shape_{_yr}.npy")
    _shape = np.load(_path)
    if len(_shape) != 8760:
        raise ValueError(f"dem_shape_{_yr}.npy has length {len(_shape)}, expected 8760")
    DEM_SHAPE_BY_YEAR[_yr] = _shape

# Default weather year: closest mean CF to the library mean -- not an average-of-all-years profile, which would flatten peaks and understate curtailment.
_year_means = {yr: WIND_CF_BY_YEAR[yr].mean() for yr in WEATHER_YEARS}
_library_mean = np.mean(list(_year_means.values()))
BASE_WEATHER_YEAR = min(WEATHER_YEARS, key=lambda yr: abs(_year_means[yr] - _library_mean))

def sample_wx_seq(rng, n_years):
    return rng.choice(WEATHER_YEARS, size=n_years)


# Link capex cost-overrun distribution, and the noisy early estimate of it a cost-aware rule reads (only known exactly at build time in reality).

# make_main_link_rule_cost_aware gates on this: capex_mult is only known exactly at build time in reality.
# Treating it as known from year 0 would let the rule "see" information the 2019 vantage point doesn't have.
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


# CAPEX_MEDIAN reverts to the original provisional, unsourced 1.4x rather than the SHET sample's own implied 4x median; CAPEX_SIGMA still keeps that sample's spread as the best available evidence on cost-forecast-revision dispersion.
# Sample: SHET's cost-forecast revisions across its 8-project ASTI portfolio (Ofgem, 5 March 2026 consultation, Table 1) -- same-company, same-programme evidence, not the Orkney project's own outturn.
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

# Main Link's cost-aware trigger defers a demand-justified build if the noisy early capex_mult estimate looks worse than expected; no independent anchor, so it's set equal to CAPEX_MEDIAN itself rather than a sweep's own noisy peak, to avoid overfitting.
# Lives here (not System_Model.py) so Strategies.py can read it without a System_Model <-> Strategies import cycle.
MAIN_LINK_COST_CAP = CAPEX_MEDIAN


# Demand / price / background-generation GBM-style paths.

# Demand.py and Prices.py are deterministic; multiplying each by its own cumulative unit-mean mean-reverting multiplier (_ou_mult_seq, below) adds persistent, correlated spread while keeping the deterministic backbone as the exact expected path.
# Follows [2]/[3]'s multiplicative demand-uncertainty treatment (cited for that idea, not mean reversion specifically); sigmas calibrated in GBM_Calibration.py from measured data.
DEMAND_GBM_SIGMA = DEMAND_GBM_SIGMA_ESTIMATED   # SSEN ANM annual demand, n=5 diffs, small sample

# Crisis-inclusive (2001-2023) by default -- a Monte Carlo risk model should arguably see the 2021-23 gas-price shock's tail rather than assume it away.
# Swap in PRICE_GBM_SIGMA_ESTIMATED_EXCL_CRISIS (2001-2020 only, ~0.34 vs ~0.46) for a "normal times" volatility assumption instead.
PRICE_GBM_SIGMA = PRICE_GBM_SIGMA_ESTIMATED

# Half-lives (years) for the mean-reverting demand/price paths -- how long a deviation takes to decay halfway back to the deterministic path; illustrative, not data-calibrated, since nowhere near enough history exists to fit a reversion rate.
# The DIFFERENCE between them is a real judgement call: prices are routinely modelled as mean-reverting on a few-year timescale, reverting much faster than demand, which behaves closer to a persistent random walk.
PRICE_MR_HALFLIFE_YEARS = 3.0
DEMAND_MR_HALFLIFE_YEARS = 15.0


# Mean-reverting (Ornstein-Uhlenbeck, log-space) multiplier path shared by sample_demand_seq/sample_price_seq/sample_background_seq, adopted project-wide after an earlier pure-random-walk version produced implausible tails (one draw's terminal price reached >£8000/MWh).
# Uses the exact OU transition (not Euler) so stationary variance is hit exactly, with mu_target set so the lognormal stationary mean is exactly 1; z_seq is an optional pre-drawn shock path to correlate with another sampler (see sample_correlated_gbm_shocks).
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


# Demand/price/background GBM shocks are correlated, not independent (a cold winter plausibly drives both higher demand and higher gas prices); independent draws would imply a "diversification benefit" that doesn't really exist, understating tail risk.
# Estimated from measured data (GBM_Correlation.py) rather than hand-picked; demand-background measured -0.51 is deliberately overridden to +0.10 (5 years too thin to trust the sign flip) -- Results.py's sensitivity runs the placeholder alongside this.
GBM_SHOCK_CORR = GBM_SHOCK_CORR_ESTIMATED


# Draws correlated standard-normal shock paths for demand/price/background GBM noise JOINTLY (via Cholesky decomposition of corr), instead of each sampler drawing independent shocks.
# Returns (n_years, 3), columns [demand, price, background], row t aligned to YEARS[t] -- callers must slice consistently (background_gen_mw's own series is shorter, starting 2026).
def sample_correlated_gbm_shocks(rng, n_years, corr=None):
    if corr is None:
        corr = GBM_SHOCK_CORR
    L = np.linalg.cholesky(corr)
    z_indep = rng.normal(size=(n_years, 3))
    return z_indep @ L.T


# DFES demand path times a cumulative unit-mean mean-reverting multiplier -- DFES stays the exact expected path, the multiplier only adds persistent spread around it.
# Pass z_seq to correlate with sample_price_seq/sample_background_seq's shocks.
def sample_demand_seq(rng, base_demand, n_years, sigma_d=None, z_seq=None, halflife=None):
    if sigma_d is None:
        sigma_d = DEMAND_GBM_SIGMA
    if halflife is None:
        halflife = DEMAND_MR_HALFLIFE_YEARS
    mult = _ou_mult_seq(rng, n_years, sigma_d, np.log(2) / halflife, z_seq=z_seq)
    return np.asarray(base_demand) * mult


# Scenario price path times a cumulative unit-mean mean-reverting multiplier -- same anchored construction as sample_demand_seq.
def sample_price_seq(rng, base_price, n_years, sigma_p=None, z_seq=None, halflife=None):
    if sigma_p is None:
        sigma_p = PRICE_GBM_SIGMA
    if halflife is None:
        halflife = PRICE_MR_HALFLIFE_YEARS
    mult = _ou_mult_seq(rng, n_years, sigma_p, np.log(2) / halflife, z_seq=z_seq)
    return np.asarray(base_price) * mult


# DFES background generation has no historical track record, so this is calibrated instead from measured Orkney generation output (ANM) as the closest available proxy.
# Lands at ~0.185, between DEMAND_GBM_SIGMA (~0.062) and PRICE_GBM_SIGMA (~0.34-0.46) -- the same ordering the old unsourced 0.12 placeholder assumed.
BACKGROUND_GBM_SIGMA = BACKGROUND_GBM_SIGMA_ESTIMATED

# ILLUSTRATIVE, not data-calibrated -- only ~5 paired years of Orkney background-generation data exist, nowhere near enough to fit a reversion rate.
# 8 years is a rough guess at grid-connection-queue/planning-cycle timescales, not a fitted value.
BACKGROUND_MR_HALFLIFE_YEARS = 8.0


# DFES background generation path times a cumulative unit-mean mean-reverting multiplier -- ONE shared multiplier per year across every tech column, not independent per-technology noise.
# Only spans base_background's own index (2026-2051).
def sample_background_seq(rng, base_background, sigma_bg=None, z_seq=None, halflife=None):
    if sigma_bg is None:
        sigma_bg = BACKGROUND_GBM_SIGMA
    if halflife is None:
        halflife = BACKGROUND_MR_HALFLIFE_YEARS
    n_years = len(base_background.index)
    mult = _ou_mult_seq(rng, n_years, sigma_bg, np.log(2) / halflife, z_seq=z_seq)
    return base_background.multiply(mult, axis=0)
