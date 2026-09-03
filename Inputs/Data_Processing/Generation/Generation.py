"""Generation cleaning -- mirrors demand pipeline conventions. Energy-from-
the-start: MW x dt integration, never mean-of-means. Valid day: span >= 23h
AND max gap <= 20 min."""

import pandas as pd
import numpy as np

PATH = "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Forecasting - Week 1/Data/Generation.csv"
OUT_DAILY = "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Forecasting - Week 1/Data/generation_daily_clean.csv"
OUT_ANNUAL = "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Forecasting - Week 1/Data/generation_annual_clean.csv"

MIN_SPAN_HOURS = 23
MAX_GAP_MIN = 20
MIN_VALID_DAYS_FRAC = 0.90   # annual coverage threshold — match whatever you used for demand

# ---------- load ----------
df = pd.read_csv(PATH, usecols=["time", "Total"])
time_col = "time"
gen_col = "Total"
print("Columns found:", list(df.columns))

df = df[[time_col, gen_col]].rename(columns={time_col: "ts", gen_col: "gen_mw"})
df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
df["gen_mw"] = pd.to_numeric(df["gen_mw"], errors="coerce")
df = df.dropna().sort_values("ts").drop_duplicates(subset="ts").reset_index(drop=True)

# ---------- daily energy + validity ----------
df["date"] = df["ts"].dt.date

def process_day(g):
    ts = g["ts"]
    span_h = (ts.iloc[-1] - ts.iloc[0]).total_seconds() / 3600
    gaps = ts.diff().dt.total_seconds().div(60)          # minutes
    max_gap = gaps.max() if len(g) > 1 else np.inf
    # energy: MW x dt (forward difference), MWh
    dt_h = ts.diff().shift(-1).dt.total_seconds().div(3600)
    energy = (g["gen_mw"] * dt_h).sum()
    valid = (span_h >= MIN_SPAN_HOURS) and (max_gap <= MAX_GAP_MIN)
    return pd.Series({
        "energy_mwh": energy,
        "span_h": span_h,
        "max_gap_min": max_gap,
        "n_obs": len(g),
        "valid": valid,
    })

daily = df.groupby("date").apply(process_day).reset_index()
daily["date"] = pd.to_datetime(daily["date"])
daily["year"] = daily["date"].dt.year

# ---------- missing-day report ----------
for yr, g in daily.groupby("year"):
    days_in_year = 366 if pd.Timestamp(yr, 12, 31).is_leap_year else 365
    present = len(g)
    valid = g["valid"].sum()
    print(f"{yr}: {present}/{days_in_year} days present, "
          f"{valid} valid ({valid/days_in_year:.1%} coverage), "
          f"{days_in_year - present} entirely missing, "
          f"{present - valid} present-but-invalid")

# ---------- annual totals (valid days only, scaled? NO — flag instead) ----------
annual = (daily[daily["valid"]]
          .groupby("year")
          .agg(energy_mwh=("energy_mwh", "sum"),
               valid_days=("valid", "sum"))
          .reset_index())
annual["days_in_year"] = annual["year"].apply(
    lambda y: 366 if pd.Timestamp(y, 12, 31).is_leap_year else 365)
annual["coverage"] = annual["valid_days"] / annual["days_in_year"]
annual["status"] = np.where(annual["coverage"] >= MIN_VALID_DAYS_FRAC, "complete", "incomplete")

print("\n", annual.to_string(index=False))

daily.to_csv(OUT_DAILY, index=False)
annual.to_csv(OUT_ANNUAL, index=False)
print(f"\nSaved:\n  {OUT_DAILY}\n  {OUT_ANNUAL}")

# ================= PLOTTING — paste at end =================
import matplotlib.pyplot as plt

# ---- 1. Daily generation energy, valid vs invalid ----
fig, ax = plt.subplots(figsize=(14, 5))
v = daily[daily["valid"]]
iv = daily[~daily["valid"]]
ax.plot(v["date"], v["energy_mwh"], ".", ms=2, color="tab:blue", label="Valid days")
ax.plot(iv["date"], iv["energy_mwh"], ".", ms=2, color="tab:red", label="Invalid days")
ax.set_xlabel("Date")
ax.set_ylabel("Daily generation (MWh)")
ax.set_title("Daily generation energy — valid vs invalid days")
ax.legend(markerscale=6)
fig.tight_layout()

# ---- 2. Annual totals, coloured by status ----
fig, ax = plt.subplots(figsize=(10, 5))
colors = annual["status"].map({"complete": "tab:green", "incomplete": "tab:orange"})
ax.bar(annual["year"], annual["energy_mwh"] / 1000, color=colors)
for _, r in annual.iterrows():
    ax.text(r["year"], r["energy_mwh"] / 1000, f"{r['coverage']:.0%}",
            ha="center", va="bottom", fontsize=8)
ax.set_xlabel("Year")
ax.set_ylabel("Annual generation (GWh)")
ax.set_title("Annual generation (valid days only) — % = coverage, orange = incomplete")
fig.tight_layout()

# ---- 3. Coverage calendar: valid days per year-month heatmap ----
cal = (daily.assign(month=daily["date"].dt.month)
       .groupby(["year", "month"])["valid"].sum()
       .unstack(fill_value=0))
fig, ax = plt.subplots(figsize=(10, 6))
im = ax.imshow(cal, aspect="auto", cmap="RdYlGn", vmin=0, vmax=31)
ax.set_xticks(range(12), ["J","F","M","A","M","J","J","A","S","O","N","D"])
ax.set_yticks(range(len(cal.index)), cal.index)
ax.set_xlabel("Month")
ax.set_ylabel("Year")
ax.set_title("Valid days per month (green = full, red = missing)")
fig.colorbar(im, label="Valid days")
fig.tight_layout()

plt.show()