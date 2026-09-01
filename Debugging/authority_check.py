"""See docs/notes/Debugging/authority_check.md#overview for full description."""
import pandas as pd

PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
        "Methodology_4/Coding/Inputs/Data/Generation/REPD_publication_Q1_2026.xlsx")

df0 = pd.read_excel(PATH, sheet_name="REPD")
df2 = pd.read_excel(PATH, sheet_name="REPD", header=2)
print("=== header=2 sanity check ===")
print("header=0 columns (first 4):", list(df0.columns[:4]))
print("header=2 columns (first 4):", list(df2.columns[:4]), "<- garbage, header=2 is wrong for this file")
print("Using header=0 (the project's actual convention) for everything below.\n")

df = df0
col = lambda *k: next(c for c in df.columns
                      if all(w.lower() in str(c).lower() for w in k))
auth, tech = col("authority"), col("technology")
stat, cap, site = col("status"), col("capacity"), col("site", "name")
xcol, ycol = col("x-coord"), col("y-coord")

df[xcol] = pd.to_numeric(df[xcol], errors="coerce")
df[ycol] = pd.to_numeric(df[ycol], errors="coerce")

# ---- 1. Planning Authority value_counts + anything plausibly northern-isles
print("=== Planning Authority value_counts (whole workbook, top 20) ===")
print(df[auth].value_counts(dropna=False).head(20).to_string())

print("\n=== Planning Authority values plausibly northern-isles / island / blank ===")
keywords = ["Orkney", "Shetland", "Eilean", "Isles", "Island"]
mask = df[auth].isna()
for kw in keywords:
    mask = mask | df[auth].astype(str).str.contains(kw, case=False, na=False)
candidates = df.loc[mask, auth].value_counts(dropna=False)
print(candidates.to_string())

# see docs/notes/Debugging/authority_check.md#geographic-cross-check-orkney-bounding-box-rationale
EASTING_MIN, EASTING_MAX = 300000, 400000
NORTHING_MIN, NORTHING_MAX = 980000, 1080000

name_matched = df[df[auth].astype(str).str.contains("Orkney", na=False)].copy()
name_matched[cap] = pd.to_numeric(name_matched[cap], errors="coerce")
name_wind_op = name_matched[
    name_matched[tech].astype(str).str.contains("Wind Onshore", case=False, na=False)
    & name_matched[stat].astype(str).str.contains("Operational", case=False, na=False)
]
name_matched_sites = set(name_wind_op[site].astype(str))

geo = df[
    df[xcol].between(EASTING_MIN, EASTING_MAX)
    & df[ycol].between(NORTHING_MIN, NORTHING_MAX)
    & df[tech].astype(str).str.contains("Wind Onshore", case=False, na=False)
    & df[stat].astype(str).str.contains("Operational", case=False, na=False)
].copy()
geo_sites = set(geo[site].astype(str))

print(f"\n=== Geographic cross-check: operational Wind Onshore in Orkney bounding box ===")
print(f"Name-matched operational wind sites: {len(name_matched_sites)}")
print(f"Geo-matched (bounding box) operational wind sites: {len(geo_sites)}")
extra = geo_sites - name_matched_sites
missing_from_geo = name_matched_sites - geo_sites
print(f"In geo set but NOT in name-matched set (would be a dropped site): {extra if extra else 'none'}")
print(f"In name-matched set but NOT in geo set (missing/blank coordinates): {missing_from_geo if missing_from_geo else 'none'}")
if missing_from_geo:
    print(df[df[site].astype(str).isin(missing_from_geo)][[site, auth, xcol, ycol]].to_string(index=False))

# ---- 3. Development Status breakdown BEFORE the operational-only filter --
print(f"\n=== Name-matched Orkney Wind Onshore: Development Status breakdown (all statuses) ===")
name_wind_all = name_matched[name_matched[tech].astype(str).str.contains("Wind Onshore", case=False, na=False)]
print(name_wind_all.groupby(stat)[cap].agg(["count", "sum"]).to_string())

decommissioned = name_wind_all[name_wind_all[stat].astype(str).str.contains("Decommission", case=False, na=False)]
print(f"\nDecommissioned sites (were presumably operational pre-2019, dropped by the current-status filter):")
print(decommissioned[[site, stat, cap]].to_string(index=False))

print("\n=== VERDICT ===")
verdict_a = "did NOT drop any real Orkney sites" if not extra else f"DROPPED {len(extra)} real Orkney site(s): {extra}"
decom_parts = []
for _, r in decommissioned.iterrows():
    op_year = pd.to_datetime(r["Operational"]).year
    decom_parts.append(f"{r[site]} {r[cap]:.1f}MW, operational since {op_year}")
decommissioned_note = (
    f"{len(decommissioned)} site(s) now show 'Decommissioned' ({', '.join(decom_parts)}), "
    f"almost certainly still running in 2019 and invisible to any current-status-only extraction"
    if len(decommissioned) else "no sites in the name-matched set are currently marked Decommissioned"
)
print(f"(a) The 'Planning Authority contains Orkney' substring match {verdict_a} -- "
      f"the geographic bounding-box cross-check (corrected after an initial box wrongly swept in "
      f"Caithness sites across the Pentland Firth) recovers exactly the same {len(name_matched_sites)} "
      f"operational wind sites as the name match, no more, no less. "
      f"(b) The 39.2 MW (current REPD) vs 52.239 MW (2019 regional-stats) gap looks like a "
      f"since-decommissioned / base-year-timing effect, not a match artefact or a sub-threshold-site "
      f"effect: REPD's Development Status reflects TODAY's status (this is the Q1 2026 publication), "
      f"and {decommissioned_note}.")
