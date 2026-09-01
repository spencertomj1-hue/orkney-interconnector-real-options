# Demand shape construction: see docs/notes/Inputs/Data_Processing/CF/Hourly_For_CF.md#building-the-annual-demand-shape

import numpy as np
import pandas as pd
from pathlib import Path

CSV = Path("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
           "Forecasting - Week 1/Data/Demand.csv")
OUT = Path("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
           "Methodology_4/Coding/Inputs/Data/Demand/dem_shape")
OUT.mkdir(exist_ok=True)

YEARS = [2012, 2013, 2014, 2016, 2017]   # 2015 (no Nov-Dec) and 2018 (~1 month total) dropped, near-total gaps
GAP_MIN, SPAN_OK, MIN_COVER = 20, "23h", 0.75

df = pd.read_csv(CSV, usecols=["time", "Total"])
df["time"] = pd.to_datetime(df["time"], format="ISO8601", utc=True).dt.tz_localize(None)
df["Total"] = pd.to_numeric(df["Total"], errors="coerce")
df.loc[df["Total"] < 0, "Total"] = np.nan   # 218/4.29M rows, meter glitches not real demand
df = df.dropna(subset=["Total"]).sort_values("time").set_index("time")


def day_good(g):
    if len(g) < 2:
        return False
    span_ok = (g.index[-1] - g.index[0]) >= pd.Timedelta(SPAN_OK)
    gap_ok = g.index.to_series().diff().dt.total_seconds().div(60).max() <= GAP_MIN
    return span_ok and gap_ok


for YEAR in YEARS:
    d = df.loc[f"{YEAR}-01-01":f"{YEAR}-12-31"].copy()

    dt_h = d.index.to_series().diff().dt.total_seconds().div(3600).shift(-1)
    dt_h = dt_h.fillna(dt_h.median()).clip(upper=GAP_MIN / 60)
    d["E_MWh"] = d["Total"] * dt_h
    d["dt_h"] = dt_h

    good_day = d["Total"].groupby(d.index.normalize()).apply(day_good)
    d = d[d.index.normalize().map(good_day).fillna(False).to_numpy()]

    idx = pd.date_range(f"{YEAR}-01-01 00:00", f"{YEAR}-12-31 23:00", freq="h")
    idx = idx[~((idx.month == 2) & (idx.day == 29))]   # drop leap day -> 8760

    hourly = pd.DataFrame(index=idx)
    hourly["E_MWh"] = d["E_MWh"].resample("h").sum().reindex(idx)
    hourly["cover"] = d["dt_h"].resample("h").sum().reindex(idx).fillna(0.0)
    hourly.loc[hourly["cover"] < MIN_COVER, "E_MWh"] = np.nan

    hourly["month"] = hourly.index.month
    hourly["hod"] = hourly.index.hour
    clim = hourly.groupby(["month", "hod"])["E_MWh"].mean()
    fill = hourly.set_index(["month", "hod"]).index.map(clim)
    hourly["E_filled"] = hourly["E_MWh"].fillna(pd.Series(fill, index=hourly.index))
    if hourly["E_filled"].isna().any():
        hourly["E_filled"] = hourly["E_filled"].fillna(hourly["E_MWh"].mean())

    shape = (hourly["E_filled"] / hourly["E_filled"].sum()).to_numpy(dtype=float)

    n_missing = int(hourly["E_MWh"].isna().sum())
    assert len(shape) == 8760, f"{YEAR}: expected 8760 hours, got {len(shape)}"
    assert np.isclose(shape.sum(), 1.0), f"{YEAR}: shape sums to {shape.sum():.6f}"
    assert (shape > 0).all(), f"{YEAR}: non-positive hours present"

    np.save(OUT / f"dem_shape_{YEAR}.npy", shape)
    print(f"{YEAR}: {8760 - n_missing}/8760 hours measured, "
          f"peak/min ratio {shape.max()/shape.min():.2f}, saved")
