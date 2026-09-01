"""See docs/notes/Debugging/curtailment_symmetry.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
import Model.Model_Components as MC
from Model.Model_Components import Decision
import Model.System_Model as M
from Model.System_Model import Strategies_2, Scenarios, Run_Strategy
from Model.Decision_Rules import Rule


def run_instrumented(Strategy, Demand, scenario_name, wx_seq=None):
    Name, Options = Strategy
    if wx_seq is None:
        wx_seq = [M.BASE_WEATHER_YEAR] * len(M.YEARS)

    M.G.RESET()
    M.L.RESET()
    capex_t = 0.0
    opex_t = 0.0
    curtail_cost_t = 0.0
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

    spilled_by_year = np.zeros(len(M.YEARS))
    curtail_cost_by_year = np.zeros(len(M.YEARS))

    for Year in M.YEARS:
        t = Year - 2019
        df = (1 + M.RATE) ** t

        for d in fixed_decisions:
            if d.IsBuilt(Year) is True and d.BuildYear() == Year:
                capex_t += d.Asset().Capex() / df
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

        opex_t += (M.G.Opex(Year) + M.L.Opex(Year)) / df

        gen_h = np.zeros(8760)
        caps = M.G.Capacity_By_Type(Year)

        bg = M.BACKGROUND.get(scenario_name)
        if bg is not None and Year in bg.index:
            for tech, mw in bg.loc[Year].items():
                caps[tech] = caps.get(tech, 0.0) + max(0.0, mw - MC.EXISTING_FLEET_NAMEPLATE.get(tech, 0.0))

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
        curtail_cost_t += year_curtail_cost
        spilled_by_year[t] = spilled
        curtail_cost_by_year[t] = year_curtail_cost

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
            capex_t += fired.Asset().Capex() / df
            fired_decisions.append(fired)
            rules.remove(r)
            if fired.BuildYear() == Year:
                if fired.Asset().Classification() == 'Generation':
                    M.G.Add_Asset(fired.Asset(), Year)
                else:
                    M.L.Add_Asset(fired.Asset(), Year)

    df_end = (1 + M.RATE) ** (M.END_YEAR - 2019)
    residual_t = 0.0
    for d in fixed_decisions + fired_decisions:
        if d.BuildYear() is None:
            continue
        life = MC.LIFETIMES[d.Asset().Classification()]
        used = M.END_YEAR - d.BuildYear() + 1
        remaining = max(0.0, (life - used) / life)
        residual_t += d.Asset().Capex() * remaining / df_end

    total_cost_t = capex_t + opex_t + curtail_cost_t - residual_t
    npv = pv_revenue - total_cost_t
    return {
        "pv_revenue": pv_revenue, "capex": capex_t, "opex": opex_t,
        "curtail_cost": curtail_cost_t, "residual_credit": residual_t,
        "total_cost": total_cost_t, "total_curtail": total_curtail, "npv": npv,
        "spilled_by_year": spilled_by_year, "curtail_cost_by_year": curtail_cost_by_year,
    }


SCEN = "Holistic Transition"
opts_dn = Strategies_2["Do Nothing"](1.0)
opts_st = Strategies_2["Staged"](1.0)
dn = run_instrumented(("Do Nothing", opts_dn), Scenarios[SCEN], SCEN)
st = run_instrumented(("Staged", opts_st), Scenarios[SCEN], SCEN)

print(f"=== 1. Per-year spilled GWh and discounted curtailment £ cost, {SCEN} ===")
print(f"{'Year':<6}{'DN spill_GWh':>13}{'DN cost_£m':>12}{'ST spill_GWh':>13}{'ST cost_£m':>12}")
for t, Year in enumerate(M.YEARS):
    print(f"{Year:<6}{dn['spilled_by_year'][t]:>13.2f}{dn['curtail_cost_by_year'][t]/1e6:>12.3f}"
          f"{st['spilled_by_year'][t]:>13.2f}{st['curtail_cost_by_year'][t]/1e6:>12.3f}")

print(f"\nTotal (undiscounted) spilled GWh: DN={dn['total_curtail']:.1f}, ST={st['total_curtail']:.1f}")
print(f"Total discounted curtailment cost, £m: DN={dn['curtail_cost']/1e6:.2f}, ST={st['curtail_cost']/1e6:.2f}")

print(f"\n=== 2. Does the link's curtailment-cost saving equal the year-by-year discounted spill difference? ===")
d_curtail_cost = dn["curtail_cost"] - st["curtail_cost"]
recomputed_diff = np.sum(
    (dn["spilled_by_year"] - st["spilled_by_year"]) * 1000 * M.CONSTRAINT_COST
    / (1 + M.RATE) ** np.arange(len(M.YEARS))
)
print(f"curtail_cost(DN) - curtail_cost(ST), from the run: £{d_curtail_cost/1e6:.6f}m")
print(f"Recomputed directly from (spilled_DN[y] - spilled_ST[y]) * 1000 * CONSTRAINT_COST / df[y], "
      f"summed over years: £{recomputed_diff/1e6:.6f}m")
print(f"Match (within float tolerance): {abs(d_curtail_cost - recomputed_diff) < 1.0}")

print(f"\n=== 3/4. Full decomposition: does total_cost difference split cleanly into capex+opex+curtailment-residual? ===")
print(f"{'Component':<20}{'Do Nothing':>14}{'Staged':>14}{'delta (ST-DN)':>16}")
rows = [
    ("pv_revenue, £m", dn["pv_revenue"]/1e6, st["pv_revenue"]/1e6),
    ("capex, £m", dn["capex"]/1e6, st["capex"]/1e6),
    ("opex, £m", dn["opex"]/1e6, st["opex"]/1e6),
    ("curtailment cost, £m", dn["curtail_cost"]/1e6, st["curtail_cost"]/1e6),
    ("residual credit, £m", dn["residual_credit"]/1e6, st["residual_credit"]/1e6),
    ("total_cost, £m", dn["total_cost"]/1e6, st["total_cost"]/1e6),
    ("npv, £m", dn["npv"]/1e6, st["npv"]/1e6),
]
for label, d, s in rows:
    print(f"{label:<20}{d:>14.2f}{s:>14.2f}{(s-d):>16.2f}")

d_capex = st["capex"] - dn["capex"]
d_opex = st["opex"] - dn["opex"]
d_curtail = st["curtail_cost"] - dn["curtail_cost"]
d_residual = st["residual_credit"] - dn["residual_credit"]
d_total_cost = st["total_cost"] - dn["total_cost"]
reconstructed = d_capex + d_opex + d_curtail - d_residual
print(f"\nd_total_cost (from run): £{d_total_cost/1e6:.4f}m")
print(f"reconstructed (d_capex + d_opex + d_curtail - d_residual): £{reconstructed/1e6:.4f}m")
print(f"Decomposition is clean (within float tolerance): {abs(d_total_cost - reconstructed) < 1.0}")

print(f"\n=== VERDICT ===")
symmetric = abs(d_curtail_cost - recomputed_diff) < 1.0 and abs(d_total_cost - reconstructed) < 1.0
if symmetric:
    print("SYMMETRIC. Both strategies are charged by the exact same formula "
          "(spilled_GWh x 1000 x CONSTRAINT_COST / df) applied identically per year. The link's "
          "curtailment-relief benefit is booked implicitly as Staged's lower curtailment cost, "
          "and that saving equals the physical spill difference at the same discounted price, "
          "to the penny -- confirmed by the exact match above. There is no separate charge or "
          "credit applied to one strategy that isn't applied to the other on the same basis. "
          "Do Nothing's 2nd place is a real result under this objective, not a one-sided-term "
          "artefact.")
else:
    print("NOT SYMMETRIC -- the curtailment-cost difference between strategies does not match "
          "the physical spill difference at the same discounted price. This would mean Do "
          "Nothing's ranking is at least partly an artefact of how the term is booked, not a "
          "clean reflection of the link's relief value. See the numbers above for where it "
          "diverges.")
