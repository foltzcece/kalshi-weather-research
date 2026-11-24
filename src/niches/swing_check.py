"""Two leads from the scan, checked as trades:
A) 'Market under-reacts to big day-to-day swings': when the market expects >=6F change vs yesterday,
   the actual tends to move even further. Trade = buy YES on the bucket one step beyond the favourite in the
   direction of the swing (taker, at ask + fee); also NO on the bucket one step back.
B) 'Lows come in warmer than priced' (seen only in the lows holdout): YES on the bucket one step warmer than the favourite."""
import pandas as pd, numpy as np, os
HERE = os.path.dirname(os.path.abspath(__file__))
d = pd.read_csv(os.path.join(HERE, "temp_rows.csv"), parse_dates=["date"])
d = d[(d.yes_ask < 1) & (d.yes_bid > 0)]
yc = d.yes_ask + d.fee_yes; nc = 1 - d.yes_bid + d.fee_no
d["yes_pl"] = d.y - yc; d["no_pl"] = (1 - d.y) - nc; d["yc"] = yc; d["nc"] = nc
d["resid"] = d.y - d.mid
sets = {"disc": (d.src == "main7") & (d.date < "2026-08-01"), "hold_time": (d.src == "main7") & (d.date >= "2026-08-01"),
        "hold_cities": (d.src == "more") & (d.kind == "high"), "hold_lows": (d.src == "more") & (d.kind == "low")}
def cse(v, dt):
    v = pd.Series(np.asarray(v, float)); dt = np.asarray(dt); mu = v.mean()
    s = (v - mu).groupby(dt).sum(); return mu, np.sqrt((s ** 2).sum()) / len(v)
def show(lbl, X, col, cost):
    if len(X) < 10: print(f"  {lbl}: n={len(X)}"); return
    m, s = cse(X[col], X.date); c = X[cost].mean()
    print(f"  {lbl:<40} n={len(X):4d} resid {X.resid.mean()*100:+.1f}c  P/L {m*100:+.1f}c/ctr ±{1.96*s*100:.1f}  return {m/c:+.1%} ±{1.96*s/c:.1%}")
print("A) Big swings (|market-expected change| >= 6F)")
for sn, m in sets.items():
    X = d[m & (d.chg.abs() >= 6)]
    up = X.chg > 0
    ahead = X[(up & (X.offset == 1)) | (~up & (X.offset == -1))]
    behind = X[(up & (X.offset == -1)) | (~up & (X.offset == 1))]
    show(f"{sn} YES one step ahead of swing", ahead, "yes_pl", "yc")
    show(f"{sn} NO one step behind swing", behind, "no_pl", "nc")
print("\nB) Warmer-than-favourite bucket")
for sn, m in sets.items():
    show(f"{sn} YES offset+1", d[m & (d.offset == 1)], "yes_pl", "yc")
    show(f"{sn} NO offset-1", d[m & (d.offset == -1)], "no_pl", "nc")
