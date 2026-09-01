# REPD_Existing_Wind_Vintages.py — notes

Background pulled out of `Inputs/Data_Processing/CF/Wind/REPD_Existing_Wind_Vintages.py` to keep the module itself short.

## Overview

Orkney operational onshore wind vintages from the DESNZ REPD (sheet `REPD`).

Extracts the real commission year (REPD's "Operational" date column) for
each currently-operational Orkney onshore wind site, groups by commission
year, and writes the result to
`Inputs/Data/Generation/orkney_existing_wind_vintages.csv` — `Model_Components.py`
reads that CSV rather than parsing REPD at import time (REPD is a 14k-row
workbook; the CSV is the one committed source of truth derived from it).
Re-run this script to regenerate the CSV if REPD updates.

Caveat printed below and left for a human to judge, not resolved here: REPD's
Development Status reflects TODAY's status (this is the Q1 2026 publication),
not a snapshot as of 2019. "Spurness Wind Farm" (11.0 MW, operational 2004)
now shows status "Decommissioned", while "Spurness Wind Farm Repowering"
(10.0 MW, operational 2012) shows "Operational" — reading this as a straight
replacement (old unit retired when the repowering commissioned in 2012), so
only the repowering is counted below. If the old unit actually ran alongside
the new one past 2019, this undercounts by 11 MW for part of the horizon;
REPD has no decommissioning-date column to check this from directly.

## REPD has no solar rows

REPD has zero Orkney rows with Technology Type "Solar Photovoltaics" (or any
solar variant) — only Wind Onshore, Battery, Hydrogen. `Existing_PV`
(1.558 MW) cannot be sourced from REPD at all; it stays on its placeholder
commission year in `Model_Components.py`, flagged there.
