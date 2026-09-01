import csv
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Extra.orkney_link_opex import method_a_fixed_opex, method_b_total, ANNUAL_THROUGHPUT_GWH_BASE

LIFETIMES = {"Link": 40, "Generation": 25}   # years

REPD_WIND_VINTAGES_PATH = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
                            "Methodology_4/Coding/Inputs/Data/Generation/orkney_existing_wind_vintages.csv")

# Existing link OpEx estimate: see docs/notes/Model/Model_Components.md#existing-link-opex-estimation-method
_, _EXISTING_LINK_FIXED_OPEX = method_a_fixed_opex()
EXISTING_LINK_OPEX_GBP_PER_YEAR = method_b_total(
    ANNUAL_THROUGHPUT_GWH_BASE, 70, _EXISTING_LINK_FIXED_OPEX)["total"]


class Existing_link:

    def __init__(self):
        self.__Classification = 'Link'
        # VERIFIED: two 33kV subsea cables (Oct 1982, +1998), combined
        # 40MW, fully utilised [SSEN Shapinsay cable announcement, 2024]
        self.__LinkCapacity = 40 # MW
        self.__Opex = EXISTING_LINK_OPEX_GBP_PER_YEAR # ESTIMATE -- see orkney_link_opex.py / orkney_link_data.md; was previously a bare 0 placeholder

    def Capacity(self):
        return self.__LinkCapacity
    def Classification(self):
        return self.__Classification
    def OPEX(self):
        return self.__Opex
    
class Existing_Wind:
    def __init__(self, capacity=52.239):
        self.__Classification = 'Generation'
        self.__type = 'Wind'
        self.__Capacity = capacity   # MW, 2019 onshore wind [regional renewable stats]
        self.__Opex = 0.05 * 1300 * self.__Capacity * 1000

    def Capacity(self): 
        return self.__Capacity
    def Classification(self): 
        return self.__Classification
    def Type(self): 
        return self.__type
    def OPEX(self): 
        return self.__Opex


class Existing_PV:
    def __init__(self):
        self.__Classification = 'Generation'
        self.__type = 'PV'
        self.__Capacity = 1.558    # MW
        self.__Opex = 0.05 * 800 * self.__Capacity * 1000   # PV capex rate, not wind's
    
    def Capacity(self): 
        return self.__Capacity
    def Classification(self): 
        return self.__Classification
    def Type(self): 
        return self.__type
    def OPEX(self): 
        return self.__Opex



# REPD existing wind vintages: see docs/notes/Model/Model_Components.md#existing-wind-fleet-repd-vintages
def _load_wind_vintages():
    rows = []
    with open(REPD_WIND_VINTAGES_PATH, newline="") as f:
        for row in csv.DictReader(f):
            rows.append((int(row["commission_year"]), float(row["capacity_mw"])))
    return [(Existing_Wind(capacity=mw), year) for year, mw in rows]

EXISTING_FLEET = _load_wind_vintages() + [(Existing_PV(), 2015)]   # PV year: placeholder, no REPD solar entries for Orkney

# EXISTING_FLEET_NAMEPLATE purpose: see docs/notes/Model/Model_Components.md#existing_fleet_nameplate-purpose
EXISTING_FLEET_NAMEPLATE = {}
for _asset, _commission_year in EXISTING_FLEET:
    _type = _asset.Type()
    EXISTING_FLEET_NAMEPLATE[_type] = EXISTING_FLEET_NAMEPLATE.get(_type, 0.0) + _asset.Capacity()

def existing_alive_mw(Year):
    out = {}
    for a, cy in EXISTING_FLEET:
        if cy <= Year < cy + LIFETIMES[a.Classification()]:
            t = a.Type()
            out[t] = out.get(t, 0.0) + a.Capacity()
    return out

class Decision:

    def __init__(self,Asset,Year):
        self.__asset = Asset
        self.__BuildYear = Year
        
    def Asset(self):
        return self.__asset
    def BuildYear(self):
        return self.__BuildYear
    def IsBuilt(self,Year):
        if self.__BuildYear is None:
            return False
        return Year >= self.__BuildYear
    
class Generation_Capacity:
    def __init__(self):
        self.RESET()

    def RESET(self):
        self.__Assets = list(EXISTING_FLEET)

    def _alive(self, Year):
        return [(a, cy) for a, cy in self.__Assets if cy <= Year < cy + LIFETIMES[a.Classification()]]

    def Add_Asset(self, Asset, Year):
        self.__Assets.append((Asset, Year))

    def Current_Total_Capacity(self, Year):
        return sum(a.Capacity() for a, cy in self._alive(Year))

    def Capacity_By_Type(self, Year):
        out = {}
        for a, cy in self._alive(Year):
            t = a.Type()
            out[t] = out.get(t, 0.0) + a.Capacity()
        return out

    def Opex(self, Year):
        return sum(a.OPEX() for a, cy in self._alive(Year))

class Link_Capacity:

    def __init__(self):
        self.__Assets = [(Existing_link(), 1982)]   # both subsea cables folded into Existing_link's single 40MW figure -- see its own comment

    def RESET(self):
        self.__Assets = [(Existing_link(), 1982)]

    def _alive(self, Year):
        # existing link exempt from lifetime retirement; condition/reliability
        # risk modelled separately as sensitivity, not a fixed cliff
        return [(a, cy) for a, cy in self.__Assets
                if isinstance(a, Existing_link)
                or cy <= Year < cy + LIFETIMES[a.Classification()]]

    def Add_Asset(self, Asset, Year):
        self.__Assets.append((Asset, Year))

    def Current_Total_Capacity(self, Year):
        return sum(a.Capacity() for a, cy in self._alive(Year))

    def Opex(self, Year):
        return sum(a.OPEX() for a, cy in self._alive(Year))

