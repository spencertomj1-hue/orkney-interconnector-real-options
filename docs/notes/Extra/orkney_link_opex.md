# orkney_link_opex.py — notes

Background, citations, and rationale pulled out of `Extra/orkney_link_opex.py` to keep
the module itself short. Per-constant provenance tags (SOURCED/PROXY/ASSUMED/PLACEHOLDER)
stay as inline trailing comments in the code next to each constant; this file holds the
longer standalone rationale.

## Two independent OpEx estimation methods

Estimates annual OpEx of the EXISTING Orkney-mainland link (2x33kV subsea distribution
cables to Thurso GSP, owned/operated by SHEPD). No published standalone OpEx figure
exists for these cables — this is an ESTIMATE built from proxies and explicit
assumptions, not a sourced actual. All inputs are hardcoded below from
`orkney_link_data.md` (read that file first) — no external data fetch. Every constant is
tagged SOURCED / PROXY / ASSUMED / PLACEHOLDER-UNSOURCED in its own comment; nothing is
silently "improved" beyond what the source table says.

Two independent methods, deliberately NOT reconciled to agree with each other —
disagreement between them is informative, not a bug to fix:

- Method A: scaled fixed O&M only (a %-of-capex proxy borrowed from the NEW link's
  Ofgem-approved opex rate) — fast, but structurally excludes electrical losses
  entirely.
- Method B: bottom-up — conductor I²·R losses (annualised via a load-factor
  loss-factor approximation) + the SAME fixed O&M proxy + an annualised fault-repair
  provision (unsourced placeholder).

Method A's own number is fixed-O&M-only by design (see `orkney_link_data.md` note: "for
the NEW 220MW HVAC link; EXCLUDES electrical losses") — it is NOT meant to be compared
like-for-like against Method B's total without that caveat front and centre.

## Per-cable capacity split assumption

The source table gives TOTAL capacity (40MW, both cables) but Method B's per-cable
current calc needs a PER-CABLE peak load. Split evenly across the two cables — an
assumption this script adds, not one carried from `orkney_link_data.md`, so it is
flagged separately here.

## Fault provision placeholder rationale

No source anywhere in `orkney_link_data.md` covers subsea fault frequency or repair cost
for these cables — both numbers below are illustrative placeholders only, needed to give
the fault-provision line SOME value rather than silently omitting it. Do not treat these
as researched figures.
