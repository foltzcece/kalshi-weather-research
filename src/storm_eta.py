"""
cece's storm-motion idea, recreated on 90 days of history: for each rain gauge at 9 AM, 11 AM,
1 PM and 3 PM Central, project every tracked storm cell forward along its motion (NEXRAD storm
tracking: speed + direction, from IEM's archive) and find when the first cell reaches the gauge.
DRCT in the archive is the direction the cell moves FROM (checked against consecutive positions).
Output: storm_eta.csv (valid, code, eta_any, eta_strong, n_arriving, cell_here). ETA in minutes, 999 = none in 3 h.
"""
import csv, io, math, os, sys, collections, urllib.request, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
SET = os.environ.get("RAIN_SET", "")            # "" = Aug-Nov (history_more.csv); "summer" = Jun-Aug
SFX = f"_{SET}" if SET else ""
SRC = "history_summer.csv" if SET == "summer" else "history_more.csv"
OUT = os.path.join(HERE, f"storm_eta{SFX}.csv")
gauges = {r["market_code"]: (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(os.path.join(HERE, "gis", "rain_gauges.csv")))}
days = collections.defaultdict(set)
for r in csv.DictReader(open(os.path.join(HERE, f"rain_candles{SFX}.csv"))):
    days[r["date"]].add(r["ticker"].split("-")[-1])
done = {r["valid"][:10] for r in csv.DictReader(open(OUT))} if os.path.exists(OUT) else set()
f = open(OUT, "a", newline=""); w = csv.writer(f)
if not done:
    w.writerow(["valid", "code", "eta_any", "eta_strong", "n_arriving", "cell_here"])
HOURS, HIT_KM, HORIZON = (15, 17, 19, 21), 10.0, 180


def km(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * 111.0, (lon2 - lon1) * 111.0 * math.cos(math.radians(lat1)))


for date in sorted(days):
    if date in done:
        continue
    codes = [c for c in days[date] if c in gauges]
    url = (f"https://mesonet.agron.iastate.edu/cgi-bin/request/gis/nexrad_storm_attrs.py?fmt=csv"
           f"&sts={date}T14:00Z&ets={date}T21:05Z")
    try:
        text = urllib.request.urlopen(url, timeout=600).read().decode()
    except Exception as e:
        print("!", date, e, file=sys.stderr); continue
    cells = collections.defaultdict(list)   # hour -> cells seen in the 10 minutes before it
    for r in csv.DictReader(io.StringIO(text)):
        t = dt.datetime.strptime(r["VALID"], "%Y%m%d%H%M")
        for H in HOURS:
            T = dt.datetime.fromisoformat(date).replace(hour=H)
            if T - dt.timedelta(minutes=10) <= t <= T:
                cells[H].append((float(r["LAT"]), float(r["LON"]), float(r["DRCT"] or 0), float(r["SKNT"] or 0), float(r["MAX_DBZ"] or 0)))
    for H in HOURS:
        for code in codes:
            glat, glon = gauges[code]
            eta_any = eta_strong = 999; n = 0; here = 0
            for lat, lon, drct, sknt, dbz in cells[H]:
                if km(glat, glon, lat, lon) > 400:
                    continue
                if km(glat, glon, lat, lon) <= HIT_KM:
                    here = 1; eta = 0
                else:
                    head = math.radians((drct + 180) % 360); v = sknt * 1.852 / 60  # km per minute
                    eta = None
                    for m in range(5, HORIZON + 1, 5):
                        plat = lat + v * m * math.cos(head) / 111.0
                        plon = lon + v * m * math.sin(head) / (111.0 * math.cos(math.radians(lat)))
                        if km(glat, glon, plat, plon) <= HIT_KM:
                            eta = m; break
                    if eta is None:
                        continue
                n += 1
                eta_any = min(eta_any, eta)
                if dbz >= 45:
                    eta_strong = min(eta_strong, eta)
            w.writerow([f"{date}T{H:02d}:00Z", code, eta_any, eta_strong, n, here])
    f.flush(); print(date, len(text) // 1000, "kB", file=sys.stderr)
f.close()
