"""
Sample past radar at each Kalshi rain-market gauge (IEM national n0q mosaic, hourly).
For every uncertain rain city-day (7 AM price 3-97c) and every hour 12Z..03Z, records the
strongest radar echo (dBZ) within 2, 10, 30 and 60 km of the settlement gauge.
Rough guide: 20 dBZ = light rain/drizzle, 35 = moderate, 45+ = heavy.
Output: radar_features.csv (resumable). Run: python3 radar_sample.py
"""
import csv, io, math, os, sys, time, datetime as dt, urllib.request, ssl
import numpy as np
from PIL import Image
from picks import get
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "radar_features.csv")
gauges = {r["market_code"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(os.path.join(HERE, "gis", "rain_gauges.csv")))}
rows = [r for r in csv.DictReader(open(os.path.join(HERE, "history_more.csv"))) if r["series"] == "KXRAIN" and r["snap"] == "morn_7am"]
days = {}
for r in rows:
    mid = (float(r["yes_bid"]) + float(r["yes_ask"])) / 2
    code = r["ticker"].split("-")[-1]
    if 0.03 <= mid <= 0.97 and code in gauges:
        days.setdefault(r["date"], set()).add(code)
done = set()
if os.path.exists(OUT):
    done = {(r["valid"]) for r in csv.DictReader(open(OUT))}
RADII = (2, 10, 30, 60)
f = open(OUT, "a", newline="")
w = csv.writer(f)
if not done:
    w.writerow(["valid", "code"] + [f"dbz_{k}km" for k in RADII])
from concurrent.futures import ThreadPoolExecutor


def features(img, codes):
    out = []
    for code in codes:
        lat, lon = gauges[code]
        r0, c0 = int((50.0 - lat) / 0.005), int((lon + 126.0) / 0.005)
        vals = []
        for km in RADII:
            dy = int(km / 111 / 0.005) + 1
            dx = int(km / (111 * math.cos(math.radians(lat))) / 0.005) + 1
            win = img[max(0, r0 - dy): r0 + dy + 1, max(0, c0 - dx): c0 + dx + 1]
            yy, xx = np.ogrid[-min(dy, r0): win.shape[0] - min(dy, r0), -min(dx, c0): win.shape[1] - min(dx, c0)]
            mask = (yy * 0.005 * 111) ** 2 + (xx * 0.005 * 111 * math.cos(math.radians(lat))) ** 2 <= km ** 2
            v = int(win[mask].max()) if mask.any() else 0
            vals.append(round(v * 0.5 - 32.5, 1) if v > 0 else -99)   # pixel value -> dBZ (0 = no echo)
        out.append([code] + vals)
    return out


def job(item):
    date, t = item
    url = f"https://mesonet.agron.iastate.edu/archive/data/{t:%Y/%m/%d}/GIS/uscomp/n0q_{t:%Y%m%d%H%M}.png"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                img = np.array(Image.open(io.BytesIO(resp.read())))
            return t, features(img, sorted(days[date]))
        except Exception:
            time.sleep(5 * (attempt + 1))
    return t, None


jobs = []
for date in sorted(days):
    d0 = dt.datetime.fromisoformat(date).replace(tzinfo=dt.timezone.utc)
    for h in range(12, 28):
        t = d0 + dt.timedelta(hours=h)
        if t.strftime("%Y-%m-%dT%H:%MZ") not in done:
            jobs.append((date, t))
with ThreadPoolExecutor(3) as ex:
    for t, rows_ in ex.map(job, jobs):
        valid = t.strftime("%Y-%m-%dT%H:%MZ")
        if rows_ is None:
            print("! missing", valid, file=sys.stderr)
            continue
        for r in rows_:
            w.writerow([valid] + r)
        f.flush()
        print(valid, file=sys.stderr)
f.close()
