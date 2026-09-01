# DFES_Gen.py — notes

Background pulled out of `Inputs/Data_Processing/Generation/DFES_Gen.py` to keep the module itself short.

## Overview

DFES 2025 (SHEPD) Orkney generation capacity, MW per year per scenario.

Background buildout only — the uncontrolled environment. Excludes backup
plant, storage, and any capacity modelled as a Decision in `System_Model`.

## Why backup plant and storage are excluded

Backup / standby plant is not export generation — it does not run
continuously and does not compete for link capacity. Including it
manufactures curtailment. Battery storage sits in the Generation category
but is absorption, not supply; it is handled separately alongside
electrolysis.

## Sourcing WIND_OPERATIONAL

`WIND_OPERATIONAL` (Orkney operational onshore wind, MW) should be SET FROM
A REAL SOURCE — the DESNZ Renewable Energy Planning Database, or SSEN's
connected generation register. DFES cannot supply this: its 2026 onshore
wind figure differs by scenario (119.3 vs 54.5 MW), so the "2026" figure
already contains pipeline projects, not just operational plant.
