# [1] Henao, Sauma, Reyes, Gonzalez (2017) Value of the option to defer a
#     transmission investment, Energy Economics 65.
# [2] Nur, MacKenzie, Min (2026) Valuation of a sequential compound option for
#     generation/transmission expansion, J. Economy and Technology 4.
# [3] Graca Gomes, Cardin, Wu (2025) Strategic real options for solar PV, IET PNZ 2025.

import csv
import os
import sys
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

import numpy as np
from Model.Options import REBASE_2018_TO_2023
from Model.Model_Components import Decision, Generation_Capacity, Link_Capacity, LIFETIMES, EXISTING_FLEET_NAMEPLATE
from Model.Decision_Rules import Rule, MAIN_LINK_BG_GEN_THRESHOLD
from Model.Demand import base, Demand_EE, Demand_HE, Demand_FB, Demand_HT, LEVEL_2019
# Stochastic drivers (weather library, GBM demand/price/background paths, capex cost-overrun calibration + noisy early estimate) live in Uncertainty.py.
# Re-imported here so M.<name> keeps working for Reporting's per-draw sampling calls and sensitivity sweeps.
from Model.Uncertainty import (
    AVAIL, compute_wind_cf_by_year, WIND_CF_BY_YEAR, DEM_SHAPE_BY_YEAR,
    _year_means, BASE_WEATHER_YEAR, sample_wx_seq, sample_capex_estimate_seq,
    CAPEX_MEDIAN, CAPEX_SIGMA, CAPEX_MU, CAPEX_P90, MAIN_LINK_COST_CAP,
    GBM_SHOCK_CORR, sample_correlated_gbm_shocks, sample_demand_seq, sample_price_seq,
    sample_background_seq,
)
# Candidate strategies (rigid + flexible) live in Strategies.py; re-imported
# here for the same reason.
from Model.Strategies import Strategies_2, Strategies_Flex, _flexible_cost_aware, _flexible_staged
from Inputs.Data_Processing.CF.PV_CF import PV_CF
from Inputs.Data_Processing.Generation.DFES_Background import BACKGROUND
from Inputs.Data_Processing.Generation.Prices import price_series as _price_series_raw
from functools import lru_cache

# Gates a post-hoc PRIM-input capture block in Results.py, right after the headline marginalised MC loop; False skips that block entirely (no file written, no behaviour change).
# Never reads the PRIM library itself from here or from Results.py -- that stays isolated in Scenario_Discovery.py, a standalone file this model never imports.
SCENARIO_DISCOVERY = True

# price_series depends only on (scenario_name, YEARS), never on capex_mult or
# strategy, so it's safe to memoise for the Monte Carlo sweep in Results.py.
@lru_cache(maxsize=None)
def _price_series_cached(scenario_name, years_tuple):
    return _price_series_raw(scenario_name, years_tuple)

def price_series(scenario_name, years):
    return _price_series_cached(scenario_name, tuple(years))

MARINE_CF = 0.30                                    # placeholder, flat

RATE = 0.035   # social discount rate; swept in Results.py

# HM Treasury Green Book's actual declining long-term discount rate schedule, current as of the 2026 Green Book: (year_upper_bound_inclusive, rate) pairs, rate applies to appraisal years 1..upper at that band.
# Only the first two bands are ever reached by this model's 33-year horizon.
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

# £/MWh, on spilled generation -- the interconnector's primary Ofgem needs-case benefit, the same role a congestion/deferral penalty plays in [1]'s TEP real-options model.
# £55/MWh = regulator-vetted CENTRAL (GHD Western Isles Transmission CBA, Aug 2018), conservative against the realised £98/MWh 2017/18 Scotland cost (National Grid MBSS); rebased 2018->2023.
CONSTRAINT_COST = 55 * REBASE_2018_TO_2023

# Sweep for Results.py, single source of truth: 55=central, 70=conservative-upper, 98=realised 2017/18 anchor (MBSS).
CONSTRAINT_COST_SWEEP = [round(v * REBASE_2018_TO_2023, 2) for v in (55, 70, 98)]

