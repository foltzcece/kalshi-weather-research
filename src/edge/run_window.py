"""When does free-feed stale-bid value happen? Value of stale prints (3-50c, taken by informed side)
after the FREE feed proves the bucket decided, by city and Central-time hour."""
import sys, numpy as np, pandas as pd
rows = []
for tapes, a, b in [("event_tapes.csv", "2024-12-01", "2026-09-21"), ("../mm/trades.csv", "2026-09-22", "2026-11-19")]:
    sys.argv = ["x", tapes, a, b]
    exec(open("capture2.py").read().split("m = pd.Timedelta(minutes=1)")[0])
    for tk, d, kind, tf, tfree, win, gg in events(True):
        for label, t0 in (("free", tfree), ("fast", tf)):
            if t0 is None: continue
            w = gg[(gg.ts >= t0) & (gg.ts < tf + pd.Timedelta(hours=6)) & (gg.px >= 0.03) & (gg.px <= 0.5)]
            for ts, px, c in zip(w.ts, w.px, w["count"]):
                rows.append((label, tk.split("-")[0], ts, c * (px - 0.07 * px * (1 - px))))
df = pd.DataFrame(rows, columns=["feed", "city", "ts", "val"])
ct = df.ts.dt.tz_convert("America/Chicago"); df["hr"] = ct.dt.hour; df["wkend"] = ct.dt.dayofweek >= 5
df.to_pickle("run_window_df.pkl")
for feed in ("free", "fast"):
    x = df[df.feed == feed]; print(f"\n== {feed} feed: weekend share of value {x[x.wkend].val.sum()/x.val.sum():.0%} (weekends are 29% of days)")
    for city, g in list(x.groupby("city")) + [("ALL", x)]:
        h = g.groupby("hr").val.sum().reindex(range(24), fill_value=0); tot = h.sum()
        best = None
        for L in range(1, 25):
            for s in range(0, 25 - L):
                if h[s:s + L].sum() >= 0.9 * tot: best = (s, s + L); break
            if best: break
        s, e = best
        print(f"  {city:12s} 90% window {s:02d}:00-{e:02d}:00 CT ({e-s} h), captures {h[s:e].sum()/tot:.0%}; "
              f"peak hour {int(h.idxmax()):02d}:00; value ${tot:,.0f}")
