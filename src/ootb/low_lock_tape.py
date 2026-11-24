"""Lock harvesting on daily LOW markets, using full trade tapes (ootb/low_trades.csv).
Official low = round(min 5-min running mean of IEM 1-min temps), local standard day (337/345 days match).
A bucket is decided once the running low passes its edge:
  dead  : between [f,c] once low <= f-1 ; 'greater' (>= f+1) once low <= f
  locked: 'less' (<= c-1) once low <= c-1
qc = despike (>3F from 7-min median) and skip buckets decided before 2 AM local (day-boundary risk).
Sim (same as edge/capture2.py): after lock + latency, take 25% of each later print on the stale side
(YES bid hit at >=3c for dead, i.e. taker_side=no; NO bid hit at yes<=97c for locked), max 20 ctr/bucket,
taker fee, settle at real result."""
import pandas as pd, numpy as np, os, sys
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFF = {"NYC": -5, "MDW": -6, "MIA": -5, "AUS": -6, "DEN": -7, "LAX": -8}
MAP = {"KXLOWTNYC": "NYC", "KXLOWTCHI": "MDW", "KXLOWTMIA": "MIA", "KXLOWTAUS": "AUS", "KXLOWTDEN": "DEN", "KXLOWTLAX": "LAX"}
z = np.load(os.path.join(P, "edge/days.npz")); D = {(s, d): t for s, d, t in zip(z["stn"], z["date"], z["temps"])}
h = pd.read_csv(os.path.join(P, "history_more.csv")); h = h[h.series.isin(MAP)].drop_duplicates("ticker").set_index("ticker")
tr = pd.read_csv(os.path.join(P, "ootb/low_trades.csv")); tr["ts"] = pd.to_datetime(tr.ts, format="ISO8601", utc=True)
fee = lambda p: np.ceil(0.07 * p * (1 - p) * 100 - 1e-9) / 100
def despike(t):
    med = pd.Series(t).rolling(7, center=True, min_periods=4).median().to_numpy(); t = t.copy(); t[np.abs(t - med) > 3] = np.nan; return t
ev = []
for tk, g in tr.groupby("ticker"):
    if tk not in h.index: continue
    r = h.loc[tk]; stn = MAP[r.series]
    if (stn, r.date) not in D: continue
    for qc in (False, True):
        t = D[(stn, r.date)]; t = despike(t) if qc else t
        rm = pd.Series(t).rolling(5).mean().to_numpy()
        s = np.floor(np.fmin.accumulate(np.nan_to_num(rm, nan=999)) + 0.5)
        if r.strike_type == "between": kind, thr = "dead", r.floor - 1
        elif r.strike_type == "greater": kind, thr = "dead", r.floor
        else: kind, thr = "lock", r.cap - 1
        hit = s <= thr
        if not hit.any(): continue
        m = int(np.argmax(hit))
        if qc and m < 120: continue
        base = pd.Timestamp(r.date, tz="UTC") - pd.Timedelta(hours=OFF[stn]); tl = base + pd.Timedelta(minutes=m)
        correct = (r.result == "no") if kind == "dead" else (r.result == "yes")
        if kind == "dead": st = g[(g.taker_side == "no") & (g.yes_price >= 0.03) & (g.ts > tl)]; px = st.yes_price
        else: st = g[(g.taker_side == "yes") & (g.yes_price <= 0.97) & (g.ts > tl)]; px = 1 - st.yes_price
        first = (st.ts.min() - tl).total_seconds() / 60 if len(st) else np.nan
        row = dict(ticker=tk, stn=stn, date=r.date, qc=qc, kind=kind, lock_min=m, correct=correct, first_hit_min=first,
                   stale_ctr=st["count"].sum())
        for lat in (2, 10, 15, 30):
            x = st[st.ts > tl + pd.Timedelta(minutes=lat)]; q = (0.25 * x["count"]).cumsum().clip(upper=20); take = q.diff().fillna(q).values
            p = px.loc[x.index].values; pay = 1.0 if correct else 0.0
            row[f"pnl_{lat}"] = float((take * (pay - (1 - p) - fee(p))).sum()) if len(x) else 0.0
            row[f"cost_{lat}"] = float((take * (1 - p)).sum()) if len(x) else 0.0
        ev.append(row)
e = pd.DataFrame(ev); e.to_csv(os.path.join(P, "ootb/low_lock_events.csv"), index=False)
for qc, s in e.groupby("qc"):
    print(f"\n== {'qc' if qc else 'base'}: {len(s)} decided buckets, rule correct {s.correct.mean():.2%}, "
          f"stale bid hit after lock on {(s.stale_ctr > 0).sum()}, median first hit {s.first_hit_min.median():.1f} min, median stale ctr {s.stale_ctr[s.stale_ctr>0].median():.0f}")
    print("lock time (local std):", (s.lock_min // 60).value_counts().sort_index().to_dict())
    for lat in (2, 10, 15, 30):
        c = s[f"cost_{lat}"].sum(); pnl = s[f"pnl_{lat}"].sum()
        print(f"  latency {lat:2d} min: ${pnl:8.2f} on ${c:8.2f} staked ({pnl / c * 100 if c else 0:+.1f}%/$), days with fills {s[s[f'cost_{lat}'] > 0].date.nunique()}, losing buckets {(s[f'pnl_{lat}'] < 0).sum()}")
