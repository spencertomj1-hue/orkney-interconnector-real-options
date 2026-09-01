"""See docs/notes/Debugging/early_delta.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import Model.Model_Components as MC
from Model.Model_Components import Generation_Capacity, Decision
import Model.System_Model as M
from Model.System_Model import Strategies_2, Scenarios, Run_Strategy, price_series

YEARS_WINDOW = range(2033, 2043)


def built_capacity_by_year(strategy_name):
    opts = Strategies_2[strategy_name](1.0)
    G = Generation_Capacity()   # standalone instance; RESET() already seeds the 2019 fleet
    for d in opts:
        if isinstance(d, Decision) and d.BuildYear() is not None \
                and d.Asset().Classification() == 'Generation':
            G.Add_Asset(d.Asset(), d.BuildYear())
    return {Year: G.Capacity_By_Type(Year) for Year in YEARS_WINDOW}


def year_series(strategy_name, scenario_name="Base"):
    opts = Strategies_2[strategy_name](1.0)
    _, _, _, _, state, _ = Run_Strategy((strategy_name, opts), Scenarios[scenario_name], scenario_name)
    out = {}
    for Year in YEARS_WINDOW:
        t = Year - 2019
        delivered = state["delivered"][t]                      # GWh
        gen_total = state["gen_total"][t] / 1000                # MWh -> GWh
        curtailed = gen_total - delivered                        # GWh, exact identity
        out[Year] = (delivered, curtailed, gen_total)
    return out


print("=== Built generation capacity online, MW (Capacity_By_Type, retirement-aware) ===")
for sname in ("Baseline", "Early"):
    caps = built_capacity_by_year(sname)
    print(f"\n{sname}:")
    print(f"{'Year':<6}{'Wind':>10}{'PV':>10}")
    for Year in YEARS_WINDOW:
        c = caps[Year]
        print(f"{Year:<6}{c.get('Wind', 0.0):>10.1f}{c.get('PV', 0.0):>10.1f}")

print("\n=== Delivered / curtailed / generated energy, GWh (Base scenario) ===")
series = {}
for sname in ("Baseline", "Early"):
    series[sname] = year_series(sname)
    print(f"\n{sname}:")
    print(f"{'Year':<6}{'Delivered':>12}{'Curtailed':>12}{'Generated':>12}{'Deliv/Gen':>11}")
    for Year in YEARS_WINDOW:
        d, c, g = series[sname][Year]
        frac = d / g if g > 0 else float("nan")
        print(f"{Year:<6}{d:>12.2f}{c:>12.2f}{g:>12.2f}{frac:>11.3f}")

print("\n=== Where Early and Baseline diverge: delivered-fraction gap ===")
print(f"{'Year':<6}{'Baseline Deliv/Gen':>20}{'Early Deliv/Gen':>18}{'gap':>10}")
for Year in YEARS_WINDOW:
    db, cb, gb = series["Baseline"][Year]
    de, ce, ge = series["Early"][Year]
    fb = db / gb if gb > 0 else float("nan")
    fe = de / ge if ge > 0 else float("nan")
    print(f"{Year:<6}{fb:>20.3f}{fe:>18.3f}{(fe - fb):>10.3f}")

# see docs/notes/Debugging/early_delta.md#cfd-share-mechanism-candidate-explanation
wind_profile_sum = M.WIND_CF_BY_YEAR[M.BASE_WEATHER_YEAR].sum()
pv_profile_sum = M.PROFILES["PV"].sum()
PRICE_YR = price_series("Base", M.YEARS)


def cfd_share_series(strategy_name):
    opts = Strategies_2[strategy_name](1.0)
    fixed_decisions = [d for d in opts if isinstance(d, Decision)]
    G = Generation_Capacity()
    for d in fixed_decisions:
        if d.BuildYear() is not None and d.Asset().Classification() == 'Generation':
            G.Add_Asset(d.Asset(), d.BuildYear())

    out = {}
    for Year in YEARS_WINDOW:
        t = Year - 2019
        caps = G.Capacity_By_Type(Year)
        wind_mw = caps.get("Wind", 0.0)
        pv_mw = caps.get("PV", 0.0)
        wind_gen = wind_mw * wind_profile_sum
        pv_gen = pv_mw * pv_profile_sum
        tot_e = wind_gen + pv_gen

        cfd_mw = 0.0
        for d in fixed_decisions:
            if d.BuildYear() is not None and Year >= d.BuildYear() \
                    and d.Asset().Classification() == 'Generation':
                if Year - d.BuildYear() < d.Asset().CFD_Lifetime():
                    cfd_mw += d.Asset().Capacity()

        cfd_share = (wind_gen * cfd_mw / wind_mw / tot_e) if wind_mw > 0 and tot_e > 0 else 0.0
        price = cfd_share * M.CFD_2023 + (1 - cfd_share) * PRICE_YR[t]
        out[Year] = (wind_mw, cfd_mw, cfd_share, price)
    return out


print("\n=== CFD share & effective price mechanism, retirement ON vs OFF ===")
_orig_gen_life = MC.LIFETIMES["Generation"]
for sname in ("Baseline", "Early"):
    print(f"\n{sname}:")
    print(f"{'Year':<6}{'wind_mw ON':>11}{'cfd_mw':>9}{'share ON':>10}{'price ON':>10}"
          f"{'wind_mw OFF':>12}{'share OFF':>11}{'price OFF':>11}{'d_price':>9}")
    on = cfd_share_series(sname)
    MC.LIFETIMES["Generation"] = 999
    off = cfd_share_series(sname)
    MC.LIFETIMES["Generation"] = _orig_gen_life
    for Year in YEARS_WINDOW:
        w_on, cfd_mw, share_on, price_on = on[Year]
        w_off, _, share_off, price_off = off[Year]
        print(f"{Year:<6}{w_on:>11.1f}{cfd_mw:>9.1f}{share_on:>10.3f}{price_on:>10.2f}"
              f"{w_off:>12.1f}{share_off:>11.3f}{price_off:>11.2f}{(price_on - price_off):>9.2f}")

# see docs/notes/Debugging/early_delta.md#full-horizon-decomposition-closing-the-loop
def discounted_capex(Options, rate):
    total = 0.0
    for d in Options:
        by = d.BuildYear()
        if by is None:
            continue
        total += d.Asset().Capex() / (1 + rate) ** (by - 2019)
    return total


def discounted_residual(Options, rate, end_year, lifetimes):
    df_end = (1 + rate) ** (end_year - 2019)
    total = 0.0
    for d in Options:
        by = d.BuildYear()
        if by is None:
            continue
        life = lifetimes[d.Asset().Classification()]
        used = end_year - by + 1
        remaining = max(0.0, (life - used) / life)
        total += d.Asset().Capex() * remaining / df_end
    return total


def full_decompose(strategy_name):
    opts = Strategies_2[strategy_name](1.0)
    total_cost_t, pv_energy, total_curtail, npv, _, _ = Run_Strategy(
        (strategy_name, opts), Scenarios["Base"], "Base")
    capex = discounted_capex(opts, M.RATE)
    residual = discounted_residual(opts, M.RATE, M.END_YEAR, MC.LIFETIMES)
    opex = total_cost_t - capex + residual
    pv_revenue = npv + total_cost_t
    return {"pv_revenue": pv_revenue, "capex": capex, "opex": opex,
            "residual_credit": residual, "npv": npv}


print("\n=== Full-horizon retirement delta (real - retirement-disabled), £m ===")
print(f"{'Strategy':<12}{'d_revenue':>11}{'d_capex':>10}{'d_opex':>9}{'d_residual':>12}{'d_npv':>9}")
for sname in ("Baseline", "Early"):
    after = full_decompose(sname)
    MC.LIFETIMES["Generation"] = 999
    before = full_decompose(sname)
    MC.LIFETIMES["Generation"] = _orig_gen_life
    d_rev = (after["pv_revenue"] - before["pv_revenue"]) / 1e6
    d_capex = (after["capex"] - before["capex"]) / 1e6
    d_opex = (after["opex"] - before["opex"]) / 1e6
    d_res = (after["residual_credit"] - before["residual_credit"]) / 1e6
    d_npv = (after["npv"] - before["npv"]) / 1e6
    print(f"{sname:<12}{d_rev:>11.2f}{d_capex:>10.2f}{d_opex:>9.2f}{d_res:>12.2f}{d_npv:>9.2f}")
