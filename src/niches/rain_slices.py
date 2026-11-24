"""Rain (KXRAIN) slices. Main pre-registered test: are a city's rain markets mispriced in its first 30 days
after launch? Kalshi added 19 cities in stages (Aug 27 - Nov 18), so we compare new cities with the
20 established cities ON THE SAME DATES, which cancels out weather and season.
Also: weekend, price band, snapshot. Dates clustered for error bars."""
import pandas as pd, numpy as np, os
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(HERE)
a = pd.read_csv(os.path.join(P, "history_summer.csv")); b = pd.read_csv(os.path.join(P, "history_more.csv"))
r = pd.concat([a, b[b.series == "KXRAIN"]]).drop_duplicates(["ticker", "snap"])
r["city"] = r.ticker.str.split("-").str[-1]
r = r[~r.city.isin(["TAM", "DET"])]
r["date"] = pd.to_datetime(r.date)
r["age"] = (r.date - r.groupby("city").date.transform("min")).dt.days
r["y"] = (r.result == "yes").astype(int); r["mid"] = (r.yes_bid + r.yes_ask) / 2
r = r[(r.yes_ask < 1) & (r.yes_bid > 0)]
noc = 1 - r.yes_bid + np.ceil(0.07 * (1 - r.yes_bid) * r.yes_bid * 100 - 1e-9) / 100
yc = r.yes_ask + np.ceil(0.07 * r.yes_ask * (1 - r.yes_ask) * 100 - 1e-9) / 100
r["no_pl"] = (1 - r.y) - noc; r["no_cost"] = noc; r["yes_pl"] = r.y - yc; r["yes_cost"] = yc
r["resid"] = r.y - r.mid
r["weekend"] = r.date.dt.dayofweek >= 5
def cse(v, dt):
    v = pd.Series(np.asarray(v, float)); dt = np.asarray(dt); mu = v.mean()
    s = (v - mu).groupby(dt).sum(); return mu, np.sqrt((s ** 2).sum()) / len(v)
first_day = {"orig": "2026-07-15"}
r["orig"] = r.groupby("city").date.transform("min") == "2026-07-15"
L = r[r.date >= "2026-08-27"]
print("=== New-city test (dates >= Aug 27; established = 20 cities live since Jul 15) ===")
for snap in ["morn_7am", "eve_6pm"]:
    for N in [14, 30, 45]:
        S = L[L.snap == snap]
        S = S[S.mid.between(0.05, 0.95)]
        new = S[(~S.orig) & (S.age < N)]
        dates = new.date.unique()
        est = S[S.orig & S.date.isin(dates)]
        mn, sn = cse(new.resid, new.date); me, se_ = cse(est.resid, est.date)
        # within-date difference
        dd = new.groupby("date").resid.mean() - est.groupby("date").resid.mean()
        dd = dd.dropna()
        npl, nse = cse(new.no_pl, new.date)
        print(f"{snap} first {N:2d}d: new n={len(new):4d} ({new.city.nunique()} cities, {len(dates)} dates) resid {mn*100:+.1f}c ±{1.96*sn*100:.1f} | "
              f"est same dates n={len(est):4d} resid {me*100:+.1f}c ±{1.96*se_*100:.1f} | diff {dd.mean()*100:+.1f}c ±{1.96*dd.std()/np.sqrt(len(dd))*100:.1f} | "
              f"buy NO new: {npl*100:+.1f}c/ctr ±{1.96*nse*100:.1f} ({npl/new.no_cost.mean():+.1%})")
print("\nNew cities after day 30 (are they still different?)")
for snap in ["morn_7am", "eve_6pm"]:
    S = L[(L.snap == snap) & L.mid.between(.05, .95)]
    old_new = S[(~S.orig) & (S.age >= 30)]
    m, s = cse(old_new.resid, old_new.date)
    print(f"  {snap}: n={len(old_new)} resid {m*100:+.1f}c ±{1.96*s*100:.1f}")
print("\nEstablished cities by month (does the launch overpricing fade?), 7 AM, mid 5-95c:")
S = r[r.orig & (r.snap == "morn_7am") & r.mid.between(.05, .95)]
for mth, g in S.groupby(S.date.dt.to_period("M")):
    m, s = cse(g.resid, g.date); npl, nse = cse(g.no_pl, g.date)
    print(f"  {mth}: n={len(g):4d} resid {m*100:+.1f}c ±{1.96*s*100:.1f}  buy-NO {npl*100:+.1f}c ±{1.96*nse*100:.1f}")
print("\nOther slices (all cities, Aug 23+, 7 AM, mid 5-95c):")
S = r[(r.date >= "2026-08-23") & (r.snap == "morn_7am") & r.mid.between(.05, .95)]
for nm, g in [("weekend", S[S.weekend]), ("weekday", S[~S.weekend])] + [(f"band {lo}-{hi}", S[S.mid.between(lo, hi - 1e-9)]) for lo, hi in [(.05, .2), (.2, .35), (.35, .5), (.5, .7), (.7, .95)]]:
    m, s = cse(g.resid, g.date)
    print(f"  {nm:<14} n={len(g):4d} dates={g.date.nunique():3d} resid {m*100:+.1f}c ±{1.96*s*100:.1f}")

print("\n=== Trading check: buy NO at (1-bid)+fee by YES price band, Aug 23+ all cities, split by halves ===")
for snap in ["morn_7am", "eve_6pm"]:
    S = r[(r.date >= "2026-08-23") & (r.snap == snap)]
    for lo, hi in [(.05, .2), (.2, .35), (.35, .5), (.5, .7), (.7, .95)]:
        out = []
        for nm, g in [("all", S), ("Aug23-Oct5", S[S.date < "2026-10-06"]), ("Oct6-Nov19", S[S.date >= "2026-10-06"])]:
            g = g[g.mid.between(lo, hi - 1e-9)]
            m, s = cse(g.no_pl, g.date)
            out.append(f"{nm}: {m/g.no_cost.mean():+.1%} ±{1.96*s/g.no_cost.mean():.1%} (n{len(g)})")
        print(f"  {snap} YES {lo:.2f}-{hi:.2f}: " + " | ".join(out))
print("\nNew cities first 45 days, buy YES at ask+fee (post-hoc direction, 6 PM):")
S = r[(r.date >= "2026-08-27") & (~r.orig) & (r.age < 45) & (r.snap == "eve_6pm") & r.mid.between(.05, .95)]
m, s = cse(S.yes_pl, S.date); print(f"  n={len(S)} {m*100:+.1f}c/ctr ±{1.96*s*100:.1f} ({m/S.yes_cost.mean():+.1%}); mean spread {(S.yes_ask-S.yes_bid).mean()*100:.1f}c vs established {(r[r.orig & (r.date>='2026-08-27')].pipe(lambda x:(x.yes_ask-x.yes_bid)[x.mid.between(.05,.95)]).mean())*100:.1f}c")
