"""Multiple-testing check, step 1: rebuild per-bet rows (date, cost, pnl) for every live lead,
using exactly the rules already reported elsewhere in kalshi-model/ (no new tuning here).
Writes noise/lead_rows.csv (lead, unit, date, cost, pnl, price) for stats.py.
Research only. Usage: python3 noise/leads.py
"""
import csv, os, sys, numpy as np, pandas as pd
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(P, "edge")); sys.path.insert(0, os.path.join(P, "audit"))
from lock_events import S2C, OFF, run_settle, free_lower, first
import audit as AU

fee = lambda p: np.ceil(0.07 * p * (1 - p) * 100 - 1e-9) / 100
rows = []
def add(lead, unit, d, cost, pnl, price=np.nan):
    rows.append((lead, unit, str(d), float(cost), float(pnl), float(price)))

# ---------- 1-3. High-temp lock harvesting (same sim as edge/capture2.py, held-out Dec 2024 - Sep 21 2026) ----------
z = np.load(os.path.join(P, "edge/days.npz")); DAYS = {(s, d): t for s, d, t in zip(z["stn"], z["date"], z["temps"])}
START, END = "2024-12-01", "2026-09-21"
mk = {}
for fn in ["history.csv", "audit/history_oos.csv"]:
    for r in csv.DictReader(open(os.path.join(P, fn))):
        if r["series"] in S2C and START <= r["date"] <= END: mk[r["ticker"]] = r
tr = pd.read_csv(os.path.join(P, "edge/event_tapes.csv"), usecols=["series", "ticker", "ts", "yes_price", "count", "taker_side"])
tr = tr[tr.series.isin(S2C) & tr.ticker.isin(mk)]; tr["ts"] = pd.to_datetime(tr.ts, format="ISO8601", utc=True)
def despike(t):
    med = pd.Series(t).rolling(7, center=True, min_periods=4).median().to_numpy(); t = t.copy(); t[np.abs(t - med) > 3] = np.nan; return t
ev = []
for tk, g in tr.groupby("ticker"):
    r = mk[tk]; stn = S2C[r["series"]]
    if (stn, r["date"]) not in DAYS: continue
    rm, s = run_settle(despike(DAYS[(stn, r["date"])])); lb = free_lower(rm); stt = r["strike_type"]
    if stt == "between": kind, thr = "dead", float(r["cap"]) + 1
    elif stt == "less": kind, thr = "dead", float(r["cap"])
    else: kind, thr = "lock", float(r["floor"]) + 1
    mf = first(s >= thr)
    if mf is None: continue
    mfree = first(lb >= thr); base = pd.Timestamp(r["date"], tz="UTC") - pd.Timedelta(hours=OFF[stn])
    right = "no" if kind == "dead" else "yes"
    gg = g[g.taker_side == right].copy(); gg["px"] = gg.yes_price if kind == "dead" else 1 - gg.yes_price
    win = (r["result"] == "no") if kind == "dead" else (r["result"] == "yes")
    ev.append((tk, r["date"], mf, base + pd.Timedelta(minutes=mf), base + pd.Timedelta(minutes=mfree) if mfree is not None else None, win, gg))

def sim(lead, events, when, minpx=0.03, maxc=20, share=0.25, horizon=360):
    for tk, d, mf, tf, tfree, win, gg in events:
        t0 = when(tf, tfree)
        if t0 is None: continue
        w = gg[(gg.ts >= t0) & (gg.ts < tf + pd.Timedelta(minutes=horizon)) & (gg.px >= minpx)].sort_values("ts")
        got = pnl = cost = 0.0
        for px, c in zip(w.px, w["count"]):
            q = min(c * share, maxc - got)
            if q <= 0: break
            pnl += q * ((1.0 if win else 0.0) - (1 - px) - fee(px)); cost += q * (1 - px); got += q
        if got: add(lead, tk, d, cost, pnl, 1 - cost / got)   # price = avg stale YES-side price we sold at
m = pd.Timedelta(minutes=1)
day_ev = [e for e in ev if e[2] >= 120]       # qc: skip decided before 2 AM
carry_ev = [e for e in ev if e[2] < 120]      # midnight carry-over only
sim("highs_lock_fast2min", day_ev, lambda tf, tfree: tf + 2 * m)
sim("highs_lock_free", day_ev, lambda tf, tfree: tfree + 10 * m if tfree is not None else None)
sim("carry_over_60min", carry_ev, lambda tf, tfree: tf + 60 * m)

