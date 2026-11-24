"""Turn IEM 1-minute files into one array per station-day: 1440 temps (whole F, NaN if missing),
local STANDARD time midnight-to-midnight (the NWS climate day Kalshi settles on).
Output: days.npz with keys stn, date, temps."""
import csv, glob, os, datetime as dt, numpy as np, collections
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(HERE)
OFF = {"NYC": -5, "MDW": -6, "MIA": -5, "AUS": -6, "DEN": -7, "LAX": -8, "PHL": -5}
files = glob.glob(os.path.join(HERE, "onemin_hist", "*.csv")) + glob.glob(os.path.join(P, "onemin", "*.csv"))
days = collections.defaultdict(lambda: np.full(1440, np.nan, dtype=np.float32))
for fn in files:
    for r in csv.reader(open(fn)):
        if len(r) < 4 or r[0] == "station": continue
        try: f = float(r[3])
        except ValueError: continue
        if not (-60 < f < 135): continue
        t = dt.datetime.strptime(r[2], "%Y-%m-%d %H:%M") + dt.timedelta(hours=OFF[r[0]])
        days[(r[0], t.date().isoformat())][t.hour * 60 + t.minute] = f
keys = sorted(k for k, v in days.items() if np.isfinite(v).sum() >= 1200)
np.savez_compressed(os.path.join(HERE, "days.npz"), stn=np.array([k[0] for k in keys]),
                    date=np.array([k[1] for k in keys]), temps=np.stack([days[k] for k in keys]))
print(len(keys), "complete station-days", keys[0], keys[-1])
