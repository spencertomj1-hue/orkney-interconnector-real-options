"""Orkney operational onshore wind from the DESNZ REPD (sheet 'REPD')."""

import pandas as pd

PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
        "Methodology_4/Coding/Inputs/Data/Generation/REPD_publication_Q1_2026.xlsx")

df = pd.read_excel(PATH, sheet_name="REPD")

col = lambda *k: next(c for c in df.columns
                      if all(w.lower() in str(c).lower() for w in k))
auth, tech = col("authority"), col("technology")
stat, cap, site = col("status"), col("capacity"), col("site", "name")

o = df[df[auth].astype(str).str.contains("Orkney", na=False)].copy()
o[cap] = pd.to_numeric(o[cap], errors="coerce")

print(o.groupby([tech, stat])[cap].sum().round(2).to_string())

w = o[o[tech].astype(str).str.contains("Wind Onshore|Onshore Wind", case=False, na=False)]
op = w[w[stat].astype(str).str.contains("Operational", case=False, na=False)]

print(f"\nOperational onshore wind: {op[cap].sum():.3f} MW ({len(op)} sites)")
print("Existing_Wind currently:  52.239 MW\n")

print("--- all Orkney onshore wind sites ---")
print(w[[site, stat, cap]].sort_values(cap, ascending=False).to_string(index=False))