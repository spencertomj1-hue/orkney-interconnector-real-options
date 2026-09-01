"""See docs/notes/Debugging/falling_behind_trace.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
import Model.Model_Components as MC
from Model.Model_Components import Decision
import Model.System_Model as M
from Model.System_Model import Strategies_2, Scenarios, Run_Strategy
from Model.Decision_Rules import Rule
from Inputs.Data_Processing.Generation.DFES_Background import BACKGROUND


def run_traced(Strategy, Demand, scenario_name, subtraction, wx_seq=None):
    # see docs/notes/Debugging/falling_behind_trace.md#run_traced-subtraction-parameter
    Name, Options = Strategy
    if wx_seq is None:
        wx_seq = [M.BASE_WEATHER_YEAR] * len(M.YEARS)

    M.G.RESET()
    M.L.RESET()
    total_cost_t = 0.0
    pv_energy = 0.0
    pv_revenue = 0.0
    total_curtail = 0.0
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

    trace = []   # per-year dict of diagnostics, only for years with a BACKGROUND entry

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
        decision_wind_mw = caps.get("Wind", 0.0)   # Decision-side wind, before background added

        bg = BACKGROUND.get(scenario_name)
        bg_wind_raw = None
        subtracted = None
        bg_wind_added = 0.0
        if bg is not None and Year in bg.index:
            for tech, mw in bg.loc[Year].items():
                if subtraction == "old":
                    sub_amount = MC.existing_alive_mw(Year).get(tech, 0.0)
                else:
                    sub_amount = MC.EXISTING_FLEET_NAMEPLATE.get(tech, 0.0)
                added = max(0.0, mw - sub_amount)
                caps[tech] = caps.get(tech, 0.0) + added
                if tech == "Wind":
                    bg_wind_raw = mw
                    subtracted = sub_amount
                    bg_wind_added = added

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
        year_curtail_cost = spilled * 1000 * M.CONSTRAINT_COST / df
        total_cost_t += year_curtail_cost

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
        year_revenue = delivered * 1000 * price / df
        pv_revenue += year_revenue

        state["curtail_frac"][t] = ((surplus - export).sum() / gen_h.sum() if gen_h.sum() > 0 else 0.0)
        state["hours_at_cap"][t] = (export >= link * 0.99).sum()
        state["headroom_p90"][t] = np.percentile(surplus, 90) - link
        state["delivered"][t] = delivered
        state["gen_total"][t] = gen_h.sum()

        if bg_wind_raw is not None:
            trace.append({
                "Year": Year, "decision_wind_mw": decision_wind_mw,
                "bg_wind_raw": bg_wind_raw, "subtracted": subtracted,
                "floor_clamped": (bg_wind_raw - subtracted) < 0,
                "bg_wind_added": bg_wind_added, "total_wind_mw": wind_mw,
                "gen_total_MWh": gen_h.sum(), "delivered_GWh": delivered,
                "spilled_GWh": spilled, "revenue_£m": year_revenue / 1e6,
                "curtail_cost_£m": year_curtail_cost / 1e6,
            })

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
    return npv, trace


def report(scenario_name):
    print(f"\n{'='*100}\nScenario: {scenario_name}\n{'='*100}")
    opts_old = Strategies_2["Do Nothing"](1.0)
    opts_new = Strategies_2["Do Nothing"](1.0)
    npv_old, trace_old = run_traced(("Do Nothing", opts_old), Scenarios[scenario_name], scenario_name, "old")
    npv_new, trace_new = run_traced(("Do Nothing", opts_new), Scenarios[scenario_name], scenario_name, "new")

    print(f"{'Year':<6}{'bg_raw':>8}{'sub_OLD':>9}{'sub_NEW':>9}{'add_OLD':>9}{'add_NEW':>9}"
          f"{'clamp_OLD':>10}{'clamp_NEW':>10}{'spill_OLD':>10}{'spill_NEW':>10}")
    for r_old, r_new in zip(trace_old, trace_new):
        assert r_old["Year"] == r_new["Year"]
        sub_old = MC.existing_alive_mw(r_old["Year"]).get("Wind", 0.0)
        sub_new = MC.EXISTING_FLEET_NAMEPLATE.get("Wind", 0.0)
        print(f"{r_old['Year']:<6}{r_old['bg_wind_raw']:>8.2f}{sub_old:>9.2f}{sub_new:>9.2f}"
              f"{r_old['bg_wind_added']:>9.2f}{r_new['bg_wind_added']:>9.2f}"
              f"{str(r_old['floor_clamped']):>10}{str(r_new['floor_clamped']):>10}"
              f"{r_old['spilled_GWh']:>10.2f}{r_new['spilled_GWh']:>10.2f}")

    total_spill_old = sum(r["spilled_GWh"] for r in trace_old)
    total_spill_new = sum(r["spilled_GWh"] for r in trace_new)
    total_rev_old = sum(r["revenue_£m"] for r in trace_old)
    total_rev_new = sum(r["revenue_£m"] for r in trace_new)
    total_cc_old = sum(r["curtail_cost_£m"] for r in trace_old)
    total_cc_new = sum(r["curtail_cost_£m"] for r in trace_new)
    n_clamped_old = sum(r["floor_clamped"] for r in trace_old)
    n_clamped_new = sum(r["floor_clamped"] for r in trace_new)

    print(f"\nTotal spilled GWh: OLD={total_spill_old:.1f}, NEW={total_spill_new:.1f}")
    print(f"Total discounted revenue, £m: OLD={total_rev_old:.2f}, NEW={total_rev_new:.2f}")
    print(f"Total discounted curtailment cost, £m: OLD={total_cc_old:.2f}, NEW={total_cc_new:.2f}")
    print(f"Years with floor clamped (mw < subtraction): OLD={n_clamped_old}/{len(trace_old)}, "
          f"NEW={n_clamped_new}/{len(trace_new)}")
    print(f"NPV: OLD={npv_old/1e6:.2f}m, NEW={npv_new/1e6:.2f}m, delta={((npv_new-npv_old)/1e6):.2f}m")


report("Falling Behind")
report("Electric Engagement")

print(f"\n{'='*100}\nVERDICT\n{'='*100}")
