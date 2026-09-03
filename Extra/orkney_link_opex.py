# Estimates annual OpEx of the EXISTING Orkney-mainland link. No published
# standalone OpEx figure exists for these cables, so this is built from
# proxies and explicit assumptions, not a sourced actual -- every constant
# below is tagged SOURCED/PROXY/ASSUMED/PLACEHOLDER in its own comment.
# Two independent methods, deliberately NOT reconciled to agree with each
# other -- disagreement between them is informative, not a bug to fix:
# Method A is a scaled-fixed-O&M-only proxy (fast, but structurally excludes
# electrical losses); Method B is bottom-up (conductor I^2*R losses + the same
# fixed-O&M proxy + an annualised fault-repair provision).

import math

# =============================================================================
# INPUTS -- every constant tagged with its provenance. See orkney_link_data.md
# for the full sourcing table; this section only restates the numbers used.
# =============================================================================

# ---- SOURCED ----------------------------------------------------------------
N_CABLES = 2                        # SOURCED: Ofgem Orkney Final Needs Case (2018) para 2.5; UK Parliament written evidence
LENGTH_KM_PER_CABLE = 37.0          # SOURCED for cable 1 (SSEN Pentland Firth East, 2020); ASSUMED similar for cable 2 (unconfirmed)
VOLTAGE_V = 33_000                  # SOURCED: 33kV (Ofgem, ICNZ, SSEN, multiple)
TOTAL_CAPACITY_MW = 40.0            # SOURCED: Ofgem Final Needs Case; ICNZ Orkney profile -- BOTH cables combined
ANNUAL_THROUGHPUT_GWH_BASE = 82.0   # SOURCED but STALE: OREF (oref.co.uk/grid) 2017 -- export 77 GWh + import 4.7 GWh. Generation has grown since; treat as a CONSERVATIVE FLOOR, not a current estimate.
CAPEX_PER_CABLE_GBP = 30e6          # SOURCED: SSEN Pentland Firth East (2020) replacement cost, £30m for 37km -- a REPLACEMENT cost anchor, not the original 1982/1998 build cost
OPEX_PCT_PROXY = 0.0034             # PROXY: Ofgem Orkney Final Needs Case para 3.23 -- £0.9m/yr on £263m capex = 0.34%/yr. This is the NEW 220MW HVAC link's approved opex rate, EXCLUDES electrical losses, and is a TRANSMISSION (not distribution) figure -- applying it to a 1980s/90s 33kV distribution cable is a proxy of convenience, not a like-for-like benchmark.

# ---- PROXY / UNVERIFIED -------------------------------------------------
RESISTANCE_OHM_PER_KM = 0.099       # PROXY, UNVERIFIED: "standard cable tables", Cu 185mm^2 @90C conductor temp -- orkney_link_data.md flags this explicitly: "VERIFY against a cited datasheet; recompute at operating temp". The 185mm^2 Cu/XLPE spec itself is a PROXY (SHEPD Orkney-Hoy replacement project spec), not confirmed for these two specific mainland cables.

# ---- ASSUMED (flagged in the source table) ----------------------------
POWER_FACTOR = 0.95                 # ASSUMED (source table: "assumption, flag")
LOSS_PRICE_GBP_PER_MWH_RANGE = [60, 70, 80]   # ASSUMED range (source table: "user to set; run both ends") -- 70 added as a midpoint for the base-case printout, not in the original range

# ---- ASSUMED here, NOT in the source table (needed to run the physics) ---
# The source table gives TOTAL capacity (40MW, both cables) but Method B's
# per-cable current calc needs a PER-CABLE peak load -- split evenly, an
# assumption this script adds, not one carried from orkney_link_data.md.
CAPACITY_MW_PER_CABLE = TOTAL_CAPACITY_MW / N_CABLES   # ASSUMED (this script, not the source table): equal 20/20 MW split between the two cables

# ---- PLACEHOLDER, UNSOURCED (fault provision) ---------------------------
# No source anywhere covers subsea fault frequency or repair cost for these
# cables -- both numbers below are illustrative placeholders only, needed to
# give the fault-provision line SOME value rather than silently omitting it.
FAULT_RATE_PER_KM_YR = 0.01         # PLACEHOLDER, UNSOURCED -- illustrative ~1 fault per 100 cable-km per year. Not sourced to any SHEPD/Ofgem RIIO-ED2 reliability report.
COST_PER_FAULT_GBP = 750_000        # PLACEHOLDER, UNSOURCED -- illustrative subsea repair cost (specialist cable-repair vessel mobilisation, jointing, ROV survey). Real subsea repairs are reported anywhere from ~£0.5m to several £m depending on depth/weather/vessel availability -- this is a single illustrative point estimate, not a distribution.

HOURS_PER_YEAR = 8760


