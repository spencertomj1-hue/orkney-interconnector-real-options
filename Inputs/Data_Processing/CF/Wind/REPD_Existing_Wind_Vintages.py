"""Orkney operational onshore wind vintages from the DESNZ REPD. Extracts the
real commission year for each currently-operational Orkney onshore wind
site, groups by commission year, and writes the result to
orkney_existing_wind_vintages.csv -- Model_Components.py reads that CSV
rather than parsing the 14k-row REPD workbook at import time. Re-run to
regenerate the CSV if REPD updates."""
import pandas as pd

PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
        "Methodology_4/Coding/Inputs/Data/Generation/REPD_publication_Q1_2026.xlsx")
OUT_PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
            "Methodology_4/Coding/Inputs/Data/Generation/orkney_existing_wind_vintages.csv")

df = pd.read_excel(PATH, sheet_name="REPD")

col = lambda *k: next(c for c in df.columns
                      if all(w.lower() in str(c).lower() for w in k))
auth, tech = col("authority"), col("technology")
stat, cap, site = col("status"), col("capacity"), col("site", "name")

o = df[df[auth].astype(str).str.contains("Orkney", na=False)].copy()
o[cap] = pd.to_numeric(o[cap], errors="coerce")

# REPD has zero Orkney rows for solar (only Wind Onshore, Battery, Hydrogen),
# so Existing_PV (1.558 MW) can't be sourced here -- it stays on its
# placeholder commission year in Model_Components.py, flagged there.
w = o[o[tech].astype(str).str.contains("Wind Onshore", case=False, na=False)]
op = w[w[stat].astype(str).str.contains("Operational", case=False, na=False)].copy()
op["commission_year"] = pd.to_datetime(op["Operational"]).dt.year

missing_date = op[op["Operational"].isna()]
if len(missing_date):
    print(f"WARNING: {len(missing_date)} operational site(s) missing an "
          f"Operational date -- falling back to Under Construction / "
          f"Planning Permission Granted date:")
    for fallback_col in ("Under Construction", "Planning Permission  Granted"):
        need = op["commission_year"].isna()
        op.loc[need, "commission_year"] = pd.to_datetime(
            op.loc[need, fallback_col]).dt.year
    print(op.loc[missing_date.index, [site, "commission_year"]].to_string(index=False))

grouped = (op.groupby("commission_year")
             .agg(capacity_mw=(cap, "sum"), sites=(site, lambda s: "; ".join(s)))
             .reset_index()
             .sort_values("commission_year"))

print("=== Orkney operational onshore wind, grouped by commission year (REPD, current status) ===")
print(grouped.to_string(index=False))
print(f"\nTotal REPD operational wind: {grouped['capacity_mw'].sum():.3f} MW "
      f"({op.shape[0]} sites, {len(grouped)} distinct commission years)")
print("Existing_Wind currently:      52.239 MW (regional renewable stats)")

grouped.to_csv(OUT_PATH, index=False)
print(f"\nWrote {OUT_PATH}")
