import io, os, time, calendar, requests, pandas as pd

TOKEN = os.environ["RENINJA_TOKEN"]   # get a free token at https://www.renewables.ninja/register
OUT   = ("/Users/tomspencer/Desktop/Code/Strategic_Engineering_Project/"
         "Methodology_4/Coding/Inputs/Data/Generation/ninja/")
LAT, LON = 58.9830, -2.9600

os.makedirs(OUT, exist_ok=True)
s = requests.Session()
s.headers = {"Authorization": "Token " + TOKEN}
URL = "https://www.renewables.ninja/api/data/wind"


def parse(text):
    lines = text.splitlines()
    hdr = next(i for i, l in enumerate(lines) if l.startswith("time,"))
    return pd.read_csv(io.StringIO(text), skiprows=hdr, parse_dates=["time"])


def fetch(date_from, date_to):
    args = {"lat": LAT, "lon": LON,
            "date_from": date_from, "date_to": date_to,
            "dataset": "merra2", "capacity": 1.0,
            "height": 80, "turbine": "Vestas V90 2000",
            "format": "csv", "raw": "true"}
    for _ in range(3):
        r = s.get(URL, params=args)
        if r.status_code == 429:
            print("  rate limited, waiting 60s"); time.sleep(60); continue
        if not r.ok:
            print(f"  {r.status_code}: {r.text[:200]}"); return None
        time.sleep(2)
        return parse(r.text)
    return None


for yr in range(2001, 2020):
    path = f"{OUT}raw_{yr}.csv"
    if os.path.exists(path):
        print(yr, "cached"); continue

    if calendar.isleap(yr):
        a = fetch(f"{yr}-01-01", f"{yr}-06-30")
        b = fetch(f"{yr}-07-01", f"{yr}-12-31")
        df = pd.concat([a, b], ignore_index=True) if a is not None and b is not None else None
    else:
        df = fetch(f"{yr}-01-01", f"{yr}-12-31")

    if df is None:
        print(yr, "FAILED"); continue

    df.to_csv(path, index=False)
    print(yr, len(df), list(df.columns))