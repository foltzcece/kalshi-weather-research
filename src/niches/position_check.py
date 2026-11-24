"""Follow-up on the one survivor: buckets 1-2 steps away from the favourite.
Is this just the known long-shot price effect, or does position add something? And can NO be bought profitably?"""
import pandas as pd, numpy as np, os
HERE = os.path.dirname(os.path.abspath(__file__))
d = pd.read_csv(os.path.join(HERE, "temp_rows.csv"), parse_dates=["date"])
d = d[(d.yes_ask < 1) & (d.yes_bid > 0)]
d["resid"] = d.y - d.mid
sets = {"disc": (d.src == "main7") & (d.date < "2026-08-01"), "hold_time": (d.src == "main7") & (d.date >= "2026-08-01"),
        "hold_cities": (d.src == "more") & (d.kind == "high"), "hold_lows": (d.src == "more") & (d.kind == "low")}
for s in ["launch_apr", "launch_aug"]:
    if (d.src == s).any(): sets[s] = d.src == s
def cse(v, dates):
    v = pd.Series(v.values); dt = dates.values; mu = v.mean()
    s = (v - mu).groupby(dt).sum(); return mu, np.sqrt((s**2).sum()) / len(v)
d["pos"] = np.select([d.offset.abs() == 1, d.offset.abs() == 2, d.offset.abs() >= 3, d.offset == 0], ["adj1", "adj2", "far3+", "fav"], "x")
d["band"] = pd.cut(d.mid, [0, .05, .10, .20, .35, .50, 1], labels=["<5", "5-10", "10-20", "20-35", "35-50", "50+"])
noc = 1 - d.yes_bid + d.fee_no
d["no_ret"] = ((1 - d.y) - noc) / noc
d["no_cost"] = noc
print("Residual (won - price) by price band x position, cents. Same price, different position = does position matter?")
for sname, m in sets.items():
    X = d[m]
    t = X.groupby(["band", "pos"], observed=True).resid.agg(["mean", "size"]).unstack("pos")
    print(f"\n[{sname}]"); print((t["mean"] * 100).round(1).astype(str) + " (n" + t["size"].fillna(0).astype(int).astype(str) + ")")
print("\nBuy NO at (1 - bid) + taker fee on buckets 1-2 steps from favourite, YES mid 10-35c:")
for sname, m in sets.items():
    for pos in ["adj1", "adj2"]:
        X = d[m & (d.pos == pos) & d.mid.between(.10, .35)]
        mu, se = cse((1 - X.y) - X.no_cost, X.date)
        ret = mu / X.no_cost.mean()
        print(f"  {sname:<12}{pos}: n={len(X):5d} dates={X.date.nunique():4d}  profit/contract {mu*100:+.2f}c ±{1.96*se*100:.2f}c  return {ret:+.1%} ±{1.96*se/X.no_cost.mean():.1%}")
print("\nBuy NO, all buckets YES mid 10-35c regardless of position (baseline):")
for sname, m in sets.items():
    X = d[m & d.mid.between(.10, .35)]
    mu, se = cse((1 - X.y) - X.no_cost, X.date)
    print(f"  {sname:<12} n={len(X):5d} profit/contract {mu*100:+.2f}c ±{1.96*se*100:.2f}c  return {mu/X.no_cost.mean():+.1%}")
