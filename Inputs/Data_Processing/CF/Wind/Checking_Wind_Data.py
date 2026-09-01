import numpy as np, glob, os, hashlib

OUT = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
       "Methodology_4/Coding/Inputs/Data/Generation/ninja/")
AVAIL = 0.90

files = sorted(glob.glob(OUT + "wind_cf_*.npy"))
print(f"{len(files)} files found\n")

data, hashes = {}, {}
print(f"{'year':<7}{'len':>7}{'mean':>9}{'net':>9}{'max':>7}{'zeros':>8}{'nan':>6}")
for f in files:
    yr = int(os.path.basename(f)[8:12])
    cf = np.load(f)
    data[yr] = cf
    hashes[yr] = hashlib.md5(cf.tobytes()).hexdigest()
    print(f"{yr:<7}{len(cf):>7}{cf.mean():>9.4f}{cf.mean()*AVAIL:>9.4f}"
          f"{cf.max():>7.3f}{(cf == 0).sum():>8}{np.isnan(cf).sum():>6}")

means = np.array([data[y].mean() for y in sorted(data)])
yrs = np.array(sorted(data))

print(f"\nraw mean over all years : {means.mean():.4f}")
print(f"net of AVAIL={AVAIL}      : {means.mean()*AVAIL:.4f}")
print(f"inter-annual sd         : {means.std(ddof=1):.4f}  ({means.std(ddof=1)/means.mean()*100:.1f}%)")
print(f"range                   : {means.min():.4f} ({yrs[means.argmin()]}) "
      f"to {means.max():.4f} ({yrs[means.argmax()]})")

# duplicates
dupes = {}
for y, h in hashes.items():
    dupes.setdefault(h, []).append(y)
bad = [v for v in dupes.values() if len(v) > 1]
print("\nduplicate years:", bad if bad else "none")

# length check
wrong = [y for y in data if len(data[y]) != 8760]
print("wrong length   :", wrong if wrong else "none")