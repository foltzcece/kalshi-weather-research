"""Fetch IEM 1-minute ASOS temps for the 7 main stations, Dec 2024 - Aug 2026 (training data for the
intraday nowcast; the trading test period Sep 22 - Nov 2026 is NOT included). One file per station-month."""
import os, sys, time, urllib.request, datetime as dt, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "onemin_hist")
STNS = ["NYC", "MDW", "MIA", "AUS", "DEN", "LAX", "PHL"]
months = []
d = dt.date(2024, 12, 1)
while d < dt.date(2026, 9, 1):
    n = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    months.append((d, n)); d = n
def one(job):
    s, (a, b) = job
    fn = os.path.join(OUT, f"{s}_{a:%Y%m}.csv")
    if os.path.exists(fn) and os.path.getsize(fn) > 1000: return
    url = ("https://mesonet.agron.iastate.edu/cgi-bin/request/asos1min.py?station=%s&vars=tmpf"
           "&sts=%sT06:00Z&ets=%sT12:00Z&sample=1min&what=download&tz=UTC" % (s, a.isoformat(), b.isoformat()))
    for k in range(6):
        try:
            data = urllib.request.urlopen(url, timeout=300).read()
            open(fn, "wb").write(data); print("ok", s, a, len(data), flush=True); return
        except Exception as e:
            print("retry", s, a, e, flush=True); time.sleep(10 * (k + 1))
with cf.ThreadPoolExecutor(3) as ex:
    list(ex.map(one, [(s, m) for s in STNS for m in months]))
print("done")
