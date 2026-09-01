# Prices.py — notes

Background pulled out of `Inputs/Data_Processing/Generation/Prices.py` to keep the module itself short.

## Overview

DESNZ Energy and Emissions Projections, Annex M — growth assumptions and
prices. Wholesale electricity (baseload), p/kWh real 2023 prices -> GBP/MWh.

Variants are fossil-fuel-price sensitivities: `FFP_Low` / `Reference` /
`FFP_High`. Baseload is the standard reference against which wind capture
rates are quoted, so `CAPTURE` converts it to what an Orkney wind farm
actually earns.
