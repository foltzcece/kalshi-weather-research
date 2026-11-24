"""Pre-registered slice scan for mispricing in Kalshi temperature markets.
Discovery = 7 main cities, dates before 2026-08-01. Holdouts = 7 main cities Aug 1-Nov 19 (later time),
11 extra cities' highs (unseen cities), lows (unseen market type), and newly launched cities.
Standard errors are clustered by date (all cities on one date count as one draw), because weather and
trader mood are shared across cities on a day. Bonferroni threshold over every test run."""
import pandas as pd, numpy as np, os, sys
from math import erf, sqrt
HERE = os.path.dirname(os.path.abspath(__file__))
d = pd.read_csv(os.path.join(HERE, "temp_rows.csv"), parse_dates=["date"])
d["resid"] = d.y - d.mid
d["resid_n"] = d.y - d.pn
K = ["series", "date", "snap"]
fav = d[d.is_fav == 1].groupby(K).first()
E = pd.DataFrame({
    "fav_resid": fav.y - fav.mid,
    "warm_resid": d[d.warm == 1].groupby(K).resid_n.sum(),
    "tail_resid": d[d["tail"] == 1].groupby(K).resid.sum(),
    "err": fav.actual - fav.imean,
}).reset_index()
meta = fav[["src", "kind", "city", "weekend", "holiday", "month", "chg", "anom", "favp", "isd", "dow"]].reset_index()
E = E.merge(meta, on=K)
E["tail_resid"] = E.tail_resid.fillna(0)

def season(m): return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
                       6: "summer", 7: "summer", 8: "summer"}.get(m, "fall")

def slice_masks(X):
    m = {"ALL": np.ones(len(X), bool), "weekend": X.weekend == 1, "weekday": X.weekend == 0,
         "holiday": X.holiday == 1, "monday": X.dow == 0, "friday": X.dow == 4,
         "snap_eve": X.snap == "eve_6pm", "snap_morn": X.snap == "morn_7am",
         "front_|chg|>=8F": X.chg.abs() >= 8, "warmup_chg>=6F": X.chg >= 6, "cooldown_chg<=-6F": X.chg <= -6,
         "steady_|chg|<2F": X.chg.abs() < 2,
         "hot_anom>=8F": X.anom >= 8, "cold_anom<=-8F": X.anom <= -8,
         "uncertain_fav<35c": X.favp < 0.35, "confident_fav>=55c": X.favp >= 0.55}
    for s in ["winter", "spring", "summer", "fall"]:
        m["season_" + s] = X.month.map(season) == s
    for c in sorted(X.city.unique()):
        m["city_" + c] = X.city == c
    return m

def clustered(vals, dates):
    """mean and date-clustered SE"""
    v = pd.Series(np.asarray(vals, float)); dts = pd.Series(np.asarray(dates))
    ok = v.notna(); v, dts = v[ok], dts[ok]
    n = len(v)
    if n < 20: return np.nan, np.nan, n, dts.nunique()
    mu = v.mean()
    s = (v - mu).groupby(dts.values).sum()
    return mu, sqrt((s ** 2).sum()) / n, n, dts.nunique()

STATS = ["fav_resid", "warm_resid", "tail_resid", "err"]
SETS = {
    "disc": (E.src == "main7") & (E.date < "2026-08-01"),
    "hold_time": (E.src == "main7") & (E.date >= "2026-08-01"),
    "hold_cities": (E.src == "more") & (E.kind == "high"),
    "hold_lows": (E.src == "more") & (E.kind == "low"),
}
if (E.src == "launch_apr").any(): SETS["launch_apr"] = (E.src == "launch_apr")
if (E.src == "launch_aug").any(): SETS["launch_aug"] = (E.src == "launch_aug")

rows = []
for setname, sm in SETS.items():
    X = E[sm]
    for sl, mk in slice_masks(X).items():
        Y = X[mk.values] if hasattr(mk, "values") else X[mk]
        for st in STATS:
            mu, se, n, nd = clustered(Y[st], Y.date)
            rows.append(dict(set=setname, slice=sl, stat=st, mean=mu, se=se, z=mu / se if se else np.nan, n=n, dates=nd))
R = pd.DataFrame(rows)
# Row-level: bucket position (offset from favourite) and tails, residual vs mid
d["side"] = np.where(d.offset > 0, "warmer", np.where(d.offset < 0, "colder", "fav"))
rrows = []
for setname, sm0 in SETS.items():
    src_mask = {"disc": (d.src == "main7") & (d.date < "2026-08-01"), "hold_time": (d.src == "main7") & (d.date >= "2026-08-01"),
                "hold_cities": (d.src == "more") & (d.kind == "high"), "hold_lows": (d.src == "more") & (d.kind == "low"),
                "launch_apr": d.src == "launch_apr", "launch_aug": d.src == "launch_aug"}[setname]
    X = d[src_mask & (d.yes_ask < 1)]
    for off in [-2, -1, 1, 2]:
        Y = X[(X.offset == off)]
        mu, se, n, nd = clustered(Y.resid, Y.date)
        rrows.append(dict(set=setname, slice=f"offset{off:+d}", stat="bucket_resid", mean=mu, se=se, z=mu / se if se else np.nan, n=n, dates=nd))
    for nm, Y in [("tail_lo_bucket", X[X.strike_type == "less"]), ("tail_hi_bucket", X[X.strike_type == "greater"]),
                  ("lowvol_0", X[X.volume == 0]), ("mid_10to35_lowvol", X[(X.volume == 0) & X.mid.between(.10, .35)])]:
        mu, se, n, nd = clustered(Y.resid, Y.date)
        rrows.append(dict(set=setname, slice=nm, stat="bucket_resid", mean=mu, se=se, z=mu / se if se else np.nan, n=n, dates=nd))
R = pd.concat([R, pd.DataFrame(rrows)])
R.to_csv(os.path.join(HERE, "slice_results.csv"), index=False)
D = R[R.set == "disc"].dropna(subset=["z"])
ntest = len(D)
from statistics import NormalDist
zcrit = NormalDist().inv_cdf(1 - 0.025 / ntest)
print(f"Discovery tests: {ntest}; Bonferroni |z| threshold {zcrit:.2f}")
D = D.assign(az=D.z.abs()).sort_values("az", ascending=False)
H = R[R.set != "disc"].set_index(["slice", "stat", "set"])
print(f"\nTop 25 discovery slices (all) and their holdout z-scores:")
for _, r in D.head(25).iterrows():
    hs = []
    for hs_name in [s for s in SETS if s != "disc"]:
        try:
            h = H.loc[(r.slice, r.stat, hs_name)]; hs.append(f"{hs_name}:{h["mean"]:+.3f}(z{h.z:+.1f},n{h.n})")
        except KeyError: pass
    flag = "PASS" if r.az >= zcrit else "    "
    print(f"{flag} {r.slice:<22}{r.stat:<12} {r['mean']:+.3f} z{r.z:+.1f} n{r.n} d{r.dates} | " + "  ".join(hs))
