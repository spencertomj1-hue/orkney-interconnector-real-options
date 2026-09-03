"""DFES 2025 (SHEPD) Orkney demand increments, converted from technology
counts to annual energy (GWh), relative to 2026. Output is a DELTA on the
metered baseline, not total demand -- the 2026 stock is already contained in
the ANM measured demand, so only increments are added."""

import pandas as pd

PATH = "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding/Inputs/Data/DFES/2025_DFES_Projections.csv"

# Car factor is derived, not assumed: miles/car/yr = Orkney car vehicle-miles
# (DfT road traffic statistics, LA level, 2022-25 mean) / Orkney licensed cars
# (DfT VEH0105, 2026 Q1, 11,400); kWh/mile = 21 kWh/100km real-world across
# 342 European BEVs (Bhatti et al., Sustainability 16(17):7529, 2024); charge
# eff. grosses up for charging losses since ANM measures grid-side.
MILES_PER_CAR = 5520
KWH_PER_MILE  = 0.338     # sensitivity: 0.27 / 0.338 / 0.40 (paper's +/-4)
CHARGE_EFF    = 0.90

KWH_PER_CAR = MILES_PER_CAR * KWH_PER_MILE / CHARGE_EFF

# Other categories expressed as multiples of the car factor. The LGV
# multiplier is INDICATIVE and unsourced -- the traffic data can't separate
# LGV mileage, it only splits cars_and_taxis vs all_motor_vehicles. HGVs and
# buses are excluded entirely: DFES projects 288 electric HGVs and 172
# electric buses on Orkney by 2040 against total licensed fleets of only
# ~200 and ~100 respectively (VEH0105, 2026 Q1) -- both exceed the entire
# existing fleet, so DFES's local allocation doesn't reflect actual Orkney
# stock. Quantified separately as a sensitivity below instead.
MULT = {
    "Off-street cars":  1.00,
    "On-street cars":   1.00,
    "Off-street LGVs":  2.00,   # NEEDS SOURCE
    "On-street LGVs":   2.00,   # NEEDS SOURCE
    "Motorcycles":      0.15,   # negligible either way
}

# Calibrated against island-wide heating energy from the HDD model, so the
# DFES unit definition cancels out: N_resist*x + N_hp*(x/SPF) = total heating energy.
SPF_H4        = 2.78      # EoH SPF_H4 median, n=428. Sensitivity: 2.55 / 3.05
C_MWH_PER_HDD = 23.556    # own HDD model, base 13C, MWh/day per HDD
ANNUAL_HDD    = 1681      # Kirkwall, mean over full-12-month years

TOTAL_HEAT_MWH = C_MWH_PER_HDD * ANNUAL_HDD

# =============================================================================

YEARS = [str(y) for y in range(2026, 2052)]
SCEN  = "Holistic Transition"     # 2026 stock is near-identical across scenarios

df = pd.read_csv(PATH)
o = df[(df.Local_authority == "Orkney Islands") & (df.Category == "Demand")].copy()
o[YEARS] = o[YEARS].apply(pd.to_numeric, errors="coerce")


def counts(technology, subtechnology=None):
    """Unit count per scenario per year."""
    d = o[o.Technology == technology]
    if subtechnology is not None:
        d = d[d.Subtechnology == subtechnology]
    return d.groupby("Scenario")[YEARS].sum()


def increment(technology, subtechnology=None):
    """Change in unit count relative to 2026."""
    c = counts(technology, subtechnology)
    return c.sub(c["2026"], axis=0)


# --- calibrate heating -------------------------------------------------------
hp     = counts("Domestic heat pumps")
resist = counts("Domestic direct electric heating")

x = TOTAL_HEAT_MWH / (resist.loc[SCEN, "2026"] + hp.loc[SCEN, "2026"] / SPF_H4)
KWH_PER_RESIST = x * 1000
KWH_PER_HP     = KWH_PER_RESIST / SPF_H4

print("--- conversion factors (kWh per unit per year) ---")
print(f"  car            : {KWH_PER_CAR:,.0f}")
print(f"  resistive unit : {KWH_PER_RESIST:,.0f}")
print(f"  heat pump unit : {KWH_PER_HP:,.0f}")

# --- EV energy, by subtechnology ---------------------------------------------
ev_kwh = sum(increment("Electric vehicles", sub) * KWH_PER_CAR * m
             for sub, m in MULT.items())

# --- heating energy ----------------------------------------------------------
heat_kwh = (increment("Domestic heat pumps") * KWH_PER_HP
            + increment("Domestic direct electric heating") * KWH_PER_RESIST)

added = (ev_kwh + heat_kwh) / 1e6            # GWh

out = added.T
out.index.name = "year"
out.index = out.index.astype(int)

print("\n--- demand increment relative to 2026 (GWh) ---")
print(out.round(1))
out.to_csv("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding/Inputs/Data/Demand/dfes_demand_delta_GWh.csv")

# --- split: how much is EV vs heating? ---------------------------------------
print("\n--- 2040 split (GWh) ---")
split = pd.DataFrame({
    "EV":      ev_kwh["2040"] / 1e6,
    "heating": heat_kwh["2040"] / 1e6,
    "total":   added["2040"],
})
print(split.round(1).to_string())

# Reruns the EV energy calc with HGV/bus counts capped at their observed
# Orkney fleet sizes (VEH0105 2026 Q1) instead of DFES's projected counts,
# using indicative unsourced multipliers -- see the note above on why HGVs
# and buses are excluded from the central case in the first place.
FLEET_CAP = {"HGVs": 200, "Buses & coaches": 100}      # VEH0105 2026 Q1, rounded
CAP_MULT  = {"HGVs": 10.0, "Buses & coaches": 12.0}    # INDICATIVE, unsourced

excl = sum(increment("Electric vehicles", sub).clip(upper=cap)
           * KWH_PER_CAR * CAP_MULT[sub]
           for sub, cap in FLEET_CAP.items())

print("\n--- SENSITIVITY: excluded HGV/bus energy, capped at observed fleet ---")
s = pd.DataFrame({
    "central_2040": added["2040"],
    "hgv_bus_2040": excl["2040"] / 1e6,
})
s["as_%_of_central"] = (s.hgv_bus_2040 / s.central_2040 * 100).round(1)
print(s.round(1).to_string())
print("\nExcluded from the central case because DFES projects more electric HGVs")
print("and buses on Orkney by 2040 than there are vehicles of those types in")
print("total today (VEH0105). Multipliers above are indicative and unsourced.")