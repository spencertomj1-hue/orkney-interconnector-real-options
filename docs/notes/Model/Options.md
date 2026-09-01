# Options.py — notes

Background, citations, and rationale pulled out of `Model/Options.py` to keep
the module itself short. Short inline citation tags (e.g. `# [1] Table
A3.3`) stay in the code next to the number they justify; this file holds the
full references and any longer design rationale.

## References

[1] Ofgem (2019). Decision: conditional approval of the SWW Final Needs Case for the Orkney electricity transmission project. Letter to all interested parties, 16 September 2019. Office of Gas and Electricity Markets, London. Available at: https://www.ofgem.gov.uk/sites/default/files/docs/2019/09/conditional_decision_on_orkney_final_needs_case_2.pdf

[2] DNV GL (2018). Orkney Project – Final Needs Case Assessment: A report for Ofgem. Doc. No. 10097585, 22 October 2018. DNV GL Limited, London. Available at: https://www.ofgem.gov.uk/sites/default/files/docs/2018/12/dnv_gl_orkney_assessment.pdf

[3] SSEN Transmission (2019). Operational Expenditure Business Plan Justification Paper (RIIO-T2), Doc. Ref. T2BP-EJP-0014, rev v3, 8 December 2019. Available at: https://www.ssen-transmission.co.uk/globalassets/documents/engineering-justification-papers/operational-expenditure-justification-paper.pdf

[4] Scottish Hydro Electric Transmission plc (2020). Directors' Report and Financial Statements, year ended 31 March 2020 (signed 25 August 2020), Strategic Report KPI table, p.2. Available at: https://www.sse.com/media/gpqf2knh/shet-plc-march-2020-financial-statements.pdf

[5] Graça Gomes, J., Cardin, M.-A., Wu, B. (2025). Strategic real options and flexibility analysis for solar PV power plants. IET Powering Net Zero (PNZ 2025), Glasgow, UK.

## Stage 2 wind: CfD lifetime assumption

Shares CFD_STRIKE (System_Model, 39.65) — unverified for Stage 2, later CfD
round likely different. 15yr lifetime VERIFIED as the standard CfD term
through Allocation Round 6; AR7 (Aug 2025) extended new awards to 20yr but
postdates this project's 2018 needs case.

## Staged interconnector: design rationale

Splits the single 220MW `NewLink` into N stages, each priced
`fixed_per_stage + variable_permw*MW`, with a learning-curve discount on
`variable_permw` for later stages. `fixed_per_stage` stays flat every stage —
no economies of scale from splitting one contract into several. This is the
phased-deployment design alternative [5] evaluates against a single
fixed-capacity build for PV, applied here to transmission capacity.

## Staged interconnector: fixed cost per stage (uncalibrated)

UNCALIBRATED: `fixed_per_stage` should be a later phase's capacity-
independent mobilisation cost when reusing stage 1's route/consent, not a
full new project's. No real precedent found (checked Table A3.3, SSEN's 2024
Orkney-Caithness contract, generic HVDC benchmarks — the real project isn't
staged). Set to ~1/5 of `Extra_Link`'s £110m fixed cost (which prices a
wholly separate circuit, so an upper bound) — swept rather than guessed
harder, see `STAGED_LINK_FIXED_PER_STAGE_SWEEP`.

## stage_variable_permw: cost formula

£/MW for stage `stage_index` (1-indexed). Stage 1 always pays `base_permw`
un-discounted — learning only applies to later stages.

- `mode='scalar'`: `variable_permw(n) = base_permw * f**(n-1)`, `f=learning_param<1`.
- `mode='wright'`: Wright's law on cumulative MW built before this stage —
  `variable_permw(n) = base_permw * (cum_mw_before_stage/MW0)**(-b)`,
  `b = -log2(1-LR)`, `LR=learning_param`, `MW0=stage_sizes[0]`.

## StagedLinkStage: capex_mult semantics

One stage of a staged (multi-block) interconnector build. Same read
interface as `NewLink`/`Extra_Link`. `capex_mult` is the REALISED multiplier
for THIS stage — for the rule-based strategy this comes from
`System_Model.sample_capex_estimate_seq` at the stage's own build year, not
a single project-wide draw like `NewLink`/`Extra_Link` use.
