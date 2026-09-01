"""See docs/notes/Inputs/Data_Processing/Generation/DFES_Gen.md#overview for full description."""

import pandas as pd

PATH = "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding/Inputs/Data/DFES/2025_DFES_Projections.csv"

# Why excluded: see docs/notes/Inputs/Data_Processing/Generation/DFES_Gen.md#why-backup-plant-and-storage-are-excluded
EXCLUDE = [
    "Diesel",
    "Gas",
    "Renewable Engines (Landfill Gas, Sewage Gas, Biogas)",
    "Battery storage",
]

# Sourcing WIND_OPERATIONAL: see docs/notes/Inputs/Data_Processing/Generation/DFES_Gen.md#sourcing-wind_operational
WIND_OPERATIONAL = 52.239

# Assets modelled as Decisions in System_Model, MW. Removed from the pipeline
# above WIND_OPERATIONAL so they are not counted twice.
DECISION_MW = 16.3 + 20.4 + 8 + 28.8 * 3   # Costa, Hesta, Hammars Hill ext, OIC x3

YEARS = [str(y) for y in range(2026, 2052)]

df = pd.read_csv(PATH)
o = df[(df.Local_authority == "Orkney Islands") & (df.Category == "Generation")].copy()
o = o[~o.Technology.isin(EXCLUDE)]
o[YEARS] = o[YEARS].apply(pd.to_numeric, errors="coerce")

gen = o.groupby(["Scenario", "Technology"])[YEARS].sum()

print("--- DFES generation capacity after excluding backup and storage, MW ---")
print(gen.groupby("Scenario").sum()[["2026", "2030", "2040", "2050"]].round(1).to_string())

print("\n--- onshore wind as published (note the 2026 disagreement) ---")
w = gen.xs("Onshore wind", level="Technology")
print(w[["2026", "2030", "2040", "2050"]].round(1).to_string())

# --- onshore wind: operational base + pipeline, less decision assets ---------
if WIND_OPERATIONAL is None:
    print("\nWIND_OPERATIONAL not set. Onshore wind left as published.")
    print("Set it from REPD/SSEN before using this output in the model.")
else:
    idx = gen.index.get_level_values("Technology") == "Onshore wind"
    pipeline = (gen.loc[idx] - WIND_OPERATIONAL).clip(lower=0)
    gen.loc[idx] = (pipeline - DECISION_MW).clip(lower=0) + WIND_OPERATIONAL
    print(f"\nonshore wind = {WIND_OPERATIONAL:.1f} MW operational "
          f"+ pipeline less {DECISION_MW:.1f} MW of Decision assets")

out = gen.T
out.index.name = "year"
out.index = out.index.astype(int)

print("\n--- background capacity by technology, MW (Holistic Transition) ---")
print(out["Holistic Transition"].round(1).to_string())

out.to_csv("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding/Inputs/Data/DFES/dfes_generation_MW.csv")