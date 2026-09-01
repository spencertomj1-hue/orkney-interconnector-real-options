# EV_Fcator.py — notes

Background pulled out of `Inputs/Data_Processing/Demand/EV_Fcator.py` to keep the module itself short.

## Overview

Derives `KWH_PER_EV_CAR` for Orkney from published data:

```
annual miles per car = (Orkney car vehicle-miles) / (Orkney licensed cars)
kWh per car per year  = miles per car x kWh per mile
```

Sources:

- `Traffic_Volume.csv` — DfT road traffic statistics, vehicle miles by local
  authority. https://roadtraffic.dft.gov.uk/downloads
- `CARS_LICENSED` — DfT VEH0105, licensed vehicles by body type and local
  authority. FILL THIS IN - not yet sourced.
- `KWH_PER_MILE` — external assumption. Real-world BEV consumption.

Caveat: traffic counts measure miles driven on Orkney roads; licensed
vehicles measure vehicles registered in Orkney. On an island with no
through-traffic these populations align closely, but they are not identical.
