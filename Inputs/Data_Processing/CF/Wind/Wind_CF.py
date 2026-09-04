# Loads Renewables.ninja hourly wind capacity-factor data for Orkney, 2019
# (58.983, -2.960, MERRA-2, Vestas V90 2000, 80m hub). Capacity is set to 1kW
# so the output is numerically the capacity factor (0-1).

import numpy as np
import pandas as pd
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]      # .../Coding
PATH = REPO_ROOT / "Inputs" / "Data" / "CF" / "Ninja_Wind_CF.csv"


def _find_header_row(path, max_scan=10):
    """Ninja prefixes metadata lines. Find the row whose first column is 'time'."""
    with open(path, "r") as f:
        for i, line in enumerate(f):
            if i >= max_scan:
                break
            first_field = line.split(",", 1)[0].strip().strip('"').lower()
            if first_field == "time":
                return i
    raise ValueError(f"No header row starting with 'time' found in first {max_scan} lines")


def load_wind_cf(path=PATH):
    """Return (cf array, dataframe indexed by time)."""
    df = pd.read_csv(path, skiprows=_find_header_row(path))

    # keyword-based column detection, tolerant of Numbers renaming things
    tcol = next(c for c in df.columns if "time" in c.lower())
    ecol = next(
        c for c in df.columns
        if any(k in c.lower() for k in ("electricity", "output", "power", "cf"))
    )

    df[tcol] = pd.to_datetime(df[tcol])
    df = df.set_index(tcol).sort_index()
    df = df.rename(columns={ecol: "cf"})

    cf = df["cf"].to_numpy(dtype=float)

    # --- validation -------------------------------------------------
    if len(cf) != 8760:
        raise ValueError(f"Expected 8760 hours, got {len(cf)}. Leap year or partial download?")
    if np.isnan(cf).any():
        raise ValueError(f"{np.isnan(cf).sum()} NaNs in CF series")
    if cf.min() < 0 or cf.max() > 1.001:
        raise ValueError(f"CF outside [0,1]: min={cf.min():.3f} max={cf.max():.3f}. "
                         "Capacity probably wasn't set to 1 kW.")
    return cf, df


WIND_CF = None

if __name__ == "__main__":
    WIND_CF, df = load_wind_cf()

    print(f"Hours              : {len(WIND_CF)}")
    print(f"Mean CF            : {WIND_CF.mean():.3f}")
    print(f"Measured 2019 CF   : 0.354  (regional renewable statistics)")
    print(f"Min / Max          : {WIND_CF.min():.3f} / {WIND_CF.max():.3f}")
    print(f"Hours at zero      : {(WIND_CF < 0.01).sum()}")
    print(f"Hours near rated   : {(WIND_CF > 0.99).sum()}")

    monthly = df["cf"].resample("ME").mean()
    print("\nMonthly mean CF:")
    print(monthly.round(3).to_string())

    np.save(PATH.parent / "wind_cf_2019.npy", WIND_CF)
    print(f"\nSaved -> {PATH.parent / 'wind_cf_2019.npy'}")
else:
    WIND_CF, _ = load_wind_cf()