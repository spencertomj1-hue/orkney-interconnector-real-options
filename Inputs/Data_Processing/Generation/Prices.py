"""DESNZ Energy and Emissions Projections, Annex M -- growth assumptions and
prices. Wholesale electricity (baseload), p/kWh real 2023 prices -> GBP/MWh.
Variants are fossil-fuel-price sensitivities: FFP_Low/Reference/FFP_High.
Baseload is the standard reference against which wind capture rates are
quoted, so CAPTURE converts it to what an Orkney wind farm actually earns."""

import numpy as np
import pandas as pd

PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
        "Methodology_4/Coding/Inputs/Data/Energy_Prices.ods")

CAPTURE = 0.85          # wind capture rate vs baseload (cannibalisation)
SHEETS = {"Low": "FFP_Low", "Central": "Reference", "High": "FFP_High"}

METRIC, FUEL = "Price - Wholesale", "Electricity (baseload)"
HDR_ROW, FIRST_COL = 2, 5


def load_prices(path=PATH):
    """DataFrame indexed by year, cols Low/Central/High, GBP/MWh real 2023."""
    out = {}
    for label, sheet in SHEETS.items():
        d = pd.read_excel(path, sheet_name=sheet, engine="odf", header=None)
        years = pd.to_numeric(d.iloc[HDR_ROW, FIRST_COL:], errors="coerce")

        row = d[(d[0] == METRIC) & (d[2] == FUEL)]
        if row.empty:
            raise ValueError(f"'{FUEL}' not found in sheet {sheet}")

        vals = pd.to_numeric(row.iloc[0, FIRST_COL:], errors="coerce") * 10.0
        s = pd.Series(vals.values, index=years.values).dropna()
        s.index = s.index.astype(int)
        out[label] = s

    t = pd.DataFrame(out)
    t.index.name = "year"
    return t * CAPTURE


PRICES = load_prices()

# scenario -> fossil fuel price variant
PRICE_MAP = {
    "Base":                "Central",
    "Falling Behind":      "High",     # weak decarb -> gas on margin -> higher
    "Hydrogen Evolution":  "Central",
    "Holistic Transition": "Central",
    "Electric Engagement": "Low",      # strong decarb -> gas displaced -> lower
}


def price_series(scenario, years):
    """np.array of GBP/MWh for the given years, held flat beyond the table."""
    col = PRICES[PRICE_MAP.get(scenario, "Central")]
    last = col.iloc[-1]
    return np.array([col.get(y, last) for y in years], dtype=float)


if __name__ == "__main__":
    print(f"years {PRICES.index.min()}-{PRICES.index.max()}, CAPTURE={CAPTURE}\n")
    print("captured price, GBP/MWh real 2023:")
    print(PRICES.loc[[2019, 2028, 2030, 2035, 2040, 2050]].round(1).to_string())
    print(f"\nCfD strike (2012 prices, unconverted): 39.65 GBP/MWh")