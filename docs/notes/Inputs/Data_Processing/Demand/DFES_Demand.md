# DFES_Demand.py — notes

Background pulled out of `Inputs/Data_Processing/Demand/DFES_Demand.py` to keep the module itself short.

## Overview

DFES 2025 (SHEPD) Orkney demand increments, converted from technology counts
to annual energy (GWh), relative to 2026.

Output: `dfes_demand_delta_GWh.csv` — four scenario columns, 2026-2051. This
is a DELTA on the metered baseline, not total demand. The 2026 stock is
already contained in the ANM measured demand, so only increments are added.

## EV energy factors

Car factor is derived, not assumed:

- `miles/car/yr`: Orkney car vehicle-miles (DfT road traffic statistics, LA
  level, 2022-25 mean) / Orkney licensed cars (DfT VEH0105, 2026 Q1, 11,400)
  = 5,520 miles/car/yr
- `kWh/mile`: 21 kWh/100km real-world across 342 European BEVs (Bhatti et
  al., Sustainability 16(17):7529, 2024) = 0.338
- `charge eff.`: ANM measures grid-side, so gross up for charging losses

## Vehicle category multipliers

Other vehicle categories (`MULT`) are expressed as multiples of the car
factor. The LGV multiplier is INDICATIVE and unsourced — the traffic data
cannot separate LGV mileage, it only splits `cars_and_taxis` vs
`all_motor_vehicles`.

HGVs and Buses & coaches are EXCLUDED from the central case. DFES projects
288 electric HGVs and 172 electric buses on Orkney by 2040, against total
licensed fleets of ~200 and ~100 respectively (VEH0105, 2026 Q1, all fuels).
Both exceed the entire existing fleet, so the DFES local allocation does not
reflect actual Orkney stock — the same failure mode as the domestic heating
counts. Quantified as a sensitivity at the end rather than carried in the
central case.

## Heating factors

Calibrated against island-wide heating energy from the HDD model, so the
DFES unit definition cancels out:

```
N_resist * x + N_hp * (x / SPF) = total heating energy
```

## Sensitivity: HGVs and buses

A sensitivity check that reruns the EV energy calculation with HGV and bus
counts capped at their observed Orkney fleet sizes (VEH0105 2026 Q1) instead
of DFES's projected counts, using indicative, unsourced multipliers
(`CAP_MULT`) relative to the car factor. See "Vehicle category multipliers"
above for why HGVs and buses are excluded from the central case in the first
place.
