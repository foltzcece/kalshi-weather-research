"""Test 1: does the market under-react? Implied mean high (from last trade prices) vs settlement.
error_t = actual - mean_t ; signal = mean_t - mean_{t-k}. Under-reaction -> positive slope.
Also lead-lag: neighbour city's recent move predicting this city's error.
Discovery: event dates Sep 22 - Oct 20 2026. Holdout: Aug 23 - Sep 21 (11 cities) and Oct 21 - Nov 19 (all)."""
import pandas as pd, numpy as np, os, re, sys
H = os.path.dirname(os.path.abspath(__file__))
g = pd.read_pickle(os.path.join(H, "grid.pkl"))
g["kind"] = g.ticker.str.extract(r"-([BT])[\d.]+$")[0]; g["x"] = g.ticker.str.extract(r"-[BT]([\d.]+)$")[0].astype(float)
g["event"] = g.ticker.str.rsplit("-", n=1).str[0]
tmin = g.groupby("event").x.transform("min")
g["val"] = np.where(g.kind == "B", g.x, np.where(g.x == tmin, g.x - 1.5, g.x + 1.5))
# actual = value of winning bucket
win = g[g.result == "yes"].drop_duplicates("event").set_index("event").val.rename("actual")
w = g.pivot_table(index=["event", "h"], columns="ticker", values="price")  # wide is heavy; do per event instead
rows = []
for ev, e in g.groupby("event"):
    if ev not in win.index: continue
    pv = e.pivot(index="h", columns="ticker", values="price")
    vals = e.drop_duplicates("ticker").set_index("ticker").val.reindex(pv.columns).values
    full = pv.notna().all(axis=1); pv = pv[full]
    if len(pv) < 10: continue
    p = pv.values; s = p.sum(1)
    mean = (p * vals).sum(1) / s
    rows.append(pd.DataFrame({"event": ev, "series": e.series.iloc[0], "date": e.date.iloc[0], "h": pv.index,
                              "mean": mean, "psum": s, "actual": win[ev]}))
d = pd.concat(rows); d["err"] = d.actual - d["mean"]
d.to_pickle(os.path.join(H, "implied.pkl")); print(len(d), d.event.nunique())
