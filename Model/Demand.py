import numpy as np
import pandas as pd

BASE_YEAR  = 2019
LEVEL_2019 = 141.95     # GWh, measured
TREND      = -1.55      # GWh/yr, weather-corrected 2012-2021

Years = np.arange(2019, 2052)

# baseline: structural decline from 2019
base = LEVEL_2019 + TREND * (Years - BASE_YEAR)

# DFES increments, zero before 2026
delta = pd.read_csv(
    "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding/Inputs/Data/Demand/dfes_demand_delta_GWh.csv",
    index_col="year",
).reindex(Years).fillna(0.0)

Scenarios = delta.add(base, axis=0)
Scenarios.index.name = "year"

Demand_EE = Scenarios["Electric Engagement"].to_numpy()
Demand_FB = Scenarios["Falling Behind"].to_numpy()
Demand_HT = Scenarios["Holistic Transition"].to_numpy()
Demand_HE = Scenarios["Hydrogen Evolution"].to_numpy()

