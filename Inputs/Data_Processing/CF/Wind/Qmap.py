import numpy as np, pandas as pd, glob, os

NINJA = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
         "Methodology_4/Coding/Inputs/Data/Generation/ninja/")
MIDAS = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
         "Methodology_4/Coding/Inputs/Data/Generation/RawWindData/")
Z0, Z_REF, Z_HUB = 0.03, 10.0, 80.0
YEARS = range(2001, 2019)          # common window, MIDAS 2001-2020 n Ninja 2000-2019

# ---- 1. MIDAS target, trimmed to common window ----------------------------
def load_midas(path):
    with open(path) as fh:
        lines = fh.readlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "data")
    df = pd.read_csv(path, skiprows=start + 1, low_memory=False)
    df = df[df["ob_time"].notna() & (df["ob_time"] != "end data")]
    df["ob_time"] = pd.to_datetime(df["ob_time"], errors="coerce")
    return df.dropna(subset=["ob_time"])[["ob_time", "wind_speed", "wind_speed_unit_id"]]

mid = pd.concat([load_midas(f) for f in sorted(glob.glob(MIDAS + "*kirkwall*.csv"))],
                ignore_index=True)
mid = mid[mid.ob_time.dt.year.isin(YEARS)].dropna(subset=["wind_speed"])
mid = mid.drop_duplicates("ob_time")
kn = mid.wind_speed_unit_id.isin([3, 4])
v_midas = np.where(kn, mid.wind_speed * 0.5144, mid.wind_speed).astype(float)
v_midas *= np.log(Z_HUB / Z0) / np.log(Z_REF / Z0)

# ---- 2. Ninja raw, same window --------------------------------------------
raw = {y: pd.read_csv(f"{NINJA}raw_{y}.csv") for y in YEARS}
probe = raw[list(YEARS)[0]]
SPD = next(c for c in probe.columns if "speed" in c.lower() or c.lower() == "wind")
print("ninja speed column:", SPD, "| all columns:", list(probe.columns))

v_ninja = np.concatenate([raw[y][SPD].to_numpy(float) for y in YEARS])
el      = np.concatenate([raw[y]["electricity"].to_numpy(float) for y in YEARS])

# ---- 3. Fit quantile map on pooled data -----------------------------------
q   = np.linspace(0, 100, 1001)
src = np.percentile(v_ninja, q)
tgt = np.percentile(v_midas, q)
qmap = lambda v: np.interp(v, src, tgt)

print(f"\nmean   ninja {v_ninja.mean():.2f}  ->  midas {v_midas.mean():.2f} m/s")
print(f"P10/50/90/99 ninja {np.percentile(v_ninja,[10,50,90,99]).round(2)}")
print(f"             midas {np.percentile(v_midas,[10,50,90,99]).round(2)}")

# ---- 4. Empirical power curve from Ninja's own speed/output pairs ----------
bins  = np.arange(0, 30.5, 0.5)
idx   = np.digitize(v_ninja, bins) - 1
curve = np.array([el[idx == i].mean() if (idx == i).sum() > 20 else np.nan
                  for i in range(len(bins) - 1)])
ok      = np.isfinite(curve)
centres = (bins[:-1] + 0.25)[ok]
curve   = curve[ok]
power = lambda v: np.clip(np.interp(v, centres, curve, left=0.0, right=curve[-1]), 0, 1)

# ---- 5. Apply per year -----------------------------------------------------
print(f"\n{'year':<7}{'raw':>9}{'corr':>9}{'zeros':>8}")
out = {}
for y in YEARS:
    v  = raw[y][SPD].to_numpy(float)
    cf = power(qmap(v))
    t  = pd.to_datetime(raw[y]["time"])
    cf = cf[(~((t.dt.month == 2) & (t.dt.day == 29))).to_numpy()]
    np.save(f"{NINJA}wind_cf_corrected_{y}.npy", cf)
    out[y] = cf
    print(f"{y:<7}{raw[y]['electricity'].mean():>9.4f}{cf.mean():>9.4f}{(cf==0).sum():>8}")

m = np.array([out[y].mean() for y in YEARS])
print(f"\ncorrected mean {m.mean():.4f}   sd {m.std(ddof=1)/m.mean()*100:.1f}%"
      f"   range {m.min():.4f}-{m.max():.4f}")