"""See docs/notes/Debugging/threshold_sweep.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import Model.Decision_Rules as DR
from Model.System_Model import Strategies_Flex, Scenarios, Run_Strategy

DEFAULTS = {
    "EXTRA_LINK_HOURS_THRESHOLD": DR.EXTRA_LINK_HOURS_THRESHOLD,
    "MAIN_LINK_HEADROOM_THRESHOLD": DR.MAIN_LINK_HEADROOM_THRESHOLD,
    "STAGE2_WIND_CURTAIL_THRESHOLD": DR.STAGE2_WIND_CURTAIL_THRESHOLD,
}


def run_flexible():
    opts = Strategies_Flex["Flexible 1-Stage"](1.0)
    _, _, _, npv, _, rlog = Run_Strategy(("Flexible 1-Stage", opts), Scenarios["Base"], "Base")
    return npv, rlog


def fmt(v):
    return "-" if v is None else str(v)


# ---- SWEEP 1: Extra Link ---------------------------------------------------
print("=== SWEEP 1: Extra Link threshold (EXTRA_LINK_HOURS_THRESHOLD, hours_at_cap, 'above') ===")
print(f"{'threshold':>12}{'fired':>8}{'decision_yr':>13}{'build_yr':>10}{'NPV_£m':>10}")

extra_link_values = [500, 1000, 1500, 2000, 2500, 3000, 4000, 1e9]
sweep1 = {}
for v in extra_link_values:
    DR.EXTRA_LINK_HOURS_THRESHOLD = v
    npv, rlog = run_flexible()
    info = rlog["Extra Link"]
    sweep1[v] = (info["fired"], info["decision_year"], info["build_year"], npv)
    print(f"{v:>12g}{str(info['fired']):>8}{fmt(info['decision_year']):>13}"
          f"{fmt(info['build_year']):>10}{npv/1e6:>10.2f}")

DR.EXTRA_LINK_HOURS_THRESHOLD = DEFAULTS["EXTRA_LINK_HOURS_THRESHOLD"]   # restore

never_fire_npv = sweep1[1e9][3]
firing_entries = {v: r for v, r in sweep1.items() if r[0] and v != 1e9}
print(f"\nNever-fire NPV (threshold=1e9): £{never_fire_npv/1e6:.2f}m")
if firing_entries:
    best_v = max(firing_entries, key=lambda v: firing_entries[v][3])
    best_npv = firing_entries[best_v][3]
    print(f"Best firing threshold: {best_v:g} -> NPV £{best_npv/1e6:.2f}m "
          f"({'BEATS' if best_npv > never_fire_npv else 'still below'} never-fire "
          f"by £{abs(best_npv - never_fire_npv)/1e6:.2f}m)")
else:
    print("Extra Link never fired at any swept threshold below 1e9 under Base.")

# ---- SWEEP 2: Main Link robustness -----------------------------------------
print("\n=== SWEEP 2: Main Link threshold (MAIN_LINK_HEADROOM_THRESHOLD, headroom_p90, 'above') ===")
print(f"{'threshold':>12}{'fired':>8}{'decision_yr':>13}{'build_yr':>10}{'NPV_£m':>10}")

main_link_values = [-50, -20, -10, 0, 10, 20, 50]
sweep2 = {}
for v in main_link_values:
    DR.MAIN_LINK_HEADROOM_THRESHOLD = v
    npv, rlog = run_flexible()
    info = rlog["Main Link"]
    sweep2[v] = (info["fired"], info["decision_year"], info["build_year"], npv)
    print(f"{v:>12g}{str(info['fired']):>8}{fmt(info['decision_year']):>13}"
          f"{fmt(info['build_year']):>10}{npv/1e6:>10.2f}")

DR.MAIN_LINK_HEADROOM_THRESHOLD = DEFAULTS["MAIN_LINK_HEADROOM_THRESHOLD"]   # restore

decision_years = [r[1] for r in sweep2.values() if r[0]]
fired_flags = [r[0] for r in sweep2.values()]
distinct_years = sorted(set(decision_years))
if len(distinct_years) <= 1 and all(fired_flags):
    robustness = f"ROBUST -- fires in every swept threshold, always at decision year {distinct_years[0] if distinct_years else '-'}"
elif not distinct_years:
    robustness = "never fires across the whole swept range"
else:
    robustness = f"KNIFE-EDGE -- decision year varies across the swept range: {distinct_years} (or fails to fire at some values)"
print(f"\nMain Link robustness verdict: {robustness}")

# ---- restore everything, defensively ---------------------------------------
DR.EXTRA_LINK_HOURS_THRESHOLD = DEFAULTS["EXTRA_LINK_HOURS_THRESHOLD"]
DR.MAIN_LINK_HEADROOM_THRESHOLD = DEFAULTS["MAIN_LINK_HEADROOM_THRESHOLD"]
DR.STAGE2_WIND_CURTAIL_THRESHOLD = DEFAULTS["STAGE2_WIND_CURTAIL_THRESHOLD"]

print("\n=== VERDICT ===")
if firing_entries:
    best_v = max(firing_entries, key=lambda v: firing_entries[v][3])
    best_npv = firing_entries[best_v][3]
    if best_npv > never_fire_npv:
        a_verdict = (f"(a) Extra Link IS value-adding at threshold {best_v:g} hours "
                     f"(NPV £{best_npv/1e6:.2f}m vs £{never_fire_npv/1e6:.2f}m never-firing, "
                     f"+£{(best_npv - never_fire_npv)/1e6:.2f}m).")
    else:
        a_verdict = (f"(a) Extra Link is value-destroying at every swept firing threshold under "
                     f"Base -- the best firing case (threshold {best_v:g}) still trails never-firing "
                     f"by £{(never_fire_npv - best_npv)/1e6:.2f}m.")
else:
    a_verdict = "(a) Extra Link never fired at any swept threshold below 1e9 under Base."
print(a_verdict)
print(f"(b) Main Link's fire year is {robustness.split(' -- ')[0]}"
      f"{' -- ' + robustness.split(' -- ', 1)[1] if ' -- ' in robustness else ''}. "
      + ("Trust the deterministic Base fire year." if robustness.startswith("ROBUST")
         else "Do not trust the deterministic Base fire year alone -- treat the Monte Carlo "
              "distribution of decision years as the real answer."))
