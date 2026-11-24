"""Test 3: lock harvesting on DAILY LOW markets (KXLOWT, 6 cities, Aug 31 - Nov 17 2026).
Rule check: official low = round(min of 5-min running mean of IEM 1-min temps), local standard day.
At the 7 AM CST snapshot (13:00 UTC), with data up to 15 min earlier (free-feed lag), buckets whose
whole range is above the low-so-far are dead. Report their snapshot yes bid (= what NO costs 1-bid)."""
import pandas as pd, numpy as np, os
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
z = np.load(os.path.join(P, "edge/days.npz"))
OFF = {"NYC": -5, "MDW": -6, "MIA": -5, "AUS": -6, "DEN": -7, "LAX": -8}
MAP = {"KXLOWTNYC": "NYC", "KXLOWTCHI": "MDW", "KXLOWTMIA": "MIA", "KXLOWTAUS": "AUS", "KXLOWTDEN": "DEN", "KXLOWTLAX": "LAX"}
T = {(s, d): t for s, d, t in zip(z["stn"], z["date"], z["temps"])}
h = pd.read_csv(os.path.join(P, "history_more.csv")); h = h[h.series.isin(MAP)]
def m5(t): return pd.Series(t).rolling(5).mean().values
ok = tot = 0; rows = []
for (ser, date), e in h[h.snap == "morn_7am"].groupby(["series", "date"]):
    stn = MAP[ser]; t = T.get((stn, date))
    if t is None: continue
    mm = m5(t); full = np.nanmin(mm)
    act = pd.to_numeric(e.actual, errors="coerce").dropna(); act = act.iloc[0] if len(act) else np.nan
    if np.isfinite(act): tot += 1; ok += int(round(full) == act)
    cut = (13 + OFF[stn]) * 60 - 15            # minutes after local std midnight
    if cut <= 5: continue
    R = round(np.nanmin(mm[:cut]))
    for _, r in e.iterrows():
        lo = r.floor + (1 if r.strike_type == "greater" else 0) if r.strike_type != "less" else -999
        dead = lo > R
        rows.append(dict(series=ser, date=date, ticker=r.ticker, dead=dead, bid=r.yes_bid, ask=r.yes_ask, result=r.result, R=R, cutmin=cut))
print(f"settle rule on lows: round(min 5-min mean) == actual on {ok}/{tot} days")
d = pd.DataFrame(rows); dd = d[d.dead]
print("dead buckets at 7 AM CST snapshot:", len(dd), " wrongly-dead (settled YES):", (dd.result == "yes").sum())
print("dead buckets with yes bid >= 3c:", (dd.bid >= 0.03).sum(), "on", dd[dd.bid >= .03].date.nunique(), "days")
print(dd[dd.bid >= 0.03].groupby("series").bid.agg(["size", "mean", "max"]))
x = dd[dd.bid >= .03]; fee = np.ceil(0.07 * x.bid * (1 - x.bid) * 100 - 1e-9) / 100
print(f"NO at 1-bid, 20 ctr each: profit ${(20*(x.bid - fee)).sum():.2f} on ${(20*(1-x.bid)).sum():.2f} staked")
d.to_csv(os.path.join(P, "ootb/low_lock_rows.csv"), index=False)
