"""See docs/notes/Debugging/spurness_fix_report.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import Model.Model_Components as MC
from Model.Model_Components import Existing_Wind, Existing_PV
from Model.System_Model import Strategies_2, Scenarios, Run_Strategy

print("=== Final vintage schedule (REPD real capacities, no rescale) ===")
print(f"{'Asset':<14}{'Commission':>11}{'Retire':>8}{'Capacity, MW':>14}")
wind_total = 0.0
for a, cy in MC.EXISTING_FLEET:
    retire = cy + MC.LIFETIMES[a.Classification()]
    print(f"{type(a).__name__:<14}{cy:>11}{retire:>8}{a.Capacity():>14.3f}")
    if a.Type() == "Wind":
        wind_total += a.Capacity()
pv_total = sum(a.Capacity() for a, _ in MC.EXISTING_FLEET if a.Type() == "PV")
fleet_total = wind_total + pv_total
print(f"\nTotal wind (REPD real, no rescale): {wind_total:.3f} MW")
print(f"Total PV (placeholder, unchanged):  {pv_total:.3f} MW")
print(f"Fleet total: {fleet_total:.3f} MW  vs regional-stats 52.239 + 1.558 = 53.797 MW "
      f"(gap {fleet_total - 53.797:+.3f} MW, {(fleet_total - 53.797) / 53.797 * 100:+.1f}%) "
      f"-- flagged for the write-up, not reconciled.")

print("\n=== Retirement schedule, 2019-2051 (MW retiring that year) ===")
retirements = {}
for a, cy in MC.EXISTING_FLEET:
    retire_year = cy + MC.LIFETIMES[a.Classification()]
    retirements.setdefault(retire_year, []).append((type(a).__name__, a.Capacity()))
for year in sorted(retirements):
    parts = ", ".join(f"{name} {mw:.2f}MW" for name, mw in retirements[year])
    print(f"  {year}: {parts}")

print("\n=== Strategies_2 under Base: real REPD (~39.2 MW) vs previous even-rescale (52.239 MW) ===")
real_fleet = MC.EXISTING_FLEET   # current (unscaled) fleet


def npvs_for_fleet(fleet):
    MC.EXISTING_FLEET = fleet
    out = {}
    for sname, factory in Strategies_2.items():
        opts = factory(1.0)
        _, _, _, n, _, _ = Run_Strategy((sname, opts), Scenarios["Base"], "Base")
        out[sname] = n
    return out


real_npv = npvs_for_fleet(real_fleet)

# see docs/notes/Debugging/spurness_fix_report.md#previous-even-rescaled-version
rescaled_rows = []
import csv
with open(MC.REPD_WIND_VINTAGES_PATH, newline="") as f:
    for row in csv.DictReader(f):
        rescaled_rows.append((int(row["commission_year"]), float(row["capacity_mw"])))
repd_raw_total = sum(mw for _, mw in rescaled_rows)
rescale = 52.239 / repd_raw_total
rescaled_fleet = [(Existing_Wind(capacity=mw * rescale), year) for year, mw in rescaled_rows] \
                 + [(Existing_PV(), 2015)]
rescaled_npv = npvs_for_fleet(rescaled_fleet)

MC.EXISTING_FLEET = real_fleet   # restore

print(f"{'Strategy':<16}{'NPV real (~39.2)':>18}{'NPV rescaled (52.2)':>21}{'delta':>10}")
for sname in Strategies_2:
    r = real_npv[sname] / 1e6
    s = rescaled_npv[sname] / 1e6
    print(f"{sname:<16}{r:>18.2f}{s:>21.2f}{(r - s):>10.2f}")
