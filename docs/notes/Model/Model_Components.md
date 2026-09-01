# Model_Components.py — notes

Background and rationale pulled out of `Model/Model_Components.py` to keep the
module itself short. Short inline comments stay in the code; this file holds
the longer explanations, in source order.

## Existing link OpEx: estimation method

Existing link (2x33kV subsea, Thurso GSP) annual OpEx — ESTIMATE, not a
published SHEPD/Ofgem actual (none exists for these specific cables). See
`orkney_link_data.md` (sourcing table) and `orkney_link_opex.py` (derivation,
every input tagged SOURCED/PROXY/ASSUMED/PLACEHOLDER) for the full picture.
Computed live from that module rather than pasted as a bare literal, so it
can't silently drift out of sync with its own derivation.

Method B (bottom-up: conductor losses + Method A's %-of-capex fixed-O&M
proxy + an annualised fault-repair provision), at the SOURCED (if stale,
2017) base throughput and the £70/MWh MIDPOINT of the ASSUMED £60-80/MWh
loss-price range — one specific point picked from a range/sensitivity table
that `orkney_link_opex.py` itself presents unresolved; re-run that file
directly to see the £60/£80 ends and the 120/160 GWh/yr alternatives.

CAVEAT, flagged loudly (do not treat this as more solid than it is): the
fault-repair provision is the LARGEST single component of this total (~58%
of it) and is a completely UNSOURCED PLACEHOLDER (illustrative fault-rate
and per-fault-cost assumptions, not researched figures) — this whole
constant is a rough placeholder pending real reliability data, not a
verified actual, and is disproportionately sensitive to that one unsourced
input.

## Existing wind fleet: REPD vintages

REPD (`REPD_Existing_Wind_Vintages.py`): 8 real commission years, 2000-2014
— retirement staggered (2025-2039), not a single 2035 cliff. Real ~39.2MW
total vs old 52.239MW regional-stats figure: ~25% gap is real pre-2019
decommissioning (Spurness Wind Farm, checked in `spurness_2019_check.py`),
not rescaled. REPD has no Orkney solar rows, so `Existing_PV` keeps its
placeholder year.

## EXISTING_FLEET_NAMEPLATE: purpose

Original nameplate by type, regardless of vintage/lifetime — lets
`System_Model`'s DFES block permanently remove the existing fleet from
background without a separately hardcoded figure (see
`background_retirement_scale.py`).
