# References [1]-[5]: see docs/notes/Model/Options.md#references

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
    
# If combining wind projets: Costa, Hesta, Hammers hill extension
class Stage1_Wind_Buildout:
    def __init__(self):
        self.__Classification = 'Generation'
        self.__type = 'Wind'  
        self.__Capacity = 20.4 + 16.3 + 8.4 #MW
        self.__Capex = 1300 * self.__Capacity * 1000 #£/kW [2] p.20, price yr unconfirmed
        self.__CFDlifetime = 15 #years
        self.__Opex = 0.05 * self.__Capex #5% of capex [2] p.20

    def Capex(self):
        return self.__Capex  
    def OPEX(self):
        return self.__Opex   
    def Capacity(self):
        return self.__Capacity  
    def CFD_Lifetime(self):
        return self.__CFDlifetime
    
    # Identification

    def Name(self):
        return 'Hesta And Costa'    
    def Type(self):
        return self.__type  
    def Classification(self):
        return self.__Classification
 

# OIC Community Wind Farm, 3 projects -> Quanterness, Faray, Hoy/Wee Fea
class Stage2_Wind_Buildout:
    def __init__(self):
        self.__Classification = 'Generation'
        self.__type = 'Wind'  
        self.__Capacity = 28.8 * 3 #MW
        self.__Capex = 1300 * self.__Capacity * 1000 #£/kW [2] p.20, price yr unconfirmed
        # see docs/notes/Model/Options.md#stage-2-wind-cfd-lifetime-assumption
        self.__CFDlifetime = 15 #years
        self.__Opex = 0.05 * self.__Capex #5% of capex [2] p.20

    def Capex(self):
        return self.__Capex  
    def OPEX(self):
        return self.__Opex
    def Capacity(self):
        return self.__Capacity
    def CFD_Lifetime(self):
        return self.__CFDlifetime

    # Identification

    def Name(self):
        return 'OIC Community Wind Farm'
    def Type(self):
        return self.__type
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


# Staged interconnector design: see docs/notes/Model/Options.md#staged-interconnector-design-rationale
STAGED_LINK_STAGE_SIZES_DEFAULT = [110.0, 110.0 / 3, 110.0 / 3, 110.0 / 3]   # MW, must sum to 220 (NewLink's capacity)

STAGED_LINK_STAGE1_YEAR_DEFAULT = 2028   # matches Baseline's NewLink build year -- a deliberate commitment, not a placeholder

# UNCALIBRATED: see docs/notes/Model/Options.md#staged-interconnector-fixed-cost-per-stage-uncalibrated
STAGED_LINK_FIXED_PER_STAGE = 20e6 * REBASE_2018_TO_2023

STAGED_LINK_FIXED_PER_STAGE_SWEEP = [0.0, 10e6 * REBASE_2018_TO_2023, STAGED_LINK_FIXED_PER_STAGE,
                                      30e6 * REBASE_2018_TO_2023, 40e6 * REBASE_2018_TO_2023]

# variable £/MW before learning discount -- Extra_Link's linear fit slope (Table A3.3, [1])
STAGED_LINK_BASE_PERMW = 0.69e6 * REBASE_2018_TO_2023

STAGED_LINK_LEARNING_MODE_DEFAULT = "wright"    # "scalar" | "wright" -- see stage_variable_permw
STAGED_LINK_LEARNING_FACTOR_DEFAULT = 0.95      # scalar mode: variable_permw(n) = base*f**(n-1), f<1
STAGED_LINK_WRIGHT_LR_DEFAULT = 0.10            # wright mode: fractional cost cut per cumulative-MW doubling


# Cost formula: see docs/notes/Model/Options.md#stage_variable_permw-cost-formula
def stage_variable_permw(stage_index, cum_mw_before_stage, stage_sizes,
                          base_permw=None, mode=None, learning_param=None):
    if base_permw is None:
        base_permw = STAGED_LINK_BASE_PERMW
    if mode is None:
        mode = STAGED_LINK_LEARNING_MODE_DEFAULT
    if stage_index == 1:
        return base_permw
    if learning_param is None:
        learning_param = (STAGED_LINK_LEARNING_FACTOR_DEFAULT if mode == "scalar"
                           else STAGED_LINK_WRIGHT_LR_DEFAULT)
    if mode == "scalar":
        f = learning_param
        return base_permw * f ** (stage_index - 1)
    if mode == "wright":
        LR = learning_param
        b = -math.log2(1 - LR)
        MW0 = stage_sizes[0]
        return base_permw * (cum_mw_before_stage / MW0) ** (-b)
    raise ValueError(f"unknown learning mode {mode!r}")


# capex_mult semantics: see docs/notes/Model/Options.md#stagedlinkstage-capex_mult-semantics
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
