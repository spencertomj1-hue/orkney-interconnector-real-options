# Wind_CF.py — notes

Background pulled out of `Inputs/Data_Processing/CF/Wind/Wind_CF.py` to keep the module itself short.

## Wind CF data source

Originally `Wind_Profile.py`. Loads Renewables.ninja hourly wind CF for
Orkney, 2019. Point: 58.983, -2.960 | MERRA-2 | Vestas V90 2000 | 80 m hub |
1 kW capacity. Capacity is set to 1 kW so output is numerically the capacity
factor (0-1).
