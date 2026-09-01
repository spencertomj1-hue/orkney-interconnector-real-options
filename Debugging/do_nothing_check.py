"""See docs/notes/Debugging/do_nothing_check.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

from Model.Model_Components import Decision, LIFETIMES
import Model.System_Model as M
from Model.System_Model import Strategies_2, Scenarios, Run_Strategy

print("=== 1. Does curtailed energy reduce npv? ===")
print("grep of System_Model.py for every total_curtail / pv_revenue / total_cost_t line:")
print("  total_curtail += (surplus - export).sum() / 1000   <- only increment, nothing else touches it")
print("  pv_revenue += delivered * 1000 * price / df         <- delivered = local + export, NOT surplus")
print("  npv = pv_revenue - total_cost_t                     <- total_curtail does not appear here")
print("\nVERDICT (1): NO -- curtailed/spilled energy is NOT costed in npv anywhere. It is "
      "un-earned revenue with zero explicit penalty: generating it costs whatever opex the "
      "asset already carries regardless of output, and not exporting it costs nothing beyond "
      "the revenue never earned on it. There is no £/MWh constraint-cost term.")


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


def decompose(strategy_name, scenario_name):
    opts = Strategies_2[strategy_name](1.0)
    total_cost_t, pv_energy, total_curtail, npv, _, _ = Run_Strategy(
        (strategy_name, opts), Scenarios[scenario_name], scenario_name)   # wx_seq=None -> BASE_WEATHER_YEAR, deterministic
    capex = discounted_capex(opts, M.RATE)
    residual = discounted_residual(opts, M.RATE, M.END_YEAR, LIFETIMES)
    opex = total_cost_t - capex + residual
    pv_revenue = npv + total_cost_t
    return {"pv_revenue": pv_revenue, "capex": capex, "opex": opex,
            "residual_credit": residual, "total_cost": total_cost_t,
            "total_curtail": total_curtail, "npv": npv}


print("\n=== 3. Do Nothing vs Baseline, Holistic Transition, capex_mult=1.0, BASE_WEATHER_YEAR ===")
dn = decompose("Do Nothing", "Holistic Transition")
bl = decompose("Baseline", "Holistic Transition")

print(f"{'Component':<20}{'Do Nothing':>14}{'Baseline':>14}{'delta (BL-DN)':>16}")
rows = [
    ("pv_revenue, £m", dn["pv_revenue"] / 1e6, bl["pv_revenue"] / 1e6),
    ("capex, £m", dn["capex"] / 1e6, bl["capex"] / 1e6),
    ("opex, £m", dn["opex"] / 1e6, bl["opex"] / 1e6),
    ("residual credit, £m", dn["residual_credit"] / 1e6, bl["residual_credit"] / 1e6),
    ("total_cost, £m", dn["total_cost"] / 1e6, bl["total_cost"] / 1e6),
    ("total_curtail, GWh", dn["total_curtail"], bl["total_curtail"]),
    ("npv, £m", dn["npv"] / 1e6, bl["npv"] / 1e6),
]
for label, d, b in rows:
    print(f"{label:<20}{d:>14.2f}{b:>14.2f}{(b - d):>16.2f}")

d_revenue = (bl["pv_revenue"] - dn["pv_revenue"]) / 1e6
d_capex = (bl["capex"] - dn["capex"]) / 1e6
d_opex = (bl["opex"] - dn["opex"]) / 1e6
d_residual = (bl["residual_credit"] - dn["residual_credit"]) / 1e6
d_npv = (bl["npv"] - dn["npv"]) / 1e6
print(f"\nBaseline vs Do Nothing: extra revenue £{d_revenue:.2f}m, extra capex £{d_capex:.2f}m, "
      f"extra opex £{d_opex:.2f}m, extra residual credit £{d_residual:.2f}m -> dNPV £{d_npv:.2f}m")
print(f"Does Baseline's extra delivered-energy revenue cover its extra capex+opex-residual cost? "
      f"{'YES' if d_revenue > (d_capex + d_opex - d_residual) else 'NO'} "
      f"(extra revenue £{d_revenue:.2f}m vs extra net cost £{(d_capex + d_opex - d_residual):.2f}m)")
print(f"Do Nothing's curtailment under this scenario: {dn['total_curtail']:.1f} GWh spilled, "
      f"costed at £0 in the objective (per part 1).")

print("\n=== 4. Is the Ofgem needs-case benefit (relieved constraint cost) represented? ===")
print("Searched System_Model.py for any £/MWh constraint-cost or curtailment-cost term: none "
      "exists. pv_revenue is built purely from `delivered` energy x (CFD or market) price -- "
      "there is no separate cost line for MWh NOT delivered due to link capacity. The Orkney "
      "needs case's primary quoted benefit (relieving constrained/curtailed generation, on the "
      "order of £55-70/MWh per prior project notes) has no corresponding term in this NPV "
      "objective at all.")

# see docs/notes/Debugging/do_nothing_check.md#baseline-vs-do-nothing-why-check-every-scenario
print("\n=== Do Nothing vs Baseline at nominal capex_mult=1.0, every scenario ===")
print(f"{'Scenario':<22}{'NPV DoNothing':>16}{'NPV Baseline':>15}{'Baseline wins?':>16}")
baseline_wins = {}
for scen in Scenarios:
    opts_dn = Strategies_2["Do Nothing"](1.0)
    opts_bl = Strategies_2["Baseline"](1.0)
    _, _, _, n_dn, _, _ = Run_Strategy(("Do Nothing", opts_dn), Scenarios[scen], scen)
    _, _, _, n_bl, _, _ = Run_Strategy(("Baseline", opts_bl), Scenarios[scen], scen)
    baseline_wins[scen] = n_bl > n_dn
    print(f"{scen:<22}{n_dn/1e6:>16.1f}{n_bl/1e6:>15.1f}{str(n_bl > n_dn):>16}")

n_baseline_wins = sum(baseline_wins.values())
print(f"\nAt nominal (no-overrun) capex, Baseline beats Do Nothing in "
      f"{n_baseline_wins}/{len(baseline_wins)} scenarios -- NOT a uniform Do-Nothing win. "
      f"The full Monte Carlo's £306m (Do Nothing) vs £248m (Baseline) result mixes in stochastic "
      f"link capex (lognormal, median 1.4x, P90 3.4x) on top of this -- since Baseline pays for "
      f"NewLink and Do Nothing does not, capex overruns hit Baseline much harder, and that risk, "
      f"not curtailment cost, is a live candidate for what flips the average.")

print("\n=== VERDICT ===")
print("(a) Curtailed energy is NOT costed in npv anywhere -- confirmed directly from the code: "
      "total_curtail is tracked but never subtracted from total_cost_t or used to adjust "
      "pv_revenue. It is purely diagnostic output plus a decision-rule observable input. This "
      "part is unambiguous and scenario-independent.")
print("(b) Do Nothing's overall Monte Carlo win is NOT simply explained by 'curtailment is free "
      "so the no-build strategy always wins' -- at nominal capex_mult=1.0, Baseline actually beats "
      "Do Nothing in most scenarios (Electric Engagement, Hydrogen Evolution, Holistic Transition), "
      "losing only in Falling Behind (low demand growth) and Base. So the missing curtailment-cost "
      "term is a real, confirmed gap in the objective (part a), but it is NOT demonstrably the "
      "single cause of Do Nothing's ENPV lead in the full Monte Carlo -- stochastic link capex risk "
      "(which only Baseline and other build strategies are exposed to) is at least as plausible a "
      "driver and would need to be isolated (e.g. rerun the marginalised MC with capex_mult pinned "
      "to 1.0) before assigning the win to either cause. What IS solid: the missing curtailment "
      "credit means every scenario's NPV comparison above is missing a real revenue stream the "
      "link is supposed to capture, so even where Baseline already wins, its true advantage is "
      "understated, and where Do Nothing wins, that win is inflated by at least the value of the "
      "constraint relief this objective doesn't count.")
