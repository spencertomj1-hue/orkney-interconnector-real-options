# Hourly_For_CF.py — notes

Background pulled out of `Inputs/Data_Processing/CF/Hourly_For_CF.py` to keep the module itself short.

## Building the annual demand shape

Originally `Demand_Shape.py`. Builds an 8760-hour normalised demand shape per
year, 2012-2018, from raw minute ANM data (SSEN Active Network Management,
Orkney). Uses the same method as the original single-year (2019) version,
looped over years; the leap day is dropped to match the wind library's
8760-hour convention (`Qmap.py`). Output sums to 1.0 — multiply by an annual
GWh level to get MWh per hour.
