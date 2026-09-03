"""Derives KWH_PER_EV_CAR for Orkney from published data: annual miles per
car = Orkney car vehicle-miles / Orkney licensed cars; kWh per car per year
= miles per car x kWh per mile. Sources: Traffic_Volume.csv (DfT road
traffic statistics), CARS_LICENSED (DfT VEH0105), KWH_PER_MILE (external
assumption, real-world BEV consumption)."""

import pandas as pd
from pathlib import Path

EXTRA = Path("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding/Inputs/Data/Demand")
TRAFFIC = EXTRA / "Traffic_Volume.csv"

# --- inputs to set -----------------------------------------------------------
CARS_LICENSED = 11400    # SET ME: Orkney licensed cars from VEH0105
KWH_PER_MILE  = 0.32      # ~0.20 kWh/km. Sensitivity: 0.29 / 0.32 / 0.35
YEARS_AVG     = [2022, 2023, 2024, 2025]   # post-covid, excludes 2020-21 dip
# -----------------------------------------------------------------------------

d = pd.read_csv(TRAFFIC)
o = d[d.local_authority_name.str.contains("Orkney", case=False, na=False)].copy()
o = o[["year", "cars_and_taxis", "all_motor_vehicles"]].set_index("year")

print("--- Orkney vehicle miles (millions) ---")
print((o / 1e6).tail(10).round(1).to_string())

miles = o.loc[YEARS_AVG, "cars_and_taxis"].mean()
print(f"\nmean car vehicle-miles {YEARS_AVG}: {miles:,.0f}")

if CARS_LICENSED is None:
    print("\nCARS_LICENSED not set - showing sensitivity across plausible fleet sizes:")
    for n in [9000, 10000, 11000, 12000, 13000]:
        mpc = miles / n
        print(f"  {n:,} cars -> {mpc:,.0f} miles/car/yr -> "
              f"{mpc * KWH_PER_MILE:,.0f} kWh/car/yr")
    print("\nGet the real figure from VEH0105 and set CARS_LICENSED.")
else:
    miles_per_car = miles / CARS_LICENSED
    print(f"\nmiles per car per year : {miles_per_car:,.0f}")
    print(f"\n--- KWH_PER_EV_CAR sensitivity (kWh/mile) ---")
    for e in [0.29, 0.32, 0.35]:
        print(f"  {e:.2f} kWh/mile -> {miles_per_car * e:,.0f} kWh/car/yr")
    print(f"\nUSE: KWH_PER_EV_CAR = {miles_per_car * KWH_PER_MILE:,.0f}")