# Link Capex() includes the stochastic overrun draw -- crediting residual value on that (True) would refund a cost overrun as salvage.
# Default False computes residual on base capex (capex_mult=1.0) instead; generation assets are unaffected, they never take capex_mult at all.
RESIDUAL_ON_OVERRUN = False

PROFILES = {"PV": PV_CF}

TIDAL_PERIOD = 12.42                                  # hours, M2 lunar semi-diurnal
_h = np.arange(8760)
_raw = np.abs(np.sin(2 * np.pi * _h / TIDAL_PERIOD)) ** 3   # power ~ velocity^3
PROFILES["Marine"] = np.clip(_raw * (MARINE_CF / _raw.mean()), 0.0, 1.0)

YEARS = list(range(2019, 2052))          # limit of Demand.py / DFES data
END_YEAR = YEARS[-1]

# CfD strike held flat in real terms -- CPI-indexing rebases 39.65 (£2012/MWh) to PRICE_BASE_YEAR once, rather than escalating it nominally every year.
# PRICE_BASE_YEAR must match capex/price_series's price base -- both UNVERIFIED; 2023 is a working assumption pending that check.
PRICE_BASE_YEAR = 2023

# ONS CPI annual index (2015=100), 2012-2025, from commonly-cited ONS rates (not a live ONS query) -- verify against published series D7BT/L522 before submission.
# Beyond 2025, extended flat at CPI_FLAT_ASSUMPTION_RATE.
CPI_PATH = os.path.join(REPO_ROOT, "Inputs", "Data", "cpi_index.csv")
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

# Alternative to background_gen_mw for make_main_link_rule (observable="growth_index", default off): blends demand's own growth with background_gen_mw's growth so both exogenous DFES drivers register, not only generation.
# Checked against DFES data: does not diverge meaningfully earlier than background_gen_mw alone; GROWTH_INDEX_BLEND_WEIGHT's 50/50 split has no independent justification, tune directly.
GROWTH_INDEX_BLEND_WEIGHT = 0.5
GROWTH_INDEX_DEMAND_REF = LEVEL_2019               # demand's own 2019 base level, GWh
GROWTH_INDEX_BG_REF = MAIN_LINK_BG_GEN_THRESHOLD   # 135MW, Ofgem's condition -- reused, not reinvented


def set_rate(r): # Rebind the discount rate. Used by the sensitivity sweep in Results
    global RATE
    RATE = r

G = Generation_Capacity()
L = Link_Capacity()

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
    # LCOT (Levelised Cost of Transmission): Link-only discounted cost and discounted energy actually exported through the link.
    # A subset of total_cost_t/pv_energy above, tracked in parallel, not derived from them after the fact.
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

        # Subtract the existing fleet's original nameplate permanently (not life-gated) so it's represented once and retires once -- a life-gated subtraction would let the immortal DFES base silently re-add retired capacity.
        # background_seq lets the MC loop inject a noisy (GBM) path; None keeps the deterministic BACKGROUND[scenario] lookup.
        bg = background_seq if background_seq is not None else BACKGROUND.get(scenario_name)
        if bg is not None and Year in bg.index:
            for tech, mw in bg.loc[Year].items():
                bg_net = max(0.0, mw - EXISTING_FLEET_NAMEPLATE.get(tech, 0.0))
                caps[tech] = caps.get(tech, 0.0) + bg_net
                state["background_gen_mw"][t] += bg_net
                # dfes_background_gen_mw and background_gen_mw are updated identically here -- DFES is the only source feeding either one now that the exogenous wind-buildout background was removed.
                # Kept as a separate observable (rather than collapsed into background_gen_mw) since Decision_Rules.py still offers it as a distinct trigger observable choice.
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
        pv_link_export += (export.sum() / 1000) / df   # LCOT denominator -- energy through the link only, not local consumption
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
        if "headroom_p90" in _needed_observables:
            state["headroom_p90"][t] = np.percentile(surplus, 90) - link
        state["delivered"][t] = delivered
        state["gen_total"][t] = gen_h.sum()
        # Fix B (make_npv_gate): the price the currently-delivered mix earns, used as a proxy for what newly-deliverable (currently curtailed) energy would earn once the link removes the constraint.
        # Unconditional -- already computed above, no extra cost.
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