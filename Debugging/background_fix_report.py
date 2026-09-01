"""See docs/notes/Debugging/background_fix_report.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
import Model.Model_Components as MC
from Model.Model_Components import Decision
import Model.System_Model as M
from Model.System_Model import Strategies_2, Scenarios, Run_Strategy
from Model.Decision_Rules import Rule


def run_strategy_before_fix(Strategy, Demand, scenario_name, wx_seq=None):
    # see docs/notes/Debugging/background_fix_report.md#run_strategy_before_fix-whats-reverted
    Name, Options = Strategy
    if wx_seq is None:
        wx_seq = [M.BASE_WEATHER_YEAR] * len(M.YEARS)

    M.G.RESET()
    M.L.RESET()
    total_cost_t = 0
    pv_energy = 0
    pv_revenue = 0
    total_curtail = 0
    PRICE_YR = M.price_series(scenario_name, M.YEARS)

    fixed_decisions = [d for d in Options if isinstance(d, Decision)]
    rules = [d for d in Options if isinstance(d, Rule)]
    fired_decisions = []
    fired_names = set()

    state = {
        "curtail_frac": np.zeros(len(M.YEARS)),
        "hours_at_cap": np.zeros(len(M.YEARS)),
        "headroom_p90": np.zeros(len(M.YEARS)),
        "delivered": np.zeros(len(M.YEARS)),
        "gen_total": np.zeros(len(M.YEARS)),
    }

    def is_live(asset_name, yr):
        for d in fixed_decisions + fired_decisions:
            if type(d.Asset()).__name__ == asset_name and d.IsBuilt(yr):
                return True
        return False

    for Year in M.YEARS:
        t = Year - 2019
        df = (1 + M.RATE) ** t

        for d in fixed_decisions:
            if d.IsBuilt(Year) is True and d.BuildYear() == Year:
                total_cost_t += d.Asset().Capex() / df
                if d.Asset().Classification() == 'Generation':
                    M.G.Add_Asset(d.Asset(), Year)
                else:
                    M.L.Add_Asset(d.Asset(), Year)

        for fd in fired_decisions:
            if fd.BuildYear() == Year:
                if fd.Asset().Classification() == 'Generation':
                    M.G.Add_Asset(fd.Asset(), Year)
                else:
                    M.L.Add_Asset(fd.Asset(), Year)

        total_cost_t += (M.G.Opex(Year) + M.L.Opex(Year)) / df

        gen_h = np.zeros(8760)
        caps = M.G.Capacity_By_Type(Year)

        bg = M.BACKGROUND.get(scenario_name)
        if bg is not None and Year in bg.index:
            for tech, mw in bg.loc[Year].items():
                caps[tech] = caps.get(tech, 0.0) + max(0.0, mw - MC.existing_alive_mw(Year).get(tech, 0.0))

        profiles = dict(M.PROFILES)
        profiles["Wind"] = M.WIND_CF_BY_YEAR[wx_seq[t]]

        gen_by_tech = {}
        for tech, mw in caps.items():
            g = mw * profiles[tech]
            gen_by_tech[tech] = g
            gen_h += g

        dem_h = Demand[t] * 1000 * M.DEM_SHAPE
        link = M.L.Current_Total_Capacity(Year)

        local = np.minimum(gen_h, dem_h)
        surplus = np.maximum(gen_h - dem_h, 0)
        export = np.minimum(surplus, link)

        delivered = (local.sum() + export.sum()) / 1000
        pv_energy += delivered / df
        spilled = (surplus - export).sum() / 1000
        total_curtail += spilled
        total_cost_t += spilled * 1000 * M.CONSTRAINT_COST / df

        cfd_mw = 0
        for d in fixed_decisions + fired_decisions:
            if d.BuildYear() is not None and d.IsBuilt(Year) is True:
                if d.Asset().Classification() == 'Generation':
                    if Year - d.BuildYear() < d.Asset().CFD_Lifetime():
                        cfd_mw += d.Asset().Capacity()

        wind_mw, tot_e = caps.get("Wind", 0.0), gen_h.sum()
        if wind_mw > 0 and tot_e > 0:
            cfd_share = gen_by_tech["Wind"].sum() * cfd_mw / wind_mw / tot_e
        else:
            cfd_share = 0.0

        price = cfd_share * M.CFD_2023 + (1 - cfd_share) * PRICE_YR[t]
        pv_revenue += delivered * 1000 * price / df

        state["curtail_frac"][t] = ((surplus - export).sum() / gen_h.sum() if gen_h.sum() > 0 else 0.0)
        state["hours_at_cap"][t] = (export >= link * 0.99).sum()
        state["headroom_p90"][t] = np.percentile(surplus, 90) - link
        state["delivered"][t] = delivered
        state["gen_total"][t] = gen_h.sum()

        for r in list(rules):
            fired = r.maybe_fire(Year, t, state, is_live)
            if fired is None:
                continue
            assert r.name not in fired_names
            fired_names.add(r.name)
            total_cost_t += fired.Asset().Capex() / df
            fired_decisions.append(fired)
            rules.remove(r)
            if fired.BuildYear() == Year:
                if fired.Asset().Classification() == 'Generation':
                    M.G.Add_Asset(fired.Asset(), Year)
                else:
                    M.L.Add_Asset(fired.Asset(), Year)

    df_end = (1 + M.RATE) ** (M.END_YEAR - 2019)
    for d in fixed_decisions + fired_decisions:
        if d.BuildYear() is None:
            continue
        life = MC.LIFETIMES[d.Asset().Classification()]
        used = M.END_YEAR - d.BuildYear() + 1
        remaining = max(0.0, (life - used) / life)
        total_cost_t -= d.Asset().Capex() * remaining / df_end

    npv = pv_revenue - total_cost_t
    return total_cost_t, pv_energy, total_curtail, npv, state, {}


print("=== (a) NPV before vs after the double-count fix, capex_mult=1.0, BASE_WEATHER_YEAR ===")
print(f"{'Scenario':<22}{'Strategy':<14}{'NPV before':>12}{'NPV after':>11}{'delta':>9}")
for scen in Scenarios:
    for sname in Strategies_2:
        opts_before = Strategies_2[sname](1.0)
        opts_after = Strategies_2[sname](1.0)
        _, _, _, n_before, _, _ = run_strategy_before_fix((sname, opts_before), Scenarios[scen], scen)
        _, _, _, n_after, _, _ = Run_Strategy((sname, opts_after), Scenarios[scen], scen)
        print(f"{scen:<22}{sname:<14}{n_before/1e6:>12.2f}{n_after/1e6:>11.2f}{(n_after-n_before)/1e6:>9.2f}")

print("\n=== (b) Post-2026 DFES pipeline: is every increment too young to retire in-horizon? ===")
from Inputs.Data_Processing.Generation.DFES_Background import BACKGROUND
for scen, bg in BACKGROUND.items():
    years = bg.index.to_list()
    earliest_pipeline_year = years[1]   # first year after the pre-2026 base level, i.e. 2027
    retires_at = earliest_pipeline_year + 25
    print(f"{scen}: earliest possible post-2026 cohort commissions {earliest_pipeline_year}, "
          f"retires {retires_at} ({'> horizon 2051, negligible' if retires_at > 2051 else 'WITHIN horizon'})")

print("\n=== (c) Full MC, Equal weighting, n=2000, rigid strategies only, AFTER the fix ===")
weights = M.SCENARIO_WEIGHTS["Equal"]
scen_names = list(weights.keys())
scen_probs = list(weights.values())
n = 2000
rng = np.random.default_rng(42)
store = {sname: np.empty(n) for sname in Strategies_2}
for i in range(n):
    capex_mult = rng.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA)
    scenario = rng.choice(scen_names, p=scen_probs)
    wx_seq = rng.choice(M.WEATHER_YEARS, size=len(M.YEARS))
    demand = Scenarios[scenario]
    for sname, factory in Strategies_2.items():
        opts = factory(capex_mult)
        result = Run_Strategy((sname, opts), demand, scenario, wx_seq)
        store[sname][i] = result[3]
    if (i + 1) % 500 == 0:
        print(f"  {i+1}/{n}")

enpvs = {sname: vals.mean() for sname, vals in store.items()}
ranked = sorted(enpvs, key=lambda s: -enpvs[s])
print(f"\n{'Strategy':<18}{'ENPV_£m':>10}{'P5':>9}{'P50':>9}{'P95':>9}")
for sname, vals in store.items():
    v = vals / 1e6
    print(f"{sname:<18}{v.mean():>10.0f}{np.percentile(v,5):>9.0f}{np.percentile(v,50):>9.0f}{np.percentile(v,95):>9.0f}")
print(f"\nRanking after fix: {ranked}")
