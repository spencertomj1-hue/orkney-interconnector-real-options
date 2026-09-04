import numpy as np, pandas as pd, glob, os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))   # .../Coding
MIDAS = os.path.join(REPO_ROOT, "Inputs", "Data", "Generation", "RawWindData") + os.sep
Z0, Z_REF, Z_HUB = 0.03, 10.0, 80.0

def load_midas(path):
    with open(path) as fh:
        lines = fh.readlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "data")
    df = pd.read_csv(path, skiprows=start + 1, low_memory=False)
    df = df[df["ob_time"].notna() & (df["ob_time"] != "end data")]
    df["ob_time"] = pd.to_datetime(df["ob_time"], errors="coerce")
    return df.dropna(subset=["ob_time"])[["ob_time", "wind_speed", "wind_speed_unit_id"]]

files = sorted(glob.glob(MIDAS + "*kirkwall*.csv"))
mid = pd.concat([load_midas(f) for f in files], ignore_index=True)

# unit check: 0/1 = m/s, 3/4 = knots
print("unit ids:", mid.wind_speed_unit_id.value_counts().to_dict())
kn = mid.wind_speed_unit_id.isin([3, 4])
mid["v10"] = np.where(kn, mid.wind_speed * 0.5144, mid.wind_speed)

mid = mid.dropna(subset=["v10"]).sort_values("ob_time")
mid = mid.drop_duplicates("ob_time")

scale = np.log(Z_HUB / Z0) / np.log(Z_REF / Z0)   # log law, 10 m -> 80 m
v_midas = mid["v10"].to_numpy() * scale

print(f"n = {len(v_midas)}  years {mid.ob_time.dt.year.min()}-{mid.ob_time.dt.year.max()}")
print(f"10 m mean {mid.v10.mean():.2f} m/s   {Z_HUB:.0f} m mean {v_midas.mean():.2f} m/s "
      f"(scale {scale:.3f})")
print("hub P10/50/90/99:", np.percentile(v_midas, [10, 50, 90, 99]).round(2))

np.save(MIDAS + "v_midas_hub80.npy", v_midas)