# =============================================================================
# METHOD A -- scaled fixed O&M (fast, excludes losses by construction)
# =============================================================================
def method_a_fixed_opex():
    proxy_capex_both_cables = CAPEX_PER_CABLE_GBP * N_CABLES   # SOURCED anchor x 2 cables
    fixed_opex = OPEX_PCT_PROXY * proxy_capex_both_cables       # PROXY rate x proxy capex basis
    return proxy_capex_both_cables, fixed_opex


# =============================================================================
# METHOD B -- bottom-up: losses + fixed O&M (reuses Method A) + fault provision
# =============================================================================
def peak_current_per_cable_amps(capacity_mw_per_cable, voltage_v=VOLTAGE_V, pf=POWER_FACTOR):
    # I = P / (sqrt(3) * V * pf), 3-phase
    return (capacity_mw_per_cable * 1e6) / (math.sqrt(3) * voltage_v * pf)


def peak_loss_per_cable_w(current_a, resistance_ohm_per_km=RESISTANCE_OHM_PER_KM,
                           length_km=LENGTH_KM_PER_CABLE):
    # P_loss = 3 * I^2 * R * length (3-phase conductor I^2R loss)
    return 3 * current_a ** 2 * resistance_ohm_per_km * length_km


def load_factor(throughput_gwh, total_capacity_mw=TOTAL_CAPACITY_MW):
    throughput_mwh = throughput_gwh * 1000
    return throughput_mwh / (total_capacity_mw * HOURS_PER_YEAR)


def loss_factor_from_lf(lf):
    # loss_factor ~= 0.3*LF + 0.7*LF^2 -- standard approximation used when
    # only average load (via throughput) is known, not a full load-duration curve.
    return 0.3 * lf + 0.7 * lf ** 2


def annual_loss_energy_mwh(peak_loss_w_total, lf_loss_factor):
    peak_loss_mw_total = peak_loss_w_total / 1e6
    return peak_loss_mw_total * HOURS_PER_YEAR * lf_loss_factor


def annualised_fault_provision(total_length_km=LENGTH_KM_PER_CABLE * N_CABLES,
                                fault_rate_per_km_yr=FAULT_RATE_PER_KM_YR,
                                cost_per_fault=COST_PER_FAULT_GBP):
    expected_faults_per_year = fault_rate_per_km_yr * total_length_km
    return expected_faults_per_year * cost_per_fault


def method_b_total(throughput_gwh, price_per_mwh, fixed_opex):
    i_peak = peak_current_per_cable_amps(CAPACITY_MW_PER_CABLE)
    p_loss_per_cable_w = peak_loss_per_cable_w(i_peak)
    p_loss_total_w = p_loss_per_cable_w * N_CABLES   # both cables, symmetric loading assumed
    lf = load_factor(throughput_gwh)
    lfac = loss_factor_from_lf(lf)
    loss_energy_mwh = annual_loss_energy_mwh(p_loss_total_w, lfac)
    loss_cost = loss_energy_mwh * price_per_mwh
    fault_provision = annualised_fault_provision()
    total = loss_cost + fixed_opex + fault_provision
    return {
        "i_peak_a": i_peak, "p_loss_per_cable_w": p_loss_per_cable_w,
        "p_loss_total_w": p_loss_total_w, "load_factor": lf, "loss_factor": lfac,
        "loss_energy_mwh": loss_energy_mwh, "loss_cost": loss_cost,
        "fixed_opex": fixed_opex, "fault_provision": fault_provision, "total": total,
    }


def fmt_gbp(x):
    return f"£{x:,.0f}"