# ---------- 4. Daily-LOW lock harvesting (ootb/low_lock_events.csv, qc, 15-min free-feed latency) ----------
# Same loop as ootb/low_lock_tape.py (qc, latency 15, max 20 ctr), re-run here to also keep the average price.
LMAP = {"KXLOWTNYC": "NYC", "KXLOWTCHI": "MDW", "KXLOWTMIA": "MIA", "KXLOWTAUS": "AUS", "KXLOWTDEN": "DEN", "KXLOWTLAX": "LAX"}
lh = pd.read_csv(os.path.join(P, "history_more.csv")); lh = lh[lh.series.isin(LMAP)].drop_duplicates("ticker").set_index("ticker")
lt = pd.read_csv(os.path.join(P, "ootb/low_trades.csv")); lt["ts"] = pd.to_datetime(lt.ts, format="ISO8601", utc=True)
for tk, g in lt.groupby("ticker"):
    if tk not in lh.index: continue
    r = lh.loc[tk]; stn = LMAP[r.series]
    if (stn, r.date) not in DAYS: continue
    t = despike(DAYS[(stn, r.date)]); rm = pd.Series(t).rolling(5).mean().to_numpy()
    s = np.floor(np.fmin.accumulate(np.nan_to_num(rm, nan=999)) + 0.5)
    if r.strike_type == "between": kind, thr = "dead", r.floor - 1
    elif r.strike_type == "greater": kind, thr = "dead", r.floor
    else: kind, thr = "lock", r.cap - 1
    hit = s <= thr
    if not hit.any(): continue
    mm_ = int(np.argmax(hit))
    if mm_ < 120: continue
    tl = pd.Timestamp(r.date, tz="UTC") - pd.Timedelta(hours=OFF[stn]) + pd.Timedelta(minutes=mm_)
    correct = (r.result == "no") if kind == "dead" else (r.result == "yes")
    if kind == "dead": st = g[(g.taker_side == "no") & (g.yes_price >= 0.03) & (g.ts > tl)]; px = st.yes_price
    else: st = g[(g.taker_side == "yes") & (g.yes_price <= 0.97) & (g.ts > tl)]; px = 1 - st.yes_price
    x = st[st.ts > tl + pd.Timedelta(minutes=15)]
    if not len(x): continue
    q = (0.25 * x["count"]).cumsum().clip(upper=20); take = q.diff().fillna(q).values; p = px.loc[x.index].values
    cost = float((take * (1 - p)).sum())
    if cost > 0: add("lows_lock_free15", tk, r.date, cost, float((take * ((1.0 if correct else 0.0) - (1 - p) - fee(p))).sum()), float((take * p).sum() / take.sum()))

# ---------- 5-7. Favourite 50-65c + limit, and limit vs paying the ask (audit/audit.py rules) ----------
ins, extra, oos = AU.load_all()
def fav_rows(lead, xs, paired=False):
    for x in xs:
        if not (0.50 <= x["mid"] < 0.65 and x["ask"] < 1 and x["has_low"]): continue
        t = AU.trade(x)
        if paired:   # profit per chance: limit rule minus paying the ask (0 if limit didn't fill)
            a = AU.trade(x, off=0); pl = (t[1] - t[0]) if t else 0.0
            add(lead, x["series"] + x["snap"], x["date"], 1.0, pl - (a[1] - a[0]))
        elif t: add(lead, x["series"] + x["snap"], x["date"], t[0], t[1] - t[0], t[0])
fav_rows("fav_limit_untouched", oos + extra)
fav_rows("fav_limit_tuning_year", ins)
fav_rows("limit_minus_ask_untouched", oos + extra, paired=True)

# ---------- 8-9. Rain NO when YES mid 50-70c (fall, Aug 23 - Nov 19 2026) ----------
rc = pd.read_csv(os.path.join(P, "rain_candles.csv")); rc = rc[(rc.bid > 0) & (rc.ask < 1)]
rc["mid"] = (rc.bid + rc.ask) / 2; rc = rc[rc.mid.between(0.50, 0.70)].sort_values("hour_utc")
for (tk, d), g in rc.groupby(["ticker", "date"]):          # first qualifying hour per city-day
    b = g.iloc[0].bid; c = 1 - b + fee(b); add("rain_no_hourly", tk, d, c, (g.iloc[0].result == "no") - c, b)
hm = pd.read_csv(os.path.join(P, "history_more.csv")); hm = hm[(hm.series == "KXRAIN") & (hm.snap == "morn_7am") & (hm.yes_bid > 0) & (hm.yes_ask < 1)]
hm = hm[((hm.yes_bid + hm.yes_ask) / 2).between(0.50, 0.70)]
for _, r in hm.iterrows():
    c = 1 - r.yes_bid + fee(r.yes_bid); add("rain_no_7am", r.ticker, r.date, c, (r.result == "no") - c, r.yes_bid)

out = pd.DataFrame(rows, columns=["lead", "unit", "date", "cost", "pnl", "price"])
out.to_csv(os.path.join(H, "lead_rows.csv"), index=False)
print(out.groupby("lead").agg(n=("pnl", "size"), days=("date", "nunique"), cost=("cost", "sum"), pnl=("pnl", "sum")).assign(ret=lambda d: d.pnl / d.cost))
