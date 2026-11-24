"""Speed-edge capture test, parameterised (see capture.py for the method).
Usage: python3 capture2.py TAPES_CSV START END
Variants fixed BEFORE looking at the held-out months (Dec 2024 - Sep 21 2026):
  base : rule exactly as found on Sep 22 - Nov 19 2026
  qc   : + spike filter (drop a 1-min reading >3F away from the median of the 7 minutes around it)
         + skip buckets decided before 2 AM local (cold-front midnight carry-over, the NYC Nov 13 loss)"""
import csv, os, sys, numpy as np, pandas as pd
from lock_events import S2C, OFF, run_settle, free_lower, first
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(HERE)
tapes, START, END = sys.argv[1], sys.argv[2], sys.argv[3]
z = np.load(os.path.join(HERE, "days.npz")); days = {(s, d): t for s, d, t in zip(z["stn"], z["date"], z["temps"])}
mk = {}
for fn in ["history.csv", "audit/history_oos.csv"]:
    for r in csv.DictReader(open(os.path.join(P, fn))):
        if r["series"] in S2C and START <= r["date"] <= END: mk[r["ticker"]] = r
tr = pd.read_csv(tapes, usecols=["series", "ticker", "ts", "yes_price", "count", "taker_side"])
tr = tr[tr.series.isin(S2C) & tr.ticker.isin(mk)]; tr["ts"] = pd.to_datetime(tr.ts, format="ISO8601", utc=True)
def despike(t):
    med = pd.Series(t).rolling(7, center=True, min_periods=4).median().to_numpy()
    t = t.copy(); t[np.abs(t - med) > 3] = np.nan; return t
def events(qc):
    ev = []
    for tk, g in tr.groupby("ticker"):
        r = mk[tk]; stn = S2C[r["series"]]
        if (stn, r["date"]) not in days: continue
        t = days[(stn, r["date"])]
        if qc: t = despike(t)
        rm, s = run_settle(t); lb = free_lower(rm); stt = r["strike_type"]
        if stt == "between": kind, thr = "dead", float(r["cap"]) + 1
        elif stt == "less": kind, thr = "dead", float(r["cap"])
        else: kind, thr = "lock", float(r["floor"]) + 1
        mf = first(s >= thr)
        if mf is None or (qc and mf < 120): continue
        mfree = first(lb >= thr); base = pd.Timestamp(r["date"], tz="UTC") - pd.Timedelta(hours=OFF[stn])
        right = "no" if kind == "dead" else "yes"
        gg = g[g.taker_side == right].copy(); gg["px"] = gg.yes_price if kind == "dead" else 1 - gg.yes_price
        win = (r["result"] == "no") if kind == "dead" else (r["result"] == "yes")
        ev.append((tk, r["date"], kind, base + pd.Timedelta(minutes=mf), base + pd.Timedelta(minutes=mfree) if mfree is not None else None, win, gg))
    return ev
def sim(ev, label, when, minpx=0.03, share=0.25, maxc=100, horizon=360, maxpx=1.0):
    rows = []
    for tk, d, kind, tf, tfree, win, gg in ev:
        t0 = when(tf, tfree)
        if t0 is None: continue
        w = gg[(gg.ts >= t0) & (gg.ts < tf + pd.Timedelta(minutes=horizon)) & (gg.px >= minpx) & (gg.px <= maxpx)].sort_values("ts")
        got = pnl = cost = 0.0
        for px, c in zip(w.px, w["count"]):
            q = min(c * share, maxc - got)
            if q <= 0: break
            pnl += q * ((1.0 if win else 0.0) - (1 - px) - 0.07 * px * (1 - px)); cost += q * (1 - px); got += q
        if got: rows.append((d, got, cost, pnl, win))
    if not rows: print(f"  {label:44s} no trades"); return
    df = pd.DataFrame(rows, columns=["d", "ctr", "cost", "pnl", "win"]); byd = df.groupby("d")[["cost", "pnl"]].sum()
    rng = np.random.default_rng(0); rr = []
    for _ in range(2000):
        b = byd.iloc[rng.integers(0, len(byd), len(byd))].sum(); rr.append(b.pnl / b.cost)
    print(f"  {label:44s} buckets {len(df):4d} on {df.d.nunique():3d} days  staked ${df.cost.sum():7.0f}  P&L ${df.pnl.sum():6.0f} "
          f"({df.pnl.sum()/df.cost.sum():+.1%}, 95% [{np.percentile(rr,2.5):+.1%},{np.percentile(rr,97.5):+.1%}])  "
          f"losses {int((~df.win).sum())}  per active day ${df.pnl.sum()/df.d.nunique():.1f}")
m = pd.Timedelta(minutes=1)
print(f"Period {START} .. {END}, tapes {os.path.basename(tapes)}")
for qc in (False, True):
    ev = events(qc); print(f"{'qc' if qc else 'base'}: {len(ev)} decided buckets with trades, rule correct {np.mean([e[5] for e in ev]):.2%}")
    for L in (1, 2, 5, 10, 30):
        sim(ev, f"fast feed, act {L} min after", lambda tf, tfree, L=L: tf + L * m)
    sim(ev, "fast feed 2 min, only stale >=5c", lambda tf, tfree: tf + 2 * m, minpx=0.05)
    sim(ev, "fast feed 2 min, max 20 contracts/bucket", lambda tf, tfree: tf + 2 * m, maxc=20)
    sim(ev, "free feed, 10 min after it proves it", lambda tf, tfree: tfree + 10 * m if tfree is not None else None)
