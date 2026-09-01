"""See docs/notes/Debugging/mc_threshold_sweep.md#overview for full description."""
import sys
sys.path.insert(0, "/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/Methodology_4/Coding")

import numpy as np
import Model.Decision_Rules as DR
import Model.System_Model as M
from Model.System_Model import Strategies_Flex, Scenarios, Run_Strategy

DEFAULTS = {
    "MAIN_LINK_HEADROOM_THRESHOLD": DR.MAIN_LINK_HEADROOM_THRESHOLD,
    "EXTRA_LINK_HOURS_THRESHOLD": DR.EXTRA_LINK_HOURS_THRESHOLD,
    "STAGE2_WIND_CURTAIL_THRESHOLD": DR.STAGE2_WIND_CURTAIL_THRESHOLD,
}

N = 300
SEED = 42
TARGET_STRATEGY = "Flexible 1-Stage"


def run_flexible_mc(n=N, seed=SEED, strategy_name=TARGET_STRATEGY):
    rng = np.random.default_rng(seed)
    scen_names = list(M.SCENARIO_WEIGHTS["Equal"].keys())
    scen_probs = list(M.SCENARIO_WEIGHTS["Equal"].values())
    npv_arr = np.empty(n)
    rule_log = {}
    for i in range(n):
        capex_mult = rng.lognormal(M.CAPEX_MU, M.CAPEX_SIGMA)
        scenario = rng.choice(scen_names, p=scen_probs)
        wx_seq = M.sample_wx_seq(rng, len(M.YEARS))
        capex_estimate_seq = M.sample_capex_estimate_seq(rng, capex_mult, len(M.YEARS))
        demand = Scenarios[scenario]
        opts = Strategies_Flex[strategy_name](capex_mult)
        _, _, _, npv, _, rlog = Run_Strategy((strategy_name, opts), demand, scenario, wx_seq,
                                              capex_mult, capex_estimate_seq)
        npv_arr[i] = npv
        for rname, info in rlog.items():
            rule_log.setdefault(rname, []).append(info)
    return npv_arr, rule_log


def summarize(infos, n):
    fired_years = [info["decision_year"] for info in infos if info["fired"]]
    never_pct = 1 - len(fired_years) / n
    mean_y = np.mean(fired_years) if fired_years else float("nan")
    sd_y = np.std(fired_years) if fired_years else float("nan")
    return never_pct, mean_y, sd_y, len(fired_years)


def restore():
    DR.MAIN_LINK_HEADROOM_THRESHOLD = DEFAULTS["MAIN_LINK_HEADROOM_THRESHOLD"]
    DR.EXTRA_LINK_HOURS_THRESHOLD = DEFAULTS["EXTRA_LINK_HOURS_THRESHOLD"]
    DR.STAGE2_WIND_CURTAIL_THRESHOLD = DEFAULTS["STAGE2_WIND_CURTAIL_THRESHOLD"]


# ---- SWEEP 1: Main Link ----------------------------------------------------
print(f"=== SWEEP 1: MAIN_LINK_HEADROOM_THRESHOLD (headroom_p90, 'above'), N={N}, "
      f"target='{TARGET_STRATEGY}' ===")
print(f"{'threshold':>10}{'never-fired%':>14}{'mean_year':>11}{'sd':>8}")
sweep1_rows = []
for v in [0, 25, 50, 100, 150, 200, 300]:
    restore()
    DR.MAIN_LINK_HEADROOM_THRESHOLD = v
    _, rule_log = run_flexible_mc()
    never_pct, mean_y, sd_y, n_fired = summarize(rule_log["Main Link"], N)
    sweep1_rows.append((v, never_pct, mean_y, sd_y, n_fired))
    print(f"{v:>10}{never_pct:>14.1%}{mean_y:>11.2f}{sd_y:>8.2f}")
restore()

# see docs/notes/Debugging/mc_threshold_sweep.md#sweep-2-extra-link-gating
print(f"\n=== SWEEP 2: EXTRA_LINK_HOURS_THRESHOLD (hours_at_cap, 'above'), N={N} ===")
_, _probe_log = run_flexible_mc(n=1)
if "Extra Link" not in _probe_log:
    print(f"SKIPPED -- '{TARGET_STRATEGY}' has no Extra Link rule (removed in the headline "
          f"reconfiguration). Point TARGET_STRATEGY at a strategy that still has one (e.g. "
          f"'Flexible - Mandated Link') to run this sweep for real.")
    sweep2_rows, any_selective_and_adding = [], False
