import csv, numpy as np, collections, os
P = ".."
S2C = {"KXHIGHNY": "NYC", "KXHIGHCHI": "MDW", "KXHIGHMIA": "MIA", "KXHIGHAUS": "AUS", "KXHIGHDEN": "DEN", "KXHIGHLAX": "LAX", "KXHIGHPHIL": "PHL"}
act = {}
for fn in ["../history.csv", "../audit/history_oos.csv"]:
    for r in csv.DictReader(open(fn)):
        if r["series"] in S2C and r["actual"] not in ("", None):
            try: act[(S2C[r["series"]], r["date"])] = float(r["actual"])
            except ValueError: pass
z = np.load("days.npz"); res = collections.defaultdict(collections.Counter)
rows = 0
for s, d, t in zip(z["stn"], z["date"], z["temps"]):
    if (s, d) not in act: continue
    a = act[(s, d)]; rows += 1
    m = np.nanmax(t); nmax = int(np.nansum(t == m)); nm1 = int(np.nansum(t >= m - 1))
    res["n_at_max=%s" % min(nmax, 6)][int(a - m)] += 1
    for N in (2, 3, 5):
        rm = np.convolve(np.nan_to_num(t, nan=-99), np.ones(N) / N, mode="valid")
        res["round(max %d-min mean)" % N][int(a - np.floor(rm.max() + 0.5))] += 1
        res["floor(max %d-min mean)" % N][int(a - np.floor(rm.max()))] += 1
print(rows)
for k in sorted(res):
    c = res[k]; n = sum(c.values())
    print(f"{k:28s} n={n:5d} " + " ".join(f"{g:+d}:{c[g]/n:.0%}" for g in sorted(c) if c[g] / n > .005))