if __name__ == "__main__":
    print("=" * 78)
    print("Orkney existing link (2x33kV subsea, Thurso GSP) -- OpEx estimate")
    print("ESTIMATE ONLY -- no published standalone OpEx figure exists for these")
    print("cables. See orkney_link_data.md for full sourcing. Tags below:")
    print("  [SOURCED]=cited figure  [PROXY]=borrowed from a different asset")
    print("  [ASSUMED]=stated assumption  [PLACEHOLDER]=unsourced illustrative value")
    print("=" * 78)

    print("\n--- Method A: scaled fixed O&M -----------------------------------------")
    proxy_capex_both, fixed_opex = method_a_fixed_opex()
    print(f"  proxy_capex_both_cables [SOURCED anchor]      = {fmt_gbp(proxy_capex_both)}  "
          f"({N_CABLES} x {fmt_gbp(CAPEX_PER_CABLE_GBP)}/cable)")
    print(f"  opex_pct [PROXY, transmission, excl. losses]  = {OPEX_PCT_PROXY:.2%}/yr")
    print(f"  Method A fixed O&M (LOSSES NOT INCLUDED)      = {fmt_gbp(fixed_opex)}/yr")

    print("\n--- Method B: bottom-up, intermediate values ---------------------------")
    print(f"  per-cable peak capacity [ASSUMED 50/50 split] = {CAPACITY_MW_PER_CABLE:.1f} MW")
    i_peak = peak_current_per_cable_amps(CAPACITY_MW_PER_CABLE)
    p_loss_cable = peak_loss_per_cable_w(i_peak)
    print(f"  I_peak per cable [derived]                    = {i_peak:.1f} A")
    print(f"  P_loss per cable at peak [derived, R UNVERIFIED] = {p_loss_cable/1e6:.3f} MW")
    print(f"  P_loss total (both cables) at peak [derived]  = {p_loss_cable * N_CABLES/1e6:.3f} MW")
    lf_base = load_factor(ANNUAL_THROUGHPUT_GWH_BASE)
    lfac_base = loss_factor_from_lf(lf_base)
    print(f"  Load factor LF (throughput={ANNUAL_THROUGHPUT_GWH_BASE:.0f} GWh/yr, "
          f"[SOURCED-but-STALE 2017 figure]) = {lf_base:.3f}")
    print(f"  Loss factor (0.3*LF + 0.7*LF^2) [derived]     = {lfac_base:.3f}")
    fault_prov = annualised_fault_provision()
    print(f"  Fault provision [PLACEHOLDER, UNSOURCED]      = {fmt_gbp(fault_prov)}/yr "
          f"({FAULT_RATE_PER_KM_YR:.3f} faults/km/yr x {LENGTH_KM_PER_CABLE * N_CABLES:.0f} km x "
          f"{fmt_gbp(COST_PER_FAULT_GBP)}/fault)")

    print("\n--- Method B breakdown, base throughput = "
          f"{ANNUAL_THROUGHPUT_GWH_BASE:.0f} GWh/yr [SOURCED-but-STALE], both £/MWh ends ---")
    print(f"{'£/MWh [ASSUMED]':<18}{'Losses £/yr':>14}{'Fixed O&M £/yr':>16}"
          f"{'Faults £/yr':>14}{'TOTAL £/yr':>14}")
    for price in (LOSS_PRICE_GBP_PER_MWH_RANGE[0], LOSS_PRICE_GBP_PER_MWH_RANGE[-1]):
        r = method_b_total(ANNUAL_THROUGHPUT_GWH_BASE, price, fixed_opex)
        print(f"{price:<18}{r['loss_cost']:>14,.0f}{r['fixed_opex']:>16,.0f}"
              f"{r['fault_provision']:>14,.0f}{r['total']:>14,.0f}")

    print("\n--- Method A vs Method B, side by side "
          f"(base throughput={ANNUAL_THROUGHPUT_GWH_BASE:.0f} GWh/yr) ---------------")
    print(f"  Method A (fixed O&M only, NO losses)          = {fmt_gbp(fixed_opex)}/yr")
    for price in LOSS_PRICE_GBP_PER_MWH_RANGE:
        r = method_b_total(ANNUAL_THROUGHPUT_GWH_BASE, price, fixed_opex)
        print(f"  Method B total @ £{price}/MWh losses           = {fmt_gbp(r['total'])}/yr "
              f"(losses {fmt_gbp(r['loss_cost'])} + fixed {fmt_gbp(r['fixed_opex'])} "
              f"+ faults {fmt_gbp(r['fault_provision'])})")
    print("  NOTE: Method A structurally excludes losses -- it is not a like-for-like")
    print("  comparison with Method B's total, only with Method B's own fixed-O&M line.")

    print("\n--- Sensitivity: Method B total OpEx, £/MWh x throughput (GWh/yr) -------")
    print("  Throughput 82 GWh/yr is [SOURCED-but-STALE 2017]; 120/160 are ASSUMED")
    print("  illustrative higher-growth scenarios, not independently sourced.")
    throughputs = [82, 120, 160]
    header = f"{'£/MWh \\ GWh/yr':<16}" + "".join(f"{t:>14}" for t in throughputs)
    print(header)
    for price in LOSS_PRICE_GBP_PER_MWH_RANGE:
        row = f"{price:<16}"
        for t in throughputs:
            r = method_b_total(t, price, fixed_opex)
            row += f"{fmt_gbp(r['total']):>14}"
        print(row)

    print("\n--- Headline caveats (see orkney_link_data.md for full detail) ----------")
    print("  - Granular SHEPD subsea-cable OpEx is not published; fixed O&M is a")
    print("    proxy/benchmark only, borrowed from a different (new, transmission) asset.")
    print("  - The 0.34%/yr proxy excludes losses and is a transmission, not")
    print("    distribution, figure.")
    print("  - Throughput is 2017 (STALE) -- results at 82 GWh/yr are a floor.")
    print("  - Resistance (0.099 Ohm/km) is UNVERIFIED against a cited datasheet.")
    print("  - Fault provision is an UNSOURCED PLACEHOLDER, not a researched figure.")
    print("  - Per-cable capacity split (20/20 MW) is ASSUMED by this script, not")
    print("    stated in orkney_link_data.md.")
