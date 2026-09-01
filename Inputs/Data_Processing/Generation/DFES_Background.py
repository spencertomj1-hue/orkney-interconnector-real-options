import numpy as np
import pandas as pd
from pathlib import Path

PATH = Path("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
            "Methodology_4/Coding/Inputs/Data/DFES/dfes_generation_MW.csv")

# DFES technology -> profile key in System_Model.PROFILES
TECH_MAP = {
    "Onshore wind": "Wind",
    "Solar PV":     "PV",
    "Marine":       "Marine",
    "Hydropower":   "Wind",     # 0.011 MW, immaterial; folded in to avoid a key
}


def load_background(path=PATH):
    """Return {scenario: DataFrame indexed by year, cols = profile keys, MW}."""
    df = pd.read_csv(path, header=[0, 1], index_col=0)
    df.index = df.index.astype(int)
    df.index.name = "year"

    out = {}
    for scen in df.columns.get_level_values(0).unique():
        sub = df[scen].copy()
        sub.columns = [TECH_MAP[c] for c in sub.columns]
        out[scen] = sub.T.groupby(level=0).sum().T   # collapse mapped duplicates
    return out


BACKGROUND = load_background()

if __name__ == "__main__":
    for scen, sub in BACKGROUND.items():
        print(f"\n{scen}")
        print(sub.round(1).head(3).to_string())
        print(f"  2049 total: {sub.loc[2049].sum():.1f} MW")