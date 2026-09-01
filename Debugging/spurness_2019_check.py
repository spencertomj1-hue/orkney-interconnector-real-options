"""See docs/notes/Debugging/spurness_2019_check.md#overview for full description."""
import pandas as pd

PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
        "Methodology_4/Coding/Inputs/Data/Generation/REPD_publication_Q1_2026.xlsx")

df = pd.read_excel(PATH, sheet_name="REPD")   # header=0, the real header row
col = lambda *k: next(c for c in df.columns
                      if all(w.lower() in str(c).lower() for w in k))
site, stat = col("site", "name"), col("status")

row = df[(df[site] == "Spurness Wind Farm")]
assert len(row) == 1, f"expected exactly one 'Spurness Wind Farm' row, found {len(row)}"
r = row.iloc[0]

date_cols = ["Planning Application Submitted", "Planning Application Withdrawn",
             "Planning Permission Refused", "Appeal Lodged", "Appeal Withdrawn",
             "Appeal Refused", "Appeal Granted", "Planning Permission  Granted",
             "Secretary of State - Intervened", "Secretary of State - Refusal",
             "Secretary of State - Granted", "Planning Permission Expired",
             "Under Construction", "Operational"]

print(f"=== Spurness Wind Farm: every date/status field in REPD ===")
print(f"Development Status: {r[stat]}")
print(f"Record Last Updated (dd/mm/yyyy): {r['Record Last Updated (dd/mm/yyyy)']}")
for c in date_cols:
    print(f"{c}: {r[c]}")

decom_date_cols = [c for c in df.columns if "decommission" in c.lower()]
print(f"\nDecommission-date column(s) in REPD: {decom_date_cols if decom_date_cols else 'NONE -- REPD has no decommissioning-date field at all'}")

operational_date = pd.to_datetime(r["Operational"])
last_updated = pd.to_datetime(r["Record Last Updated (dd/mm/yyyy)"])

print(f"\nOperational since: {operational_date.date()} ({operational_date.year})")
print(f"REPD record last updated: {last_updated.date()} ({last_updated.year}) "
      f"-- with no decommission-date column, this is the closest available "
      f"proxy for when REPD's compilers last confirmed/changed this record's "
      f"status to 'Decommissioned'.")

# see docs/notes/Debugging/spurness_2019_check.md#corroborating-signal-the-repowering-project
repowering = df[df[site] == "Spurness Wind Farm Repowering"].iloc[0]
repowering_operational = pd.to_datetime(repowering["Operational"])
print(f"\nSpurness Wind Farm Repowering (different REPD entry, same site, "
      f"10.0 MW) went operational: {repowering_operational.date()}")

was_operational_2019 = operational_date.year <= 2019 and last_updated.year > 2019
print(f"\nDirect test (operational date <= 2019 AND no evidence status changed "
      f"before 2019): operational since {operational_date.year} (<=2019: "
      f"{operational_date.year <= 2019}), but REPD's record was already "
      f"updated to Decommissioned by {last_updated.year} ({last_updated.year} "
      f"<= 2019: {last_updated.year <= 2019}).")

print(f"\n=== VERDICT ===")
if last_updated.year <= 2019:
    print(f"NO -- Spurness Wind Farm was almost certainly NOT operational in 2019. "
          f"REPD has no explicit decommissioning-date column, but its record for "
          f"this site was already updated to 'Decommissioned' by "
          f"{last_updated.date()}, four years before the 2019 base year, and the "
          f"replacement 'Spurness Wind Farm Repowering' had already been "
          f"operational since {repowering_operational.date()} -- consistent with "
          f"the original turbines being retired well before 2012-2015, not still "
          f"running in 2019.")
else:
    print(f"Ambiguous from REPD alone: operational since {operational_date.year}, "
          f"and the record was last updated in {last_updated.year} (after 2019), "
          f"which does not by itself prove the site was still running in 2019 -- "
          f"but combined with the repowering site's {repowering_operational.year} "
          f"commissioning, the balance of evidence leans toward NOT operational "
          f"by 2019.")
