"""Do brand-new temperature markets start out mispriced?
Compares each newly launched city's first 45 days with established cities ON THE SAME DATES
(cancels weather/season). April 2026 launches (13 cities) vs the 7 main cities; Aug 2026 launches
(SAN, EWR, TTN, SDF highs + lows) vs the 11 'more' cities + main 7 lows on the same dates."""
import pandas as pd, numpy as np, os, glob
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(HERE)
def load(files, tag):
    fs = [pd.read_csv(f) for f in files if os.path.getsize(f) > 0]
    d = pd.concat(fs); d["grp"] = tag; return d
apr = load(glob.glob(os.path.join(HERE, "la[0-9].csv")), "new_apr")
aug = load(glob.glob(os.path.join(HERE, "lg[0-9].csv")), "new_aug")
main = pd.read_csv(os.path.join(P, "history.csv")); main["grp"] = "est_main"
more = pd.read_csv(os.path.join(P, "history_more.csv")); more = more[more.series != "KXRAIN"]; more["grp"] = "est_more"
d = pd.concat([apr, aug, main, more]).drop_duplicates(["ticker", "snap"])
d["kind"] = np.where(d.series.str.contains("LOW"), "low", "high")
d["date"] = pd.to_datetime(d.date)
d = d[(d.yes_ask < 1) & (d.yes_bid > 0)]
d["mid"] = (d.yes_bid + d.yes_ask) / 2; d["y"] = (d.result == "yes").astype(int)
d["spread"] = d.yes_ask - d.yes_bid
fy = np.ceil(0.07 * d.yes_ask * (1 - d.yes_ask) * 100 - 1e-9) / 100
nb = 1 - d.yes_bid; fn = np.ceil(0.07 * nb * (1 - nb) * 100 - 1e-9) / 100
d["yes_pl"] = d.y - d.yes_ask - fy; d["yc"] = d.yes_ask + fy
d["no_pl"] = (1 - d.y) - nb - fn; d["nc"] = nb + fn
d["brier"] = (d.y - d.mid) ** 2
first = d.groupby("series").date.transform("min"); d["age"] = (d.date - first).dt.days
g = d.groupby(["series", "date", "snap"])
d["favp"] = g.mid.transform("max"); d["is_fav"] = d.mid == d.favp
def cse(v, dt):
    v = pd.Series(np.asarray(v, float)); dt = np.asarray(dt); mu = v.mean()
    s = (v - mu).groupby(dt).sum(); return mu, np.sqrt((s ** 2).sum()) / max(len(v), 1)
def ev_brier(X):
    """per city-day multi-bucket Brier using normalised mids"""
    X = X.copy(); X["pn"] = X.mid / X.groupby(["series", "date", "snap"]).mid.transform("sum")
    X["b"] = (X.y - X.pn) ** 2
    return X.groupby(["series", "date", "snap"]).agg(b=("b", "sum"), date=("date", "first")).reset_index(drop=True)
def report(new, est, title):
    print(f"\n=== {title} ===")
    print(f"new: {new.series.nunique()} series, {new.date.nunique()} dates, {len(new)} prices | established same dates: {est.series.nunique()} series, {len(est)} prices")
    for lbl, X in [("new", new), ("est", est)]:
        eb = ev_brier(X); b, bs = cse(eb.b, eb.date)
        ls = X[X.mid < .35]; lr, lse = cse(ls.y - ls.mid, ls.date)
        fv = X[X.is_fav & X.mid.between(.5, .65)]; fr, fse = cse(fv.yes_pl, fv.date)
        nb_ = X[X.mid.between(.10, .35)]; nr, nse = cse(nb_.no_pl, nb_.date)
        print(f"  {lbl}: city-day Brier {b:.3f} ±{1.96*bs:.3f} | spread {X.spread.mean()*100:.1f}c | long-shot (<35c) won-minus-price {lr*100:+.1f}c ±{1.96*lse*100:.1f} "
              f"| fav 50-65c at ask {fr/fv.yc.mean() if len(fv) else np.nan:+.1%} ±{1.96*fse/fv.yc.mean() if len(fv) else np.nan:.1%} (n{len(fv)}) "
              f"| NO on 10-35c {nr/nb_.nc.mean():+.1%} ±{1.96*nse/nb_.nc.mean():.1%} (n{len(nb_)})")
for win in [(0, 14), (0, 45)]:
    A = d[(d.grp == "new_apr") & d.age.between(*win)]
    report(A, d[(d.grp == "est_main") & d.date.isin(A.date.unique())], f"April 2026 launches, days {win[0]}-{win[1]} vs 7 main cities")
    for k in ["high", "low"]:
        G = d[(d.grp == "new_aug") & (d.kind == k) & d.age.between(*win)]
        if len(G) == 0: continue
        E = d[(d.grp.isin(["est_more", "est_main"])) & (d.kind == k) & d.date.isin(G.date.unique()) & (d.date >= "2026-08-23")]
        report(G, E, f"Aug 2026 launches ({k}s), days {win[0]}-{win[1]} vs established {k}s")
