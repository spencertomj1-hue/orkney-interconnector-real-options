# early_delta.py — notes

Background and rationale pulled out of `Debugging/early_delta.py` to keep the script itself short.

## Overview

Throwaway diagnostic -- NOT part of the maintained codebase.

Why does "Early" show a larger generation-retirement NPV delta (~-79m) than Baseline/Staged/Baseline+XL (~-73m) under Base? Established (not re-derived here): only the pre-existing 2019 fleet retires in-horizon (existing wind 2010+25=2035, existing PV 2015+25=2040); every strategy's own Stage 1/Stage 2 buildout survives past 2051. So the difference has to come from how each strategy's *own* generation interacts with the same physical retirement event, not from different assets retiring.

`Run_Strategy`'s returned `state` dict already carries per-year delivered energy (GWh) and total generation (MWh) -- `state["delivered"][t]` and `state["gen_total"][t]` -- so curtailed energy per year is recovered exactly as `gen_total/1000 - delivered` (an identity: `gen_h.sum() = local+surplus = local+export+(surplus-export)`, i.e. `gen_total = delivered_MWh + curtailed_MWh`). No need to instrument `System_Model.py` for that.

Built generation capacity by year/type is not in `state`, but it's fully determined by each strategy's (rigid, Decision-only) build years, so it's recomputed here with a standalone `Model_Components.Generation_Capacity` instance -- reusing the real retirement-aware `Capacity_By_Type(Year)`, not duplicating its logic.

## CFD-share mechanism: candidate explanation

Physical energy is identical between strategies (shown above), so the NPV-delta gap must be a revenue-per-MWh effect, not a volume effect. The candidate mechanism: `cfd_share` = (wind generation fraction of total) x (CFD-eligible wind capacity / total wind capacity). Stage1/Stage2's `CFD_Lifetime()` = 15 years (`Options.py`), and each strategy commissions Stage1/Stage2 in different calendar years, so "CFD-eligible" wind capacity follows a different calendar schedule per strategy. `wind_mw` (the denominator) drops when the existing 2019 fleet retires -- so the SAME retirement event changes `cfd_share` by a different amount depending on how much of each strategy's own wind is still CFD-eligible at that moment. Recomputed here in closed form (no hourly loop needed: annual generation from a fixed capacity x fixed hourly profile is capacity x `profile.sum()`, so `gen_by_tech` per year is linear in capacity) -- reusing the real `Capacity()`/`CFD_Lifetime()`/`Classification()` methods, not duplicating them.

## Full-horizon decomposition: closing the loop

Close the loop: full-horizon capex/opex/residual/revenue decomposition for both strategies (same algebraic-recovery method as `retirement_decomp.py`: capex and residual recomputed directly from Options' `Capex()`/`BuildYear()`/`Classification()`, opex recovered as `total_cost_t - capex + residual`, revenue recovered as `npv + total_cost_t` -- both exact identities, not approximations). This confirms whether the ~6m extra Early delta over Baseline is concentrated in revenue, as the CFD-share mechanism above suggests, or whether capex/opex/residual also differ.
