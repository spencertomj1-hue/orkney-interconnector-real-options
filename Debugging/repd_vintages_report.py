"""See docs/notes/Debugging/repd_vintages_report.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import Model.Model_Components as MC
from Model.Model_Components import Existing_Wind, Existing_PV
from Model.System_Model import Strategies_2, Scenarios, Run_Strategy

print("=== Extracted Orkney existing fleet (REPD wind vintages + PV) ===")
print(f"{'Asset':<14}{'Commission':>11}{'Retire':>8}{'Capacity, MW':>14}")
wind_total = 0.0
for a, cy in MC.EXISTING_FLEET:
    retire = cy + MC.LIFETIMES[a.Classification()]
    print(f"{type(a).__name__:<14}{cy:>11}{retire:>8}{a.Capacity():>14.3f}")
    if a.Type() == "Wind":
        wind_total += a.Capacity()
pv_total = sum(a.Capacity() for a, _ in MC.EXISTING_FLEET if a.Type() == "PV")
print(f"\nTotal wind (rescaled to match regional stats): {wind_total:.3f} MW")
print(f"Total PV: {pv_total:.3f} MW")

print("\n=== REPD-vs-existing capacity cross-check ===")
repd_raw_wind_total = 39.2   # from REPD_Existing_Wind_Vintages.py, current Development Status = Operational
existing_wind_stat = 52.239
pct_diff = (repd_raw_wind_total - existing_wind_stat) / existing_wind_stat * 100
print(f"REPD raw operational wind total:  {repd_raw_wind_total:.1f} MW")
print(f"Existing_Wind (regional stats):   {existing_wind_stat:.3f} MW")
print(f"Divergence: {pct_diff:+.1f}% -- MATERIAL (>10%), flagged, NOT silently overwritten.")
print("Resolution: kept the 52.239 MW total; used REPD only for the relative "
      "vintage-year split (each REPD vintage rescaled by 52.239/39.2).")
print("REPD has zero Orkney rows with any solar/PV Technology Type -- "
      "Existing_PV's commission year (2015) could not be sourced from REPD "
      "and remains a placeholder.")

print("\n=== Retirement schedule, 2019-2051 (MW retiring that year) ===")
retirements = {}
for a, cy in MC.EXISTING_FLEET:
    retire_year = cy + MC.LIFETIMES[a.Classification()]
    retirements.setdefault(retire_year, []).append((type(a).__name__, a.Capacity()))
for year in sorted(retirements):
    parts = ", ".join(f"{name} {mw:.2f}MW" for name, mw in retirements[year])
    print(f"  {year}: {parts}")

print("\n=== Strategies_2 under Base: staggered REPD vintages vs old single-lump ===")
staggered_fleet = MC.EXISTING_FLEET   # current (already REPD-derived) fleet

def npvs_for_fleet(fleet):
    MC.EXISTING_FLEET = fleet
    out = {}
    for sname, factory in Strategies_2.items():
        opts = factory(1.0)
        _, _, _, n, _, _ = Run_Strategy((sname, opts), Scenarios["Base"], "Base")
        out[sname] = n
    return out

staggered_npv = npvs_for_fleet(staggered_fleet)

# see docs/notes/Debugging/repd_vintages_report.md#old-single-lump-fleet-baseline
single_lump_fleet = [(Existing_Wind(), 2010), (Existing_PV(), 2015)]
single_lump_npv = npvs_for_fleet(single_lump_fleet)

MC.EXISTING_FLEET = staggered_fleet   # restore

print(f"{'Strategy':<16}{'NPV staggered':>15}{'NPV single-lump':>17}{'delta':>10}")
for sname in Strategies_2:
    s = staggered_npv[sname] / 1e6
    l = single_lump_npv[sname] / 1e6
    print(f"{sname:<16}{s:>15.2f}{l:>17.2f}{(s - l):>10.2f}")
