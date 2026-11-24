"""Out-of-box tests (2026-11-24). Build an hourly last-trade price grid for every high-temp bucket
from full trade tapes (mm/trades.csv: 7 cities Sep22-Nov19; exec/tapes_extra.csv: 11 cities Aug23-Nov19).
Output grid.pkl: ticker, series, date, hour_utc(ts), price (last trade at/before that hour, ffill), result."""
import pandas as pd, numpy as np, os
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fr = []
for f in ["mm/trades.csv", "exec/tapes_extra.csv"]:
    t = pd.read_csv(os.path.join(P, f), usecols=["series","ticker","date","result","ts","yes_price"])
    fr.append(t[t.series.str.startswith("KXHIGH")])
t = pd.concat(fr); t["ts"] = pd.to_datetime(t.ts, utc=True, format="ISO8601")
t["h"] = t.ts.dt.ceil("h")
last = t.sort_values("ts").groupby(["ticker","h"]).yes_price.last().reset_index()
meta = t.drop_duplicates("ticker").set_index("ticker")[["series","date","result"]]
out = []
for tk, g in last.groupby("ticker"):
    idx = pd.date_range(g.h.min(), g.h.max(), freq="h")
    s = g.set_index("h").yes_price.reindex(idx).ffill()
    out.append(pd.DataFrame({"ticker": tk, "h": idx, "price": s.values}))
g = pd.concat(out).join(meta, on="ticker")
g.to_pickle(os.path.join(os.path.dirname(__file__), "grid.pkl"))
print(len(g), g.ticker.nunique())
