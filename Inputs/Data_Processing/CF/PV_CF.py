# Renewables.ninja hourly PV CF, Orkney 2019.
# Point 58.983, -2.960 | MERRA-2 | fixed, tilt 35, azimuth 180 | 10% system loss | 1 kW

import numpy as np
import pandas as pd
from pathlib import Path

PATH = Path("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
            "Methodology_4/Coding/Inputs/Data/CF/Ninja_PV_CF.csv")

MEASURED_CF = 0.100   # 2019 Orkney PV, regional renewable statistics


def _find_header_row(path, max_scan=10):
    with open(path, "r") as f:
        for i, line in enumerate(f):
            if i >= max_scan:
                break
            first_field = line.split(",", 1)[0].strip().strip('"').lower()
            if first_field == "time":
                return i
    raise ValueError(f"No header row starting with 'time' found in first {max_scan} lines")


def load_pv_cf(path=PATH):
    df = pd.read_csv(path, skiprows=_find_header_row(path))

    tcol = next(c for c in df.columns if "time" in c.lower())
    ecol = next(c for c in df.columns
                if any(k in c.lower() for k in ("electricity", "output", "power", "cf")))

    df[tcol] = pd.to_datetime(df[tcol])
    df = df.set_index(tcol).sort_index().rename(columns={ecol: "cf"})
    cf = df["cf"].to_numpy(dtype=float)

    if len(cf) != 8760:
        raise ValueError(f"Expected 8760 hours, got {len(cf)}")
    if np.isnan(cf).any():
        raise ValueError(f"{np.isnan(cf).sum()} NaNs in CF series")
    if cf.min() < 0 or cf.max() > 1.001:
        raise ValueError(f"CF outside [0,1]: {cf.min():.3f} to {cf.max():.3f}. "
                         "Capacity probably not 1 kW.")
    return cf, df


PV_CF = None

if __name__ == "__main__":
    PV_CF, df = load_pv_cf()

    print(f"Hours            : {len(PV_CF)}")
    print(f"Mean CF          : {PV_CF.mean():.3f}")
    print(f"Measured 2019 CF : {MEASURED_CF:.3f}")
    print(f"Ratio            : {PV_CF.mean()/MEASURED_CF:.2f}x")
    print(f"Max CF           : {PV_CF.max():.3f}")
    print(f"Zero hours       : {(PV_CF < 0.001).sum()}  (expect ~4000, night)")

    print("\nMonthly mean CF:")
    print(df["cf"].resample("ME").mean().round(3).to_string())

    print("\nMean CF by hour of day:")
    print(df["cf"].groupby(df.index.hour).mean().round(3).to_string())

    np.save(PATH.parent / "pv_cf_2019.npy", PV_CF)
    print(f"\nSaved -> {PATH.parent / 'pv_cf_2019.npy'}")
else:
    PV_CF, _ = load_pv_cf()