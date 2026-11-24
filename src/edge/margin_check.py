"""How reliable is the settle rule as a function of how far the 5-min mean max cleared the rounding line?"""
import csv, numpy as np, pandas as pd, collections
from lock_events import S2C, run_settle
act = {}
for fn in ["../history.csv", "../audit/history_oos.csv"]:
    for r in csv.DictReader(open(fn)):
        if r["series"] in S2C:
            try: act[(S2C[r["series"]], r["date"])] = float(r["actual"])
            except ValueError: pass
z = np.load("days.npz"); c = collections.defaultdict(collections.Counter)
for s, d, t in zip(z["stn"], z["date"], z["temps"]):
    if (s, d) not in act: continue
    rm, st = run_settle(t); mx = np.nanmax(rm); frac = mx - np.floor(mx)   # .5 = rounding line
    dist = abs(frac - 0.5)
    b = "<0.05" if dist < .05 else "<0.15" if dist < .15 else "<0.25" if dist < .25 else ">=0.25"
    nmiss = int(np.isnan(t).sum()); mb = "miss<30" if nmiss < 30 else "miss>=30"
    c[b][int(act[(s, d)] - st[-1])] += 1; c[mb][int(act[(s, d)] - st[-1])] += 1
for k in sorted(c):
    n = sum(c[k].values()); print(f"distance from .5 line {k:8s} n={n:5d} match {c[k][0]/n:.1%}  " + " ".join(f"{g:+d}:{v}" for g, v in sorted(c[k].items()) if g))
