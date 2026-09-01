# Orkney–mainland existing link (2×33kV subsea): input data

"Existing Orkney link" = two 33kV subsea distribution cables connecting Orkney to
Thurso GSP on the Scottish mainland (owned/operated by SSEN's distribution arm,
SHEPD). No published standalone OpEx figure exists for these specific cables --
every OpEx number derived from this table (see `orkney_link_opex.py`) is an
estimate, not a sourced actual, and is built from proxies and stated assumptions.

| Input | Value | Source | Note |
|---|---|---|---|
| Cables | 2 × 33kV subsea | Ofgem Orkney Final Needs Case (2018), para 2.5; UK Parliament written evidence | run to Thurso GSP |
| Subsea length | ~37 km each | SSEN Pentland Firth East press release (2020); distribution.ssen.co.uk/SubmarineCables/Pentland | only the replaced cable is confirmed 37km; second cable ASSUMED similar |
| Install years | 1982 and 1998 | UK Parliament written evidence (committees.parliament.uk) | mainland pair (not the internal Hoy cables) |
| Voltage | 33 kV | multiple (Ofgem, ICNZ, SSEN) | |
| Conductor | 185mm² Cu, XLPE | SHEPD Orkney–Hoy replacement project description (marine.gov.scot) | PROXY spec; not confirmed for the two mainland cables |
| Resistance | ~0.099 Ω/km (Cu 185mm² @90°C) | standard cable tables | VERIFY against a cited datasheet; recompute at operating temp |
| Total capacity | 40 MW (both cables) | Ofgem Final Needs Case; ICNZ Orkney profile | |
| Annual throughput | ~82 GWh/yr | OREF (oref.co.uk/grid): 2017 export 77 GWh + import 4.7 GWh | 2017 figure, STALE — generation has grown; treat as conservative floor |
| Power factor | 0.95 (assumed) | assumption | flag |
| £/MWh for losses | 60–80 (assumed range) | assumption | user to set; run both ends |
| Capex anchor (per cable) | £30m for 37km | SSEN Pentland Firth East (2020) | replacement cost |
| Subsea cable reopener | £58.9m 2018/19–2022/23 | Ofgem CRC 3F decision (2019) | capex-dominated (replacements), NOT steady-state opex |
| OpEx proxy (transmission) | £0.9m/yr on £263m capex ≈ 0.34%/yr | Ofgem Orkney Final Needs Case, para 3.23 | for the NEW 220MW HVAC link; EXCLUDES electrical losses |

## Known limitations

- Granular SHEPD subsea-cable OpEx is not published; fixed O&M is a proxy/benchmark
  only.
- The 0.34%/yr proxy is a transmission (HVAC + substations) figure, not distribution.
- Throughput is 2017; results are a floor unless a newer figure is substituted.