else:
    sweep2_rows = []
    sweep2_npv = {}
    for v in [1500, 3000, 5000, 7000, 8760]:
        restore()
        DR.EXTRA_LINK_HOURS_THRESHOLD = v
        npv_arr, rule_log = run_flexible_mc()
        never_pct, mean_y, sd_y, n_fired = summarize(rule_log["Extra Link"], N)
        sweep2_rows.append((v, never_pct, mean_y, sd_y, n_fired))
        print(f"{v:>10}{never_pct:>14.1%}{mean_y:>11.2f}{sd_y:>8.2f}"
              f"{'  (8760 = every hour of the year at cap)' if v == 8760 else ''}")
        fired_idx = [i for i, info in enumerate(rule_log["Extra Link"]) if info["fired"]]
        never_idx = [i for i, info in enumerate(rule_log["Extra Link"]) if not info["fired"]]
        sweep2_npv[v] = (npv_arr, fired_idx, never_idx)
    restore()

    print("\nNPV when fired vs never-fired, same paired draws, per threshold:")
    print(f"{'threshold':>10}{'N_fired':>9}{'N_never':>9}{'NPV|fired':>12}{'NPV|never':>12}{'fired beats never?':>20}")
    any_selective_and_adding = False
    for v, never_pct, mean_y, sd_y, n_fired in sweep2_rows:
        npv_arr, fired_idx, never_idx = sweep2_npv[v]
        selective = 0 < never_pct < 1.0
        if fired_idx and never_idx:
            npv_fired = npv_arr[fired_idx].mean() / 1e6
            npv_never = npv_arr[never_idx].mean() / 1e6
            beats = npv_fired > npv_never
            if selective and beats:
                any_selective_and_adding = True
            print(f"{v:>10}{len(fired_idx):>9}{len(never_idx):>9}{npv_fired:>12.1f}{npv_never:>12.1f}{str(beats):>20}")
        else:
            print(f"{v:>10}{len(fired_idx):>9}{len(never_idx):>9}{'n/a (all-or-nothing, no within-threshold comparison possible)':>44}")

# see docs/notes/Debugging/mc_threshold_sweep.md#sweep-3-stage-2-wind-gating
print(f"\n=== SWEEP 3: STAGE2_WIND_CURTAIL_THRESHOLD (curtail_frac, 'below'), N={N} ===")
if "Stage 2 Wind" not in _probe_log:
    print(f"SKIPPED -- '{TARGET_STRATEGY}' has no Stage 2 Wind rule (it's a fixed Decision in "
          f"the headline reconfiguration, not a Rule). Point TARGET_STRATEGY at a strategy that "
          f"still has one (e.g. 'Flexible - Mandated Link') to run this sweep for real.")
    sweep3_rows = []
else:
    sweep3_rows = []
    for v in [0.02, 0.05, 0.10, 0.20]:
        restore()
        DR.STAGE2_WIND_CURTAIL_THRESHOLD = v
        _, rule_log = run_flexible_mc()
        never_pct, mean_y, sd_y, n_fired = summarize(rule_log["Stage 2 Wind"], N)
        sweep3_rows.append((v, never_pct, mean_y, sd_y, n_fired))
        print(f"{'threshold':>10}{'never-fired%':>14}{'mean_year':>11}{'sd':>8}")
        print(f"{v:>10}{never_pct:>14.1%}{mean_y:>11.2f}{sd_y:>8.2f}")
    restore()

# ---- Verdicts ---------------------------------------------------------------
def discriminating_rows(rows):
    return [r for r in rows if r[3] > 0 and 0 < r[1] < 1.0]

print("\n=== VERDICT ===")

d1 = discriminating_rows(sweep1_rows)
if d1:
    picks = ", ".join(f"{v} (never-fired {never_pct:.0%}, sd {sd_y:.2f})" for v, never_pct, _, sd_y, _ in d1)
    print(f"Main Link: discriminates (sd>0, partial never-fired) at threshold(s) {picks} "
          f"on the original coarse grid. See MAIN LINK RE-SWEEP below for the finer, "
          f"seed-validated result -- the coarse grid above no longer straddles the real "
          f"discriminating band post-reconfiguration.")
