import pandas as pd, numpy as np, os
H = os.path.dirname(os.path.abspath(__file__))
d = pd.read_pickle(os.path.join(H, "implied.pkl")).sort_values(["event","h"])
OFF = {"AUS":-6,"CHI":-6,"DEN":-7,"LAX":-8,"MIA":-5,"NY":-5,"PHIL":-5,"TATL":-5,"TBOS":-5,"TDAL":-6,"TDC":-5,
       "THOU":-6,"TLV":-8,"TMIN":-6,"TOKC":-6,"TPHX":-7,"TSEA":-8,"TSFO":-8}
d["city"] = d.series.str.replace("KXHIGH","")
d["loc_t"] = d.h + pd.to_timedelta(d.city.map(OFF), unit="h")  # local standard time
day = pd.to_datetime(d.date).dt.tz_localize("UTC")
d["hrel"] = (d.loc_t - day).dt.total_seconds()/3600  # hours relative to local midnight of event day
d = d[(d.hrel >= -14) & (d.hrel <= 12)]          # 10 AM day before .. noon day-of (before most locks)
for k in (3, 6):
    d[f"m{k}"] = d.groupby("event")["mean"].diff(k)
d["period"] = np.where(d.date < "2026-09-22", "holdA_aug-sep(11c)", np.where(d.date <= "2026-10-20", "DISC_sep-oct", "holdB_oct-nov"))
d["win"] = pd.cut(d.hrel, [-14.1, 0, 7, 12], labels=["eve(10a-12a)", "night(0-7a)", "morn(7a-12p)"])
def slope(x, y, dates, B=400):
    ok = x.notna() & y.notna(); x, y, dates = x[ok].values, y[ok].values, dates[ok].values
    b = (x*y).sum()/(x*x).sum()
    ud = np.unique(dates); idx = {u: np.where(dates == u)[0] for u in ud}; rng = np.random.default_rng(0); bs = []
    for _ in range(B):
        ii = np.concatenate([idx[u] for u in rng.choice(ud, len(ud))]); bs.append((x[ii]*y[ii]).sum()/(x[ii]*x[ii]).sum())
    return b, np.percentile(bs, 2.5), np.percentile(bs, 97.5), ok.sum()
print("slope of (actual - implied mean) on past move. >0 = under-reaction (momentum), <0 = over-reaction")
for k in (3, 6):
    for per, s in d.groupby("period"):
        b, lo, hi, n = slope(s[f"m{k}"], s.err, s.date); print(f"k={k}h {per:22s} all     b={b:+.2f} [{lo:+.2f},{hi:+.2f}] n={n}")
        for w, s2 in s.groupby("win", observed=True):
            b, lo, hi, n = slope(s2[f"m{k}"], s2.err, s2.date); print(f"k={k}h {per:22s} {w:12s} b={b:+.2f} [{lo:+.2f},{hi:+.2f}] n={n}")
# lead-lag: neighbour move
NB = [("NY","PHIL"),("PHIL","TDC"),("NY","TBOS"),("AUS","THOU"),("AUS","TDAL"),("TDAL","TOKC"),("TDAL","THOU"),("CHI","TMIN"),("LAX","TLV"),("TPHX","TLV"),("LAX","TSFO")]
d = d.set_index(["city","date","h"])
rows = []
for a, b in NB:
    for x, y in ((a, b), (b, a)):
        try: dx = d.loc[x]; dy = d.loc[y]
        except KeyError: continue
        j = dy[["err","m3","period"]].join(dx[["m3"]].rename(columns={"m3":"nb3"}), how="inner")
        j["pair"] = f"{x}->{y}"; rows.append(j.reset_index())
j = pd.concat(rows)
print("\nlead-lag: slope of this city's error on NEIGHBOUR's past-3h move (controlling nothing)")
for per, s in j.groupby("period"):
    b, lo, hi, n = slope(s.nb3, s.err, s.date); print(f"{per:22s} b={b:+.2f} [{lo:+.2f},{hi:+.2f}] n={n}")
    r = s.err - s.m3*0  # residual after own move:
    bo = (s.m3*s.err).sum()/(s.m3**2).sum(); res = s.err - bo*s.m3
    b, lo, hi, n = slope(s.nb3, res, s.date); print(f"{per:22s} (after own move) b={b:+.2f} [{lo:+.2f},{hi:+.2f}]")
