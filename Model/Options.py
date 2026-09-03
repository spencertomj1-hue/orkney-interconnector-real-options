# [1] Ofgem (2019) Orkney Final Needs Case conditional-approval decision.
# [2] DNV GL (2018) Orkney Project Final Needs Case Assessment, for Ofgem.
# [3] SSEN Transmission (2019) RIIO-T2 OpEx Business Plan Justification Paper.
# [4] Scottish Hydro Electric Transmission plc (2020) Directors' Report & Accounts.
# [5] Graca Gomes, Cardin, Wu (2025) Strategic real options for solar PV, IET PNZ 2025.

import csv
import math

def _cpi(year, path="/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                     "Methodology_4/Coding/Inputs/Data/cpi_index.csv"):
    with open(path, newline="") as f:
        return next(float(r["cpi_index"]) for r in csv.DictReader(f) if int(r["year"]) == year)

# ONS CPI 2018->2023 rebase factor. Applies to any 2018-priced [1]/GHD figure.
REBASE_2018_TO_2023 = _cpi(2023) / _cpi(2018)

# £15.1m T1 direct opex [3] / £3,469.2m FY2020 RAV [4] = 0.435% (link opex
# redacted in [1]/[2]; new link likely lower-maintenance, so conservative-high).
LINK_OPEX_RATE = 15.1 / 3469.2

# Sweep, single source of truth: 0.30/0.60 = range, central = sourced, 0.55 = old assumption (conservative-upper).
LINK_OPEX_SWEEP = [0.0030, LINK_OPEX_RATE, 0.0055, 0.0060]

class NewLink:
    def __init__(self, capex_mult=1.0):
        self.__Classification = 'Link'
        self.__LinkCapacity = 220 # MW
        self.__Capex_Mult = capex_mult
        self.__Capex = 262e6 * REBASE_2018_TO_2023 * capex_mult # [1] Table A3.3, 2018 prices rebased
        self.__OPEX_Rate = LINK_OPEX_RATE # [3]/[4]

    def Capacity(self):
        return self.__LinkCapacity
    def Capex(self):
        return self.__Capex
    def Capex_Mult(self):
        return self.__Capex_Mult
    def OPEX(self):
        return self.__OPEX_Rate * self.__Capex
    def Classification(self):
        return self.__Classification

class Extra_Link:

    def __init__(self,Capacity,capex_mult=1.0):
        self.__Classification = 'Link'
        self.__LinkCapacity = Capacity # MW
        self.__Capex_Mult = capex_mult
        # [1] linear fit to Table A3.3's two points (132MW=£201m, 220MW=£262m), 2018 prices rebased
        self.__Capex = (110e6 + 0.69e6 * Capacity) * REBASE_2018_TO_2023 * capex_mult
        self.__OPEX_Rate = LINK_OPEX_RATE # [3]/[4]

    def Capacity(self):
        return self.__LinkCapacity
    def Capex(self):
        return self.__Capex
    def Capex_Mult(self):
        return self.__Capex_Mult
    def OPEX(self):
        return self.__OPEX_Rate * self.__Capex
    def Classification(self):
        return self.__Classification


# Splits the single 220MW NewLink into N stages, each priced fixed_per_stage
# + variable_permw*MW with a learning-curve discount on variable_permw for
# later stages; fixed_per_stage stays flat every stage (no economies of scale
# from splitting one contract into several) -- the phased-deployment design
# alternative [5] evaluates against a single fixed-capacity build for PV,
# applied here to transmission capacity.
STAGED_LINK_STAGE_SIZES_DEFAULT = [110.0, 110.0 / 3, 110.0 / 3, 110.0 / 3]   # MW, must sum to 220 (NewLink's capacity)

STAGED_LINK_STAGE1_YEAR_DEFAULT = 2028   # matches Baseline's NewLink build year -- a deliberate commitment, not a placeholder

# UNCALIBRATED: should be a later phase's capacity-independent mobilisation
# cost when reusing stage 1's route/consent, not a full new project's. No
# real precedent found (checked Table A3.3, SSEN's 2024 Orkney-Caithness
# contract, generic HVDC benchmarks -- the real project isn't staged). Set to
# ~1/5 of Extra_Link's fixed cost (an upper bound, since that prices a wholly
# separate circuit) -- swept rather than guessed harder, see the SWEEP below.
STAGED_LINK_FIXED_PER_STAGE = 20e6 * REBASE_2018_TO_2023

STAGED_LINK_FIXED_PER_STAGE_SWEEP = [0.0, 10e6 * REBASE_2018_TO_2023, STAGED_LINK_FIXED_PER_STAGE,
                                      30e6 * REBASE_2018_TO_2023, 40e6 * REBASE_2018_TO_2023]

# variable £/MW before learning discount -- Extra_Link's linear fit slope (Table A3.3, [1])
STAGED_LINK_BASE_PERMW = 0.69e6 * REBASE_2018_TO_2023

STAGED_LINK_WRIGHT_LR_DEFAULT = 0.10            # fractional cost cut per cumulative-MW doubling


def stage_variable_permw(stage_index, cum_mw_before_stage, stage_sizes,
                          base_permw=None, learning_param=None):
    if base_permw is None:
        base_permw = STAGED_LINK_BASE_PERMW
    if stage_index == 1:
        return base_permw
    if learning_param is None:
        learning_param = STAGED_LINK_WRIGHT_LR_DEFAULT
    LR = learning_param
    b = -math.log2(1 - LR)
    MW0 = stage_sizes[0]
    return base_permw * (cum_mw_before_stage / MW0) ** (-b)


# One stage of a staged (multi-block) interconnector build, same read
# interface as NewLink/Extra_Link. capex_mult is the REALISED multiplier for
# THIS stage -- for the rule-based strategy this comes from
# sample_capex_estimate_seq at the stage's own build year, not a single
# project-wide draw like NewLink/Extra_Link use.
class StagedLinkStage:
    def __init__(self, capacity_mw, fixed_per_stage, variable_permw, capex_mult=1.0):
        self.__Classification = 'Link'
        self.__LinkCapacity = capacity_mw
        self.__Capex_Mult = capex_mult
        self.__Capex = (fixed_per_stage + variable_permw * capacity_mw) * capex_mult
        self.__OPEX_Rate = LINK_OPEX_RATE   # [3]/[4], same rate as NewLink/Extra_Link

    def Capacity(self):
        return self.__LinkCapacity
    def Capex(self):
        return self.__Capex
    def Capex_Mult(self):
        return self.__Capex_Mult
    def OPEX(self):
        return self.__OPEX_Rate * self.__Capex
    def Classification(self):
        return self.__Classification