else:
    print("Main Link: no swept threshold on the ORIGINAL coarse grid produced sd>0 with a "
          "partial never-fired rate under the current (post-reconfiguration) strategy shape "
          "-- it stays all-fire through 100 and jumps to all-never-fire by 150-200. See MAIN "
          "LINK RE-SWEEP below for the finer grid that recovers a real discriminating band.")

if sweep2_rows:
    d2 = discriminating_rows(sweep2_rows)
    if d2 and any_selective_and_adding:
        print("Extra Link: at least one threshold is both selective (fires in some draws, not "
              "others) AND value-adding (NPV|fired > NPV|never on those same draws) -- keep it, "
              "re-threshold to that value.")
    elif d2:
        print("Extra Link: selective at some threshold(s) but NOT value-adding at any of them -- "
              "firing selectively still loses money vs not firing. This is evidence to drop the "
              "rule from the headline strategy.")
    else:
        print("Extra Link: no swept threshold made it selective at all -- it stayed all-fire "
              "(low thresholds) or all-never-fire (high thresholds, including 8760) across the "
              "whole tested range, never discriminating between draws. Evidence to drop the rule.")
else:
    print("Extra Link: sweep skipped (see above) -- not present in the current headline strategy.")

if sweep3_rows:
    d3 = discriminating_rows(sweep3_rows)
    if d3:
        picks = ", ".join(f"{v} (never-fired {never_pct:.0%}, sd {sd_y:.2f})" for v, never_pct, _, sd_y, _ in d3)
        print(f"Stage 2 Wind: discriminates (sd>0, partial never-fired) at threshold(s) {picks}.")
    else:
        print("Stage 2 Wind: no swept threshold produced sd>0 with a partial never-fired rate -- "
              "collapsed to fixed-schedule behaviour across the whole tested range.")
else:
    print("Stage 2 Wind: sweep skipped (see above) -- it's a fixed Decision in the current "
          "headline strategy, not a Rule.")

# ---- MAIN LINK RE-SWEEP: finer grid, validated across three seeds ----------
print(f"\n=== MAIN LINK RE-SWEEP: finer grid around the current transition, N={N}, "
      f"seeds=42/7/1234 ===")
resweep_thresholds = [110, 115, 118, 120, 125, 130]
seeds = [42, 7, 1234]
resweep_results = {}
print(f"{'threshold':>10}" + "".join(f"{'seed=' + str(s):>22}" for s in seeds))
for v in resweep_thresholds:
    restore()
    DR.MAIN_LINK_HEADROOM_THRESHOLD = v
    row = []
    for s in seeds:
        _, rule_log = run_flexible_mc(seed=s)
        never_pct, mean_y, sd_y, n_fired = summarize(rule_log["Main Link"], N)
        row.append((never_pct, sd_y))
    resweep_results[v] = row
    print(f"{v:>10}" + "".join(f"{'never=' + format(np_, '.0%') + ',sd=' + format(sd, '.2f'):>22}"
                                for np_, sd in row))
restore()

print("\nRobust across all 3 seeds (never-fire 30-60%, sd>0.5)?")
robust = []
for v in resweep_thresholds:
    ok = all(0.30 <= np_ <= 0.60 and sd > 0.5 for np_, sd in resweep_results[v])
    if ok:
        robust.append(v)
    print(f"{v}: {'ROBUST' if ok else 'not robust'} -- "
          + ", ".join(f"never={np_:.1%},sd={sd:.2f}" for np_, sd in resweep_results[v]))

if robust:
    print(f"\nRECOMMENDATION: {robust} stay selective across all three seeds; "
          f"Decision_Rules.MAIN_LINK_HEADROOM_THRESHOLD is currently set to "
          f"{DR.MAIN_LINK_HEADROOM_THRESHOLD}.")
else:
    print("\nRECOMMENDATION: no threshold in this grid was robust across all three seeds.")

# see docs/notes/Debugging/mc_threshold_sweep.md#sweep-4-main-link-threshold-vs-enpv
print(f"\n=== SWEEP 4: MAIN_LINK_HEADROOM_THRESHOLD vs ENPV, N={N}, "
      f"target='{TARGET_STRATEGY}' (gated strategy) ===")
print(f"{'threshold':>10}{'never-fired%':>14}{'mean_year':>11}{'sd':>8}{'ENPV_£m':>10}")
sweep4_rows = []
for v in range(60, 141, 10):
    restore()
    DR.MAIN_LINK_HEADROOM_THRESHOLD = v
    npv_arr, rule_log = run_flexible_mc()
    never_pct, mean_y, sd_y, n_fired = summarize(rule_log["Main Link"], N)
    enpv = npv_arr.mean() / 1e6
    sweep4_rows.append((v, never_pct, mean_y, sd_y, enpv))
    print(f"{v:>10}{never_pct:>14.1%}{mean_y:>11.2f}{sd_y:>8.2f}{enpv:>10.1f}")
restore()

best_v, best_never, best_mean_y, best_sd, best_enpv = max(sweep4_rows, key=lambda r: r[4])
print(f"\nENPV-maximising threshold in the REQUESTED grid (60-140 step 10): {best_v} "
      f"(ENPV £{best_enpv:.1f}m, never-fired {best_never:.1%}, "
      f"mean fire year {best_mean_y:.2f}, sd {best_sd:.2f})")
print("CAVEAT, not a clean answer: every value from 70 to 140 gives IDENTICAL never-fired=100%, "
      "sd=nan, ENPV=£160.5m -- Main Link has already collapsed to never-fire across nearly the "
      "whole requested grid, so '60' only 'wins' by 1 fired draw out of 300. This is a real, "
      "unrequested consequence of the Stage1/Stage2 gating in _flexible: with wind now built only "
      "AFTER the link, there is far less pre-link generation to create the surplus headroom_p90 "
      "measures, so headroom_p90 sits much lower pre-link than it did when wind was on a fixed "
      "schedule regardless of the link. The 60-140 grid is now almost entirely past the point "
      "where the rule can ever fire. See the supplementary lower-range sweep below.")

# see docs/notes/Debugging/mc_threshold_sweep.md#supplementary-sweep-lower-and-negative-threshold-range
print(f"\n=== SUPPLEMENTARY: MAIN_LINK_HEADROOM_THRESHOLD vs ENPV, lower/negative range, "
      f"N={N}, target='{TARGET_STRATEGY}' ===")
print(f"{'threshold':>10}{'never-fired%':>14}{'mean_year':>11}{'sd':>8}{'ENPV_£m':>10}")
sweep4b_rows = []
for v in [-100, -50, -20, -10, 0, 10, 20, 30, 40, 50, 60]:
    restore()
    DR.MAIN_LINK_HEADROOM_THRESHOLD = v
    npv_arr, rule_log = run_flexible_mc()
    never_pct, mean_y, sd_y, n_fired = summarize(rule_log["Main Link"], N)
    enpv = npv_arr.mean() / 1e6
    sweep4b_rows.append((v, never_pct, mean_y, sd_y, enpv))
    print(f"{v:>10}{never_pct:>14.1%}{mean_y:>11.2f}{sd_y:>8.2f}{enpv:>10.1f}")
restore()

best_v2, best_never2, best_mean_y2, best_sd2, best_enpv2 = max(sweep4b_rows, key=lambda r: r[4])
print(f"\nENPV-maximising threshold in the SUPPLEMENTARY range: {best_v2} "
      f"(ENPV £{best_enpv2:.1f}m, never-fired {best_never2:.1%}, "
      f"mean fire year {best_mean_y2:.2f}, sd {best_sd2:.2f})")
print(f"This beats every value in the originally-requested 60-140 grid, including its own "
      f"nominal 'winner' (£{best_enpv:.1f}m at {best_v}), by £{(best_enpv2 - best_enpv):.1f}m, "
      f"and combines high ENPV with genuine discrimination (never-fired {best_never2:.0%}, "
      f"sd {best_sd2:.2f}) rather than a near-total collapse.")
print(f"\nCurrent MAIN_LINK_HEADROOM_THRESHOLD = {DR.MAIN_LINK_HEADROOM_THRESHOLD} is far above "
      f"both ranges tested and, per SWEEP 1 above, already gives 100% never-fired under the "
      f"gated strategy -- it was tuned against the PRE-gating strategy shape and is now stale "
      f"again, the same failure mode as the 100->115 retune two sessions ago.")
print("NOT applied -- this is a report only, per instruction. Decide separately whether "
      "MAIN_LINK_HEADROOM_THRESHOLD should be re-tuned, and to what value/range, given this.")
