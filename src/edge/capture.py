"""Speed-edge capture simulation on decided buckets (dead = can no longer win; lock = already won).
After decision time (event + latency) we act as TAKER only on trades where someone else took the same
'right' side (NO on a dead bucket, YES on a locked one) at a stale price: proof that a stale quote was
there. We assume we would have got CAP_SHARE of each such print, at most MAX_CTR per bucket.
P&L uses the real Kalshi result (so rule failures count) and the taker fee 0.07*p*(1-p)."""
import csv, os, numpy as np, pandas as pd
from lock_events import S2C, OFF, run_settle, free_lower, first
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(HERE)
CAP_SHARE, MAX_CTR = 0.25, 100
z = np.load(os.path.join(HERE, "days.npz")); days = {(s, d): t for s, d, t in zip(z["stn"], z["date"], z["temps"])}
mk = {r["ticker"]: r for r in csv.DictReader(open(os.path.join(P, "history.csv"))) if r["series"] in S2C and r["date"] >= "2026-09-22"}
tr = pd.read_csv(os.path.join(P, "mm", "trades.csv"), usecols=["series", "ticker", "ts", "yes_price", "count", "taker_side"])
tr = tr[tr.series.isin(S2C)]; tr["ts"] = pd.to_datetime(tr.ts, format="ISO8601", utc=True)
ev = []
for tk, g in tr.groupby("ticker"):
    r = mk.get(tk)
    if r is None or (S2C[r["series"]], r["date"]) not in days: continue
    stn = S2C[r["series"]]; t = days[(stn, r["date"])]; rm, s = run_settle(t); lb = free_lower(rm)
    stt = r["strike_type"]
    if stt == "between": kind, thr = "dead", float(r["cap"]) + 1
    elif stt == "less": kind, thr = "dead", float(r["cap"])
    else: kind, thr = "lock", float(r["floor"]) + 1
    mf = first(s >= thr)
    if mf is None: continue
    mfree = first(lb >= thr); base = pd.Timestamp(r["date"], tz="UTC") - pd.Timedelta(hours=OFF[stn])
    right = "no" if kind == "dead" else "yes"
    gg = g[g.taker_side == right].copy()
    gg["px"] = gg.yes_price if kind == "dead" else 1 - gg.yes_price    # stale price of the wrong side we sell into
    win = (r["result"] == "no") if kind == "dead" else (r["result"] == "yes")
    ev.append((tk, r["date"], kind, base + pd.Timedelta(minutes=mf),
               base + pd.Timedelta(minutes=mfree) if mfree is not None else None, win, gg))
print(len(ev), "decided buckets; rule correct on", f"{np.mean([e[5] for e in ev]):.1%}")
def sim(label, when, minpx=0.03):
    rows = []
    for tk, d, kind, tf, tfree, win, gg in ev:
        t0 = when(tf, tfree)
        if t0 is None: continue
        w = gg[(gg.ts >= t0) & (gg.px >= minpx)].sort_values("ts")
        got = 0.0; pnl = 0.0; cost = 0.0
        for px, c in zip(w.px, w["count"]):
            q = min(c * CAP_SHARE, MAX_CTR - got)
            if q <= 0: break
            price_right = 1 - px                    # what we pay for the right side
            fee = 0.07 * px * (1 - px)
            pnl += q * ((1.0 if win else 0.0) - price_right - fee); cost += q * price_right; got += q
        if got: rows.append((d, got, cost, pnl, win))
    if not rows: print(f"{label:38s} no trades"); return
    df = pd.DataFrame(rows, columns=["d", "ctr", "cost", "pnl", "win"])
    byd = df.groupby("d")[["cost", "pnl"]].sum(); rng = np.random.default_rng(0)
    bs = [byd.iloc[rng.integers(0, len(byd), len(byd))].sum() for _ in range(2000)]
    rr = np.array([b.pnl / b.cost for b in bs])
    print(f"{label:38s} buckets {len(df):4d}  contracts {df.ctr.sum():7.0f}  staked ${df.cost.sum():7.0f}  "
          f"P&L ${df.pnl.sum():6.0f} ({df.pnl.sum()/df.cost.sum():+.2%}, 95% [{np.percentile(rr,2.5):+.2%},{np.percentile(rr,97.5):+.2%}])"
          f"  per day ${df.pnl.sum()/df.d.nunique():.1f}  losses {int((~df.win).sum())}")
m = pd.Timedelta(minutes=1)
for L in [1, 2, 5, 10, 30, 60]:
    sim(f"fast 1-min feed, act {L} min after", lambda tf, tfree, L=L: tf + L * m)
for L in [10, 20]:
    sim(f"free feed, act {L} min after it proves it", lambda tf, tfree, L=L: tfree + L * m if tfree is not None else None)
sim("fast feed 2 min, only stale price >=5c", lambda tf, tfree: tf + 2 * m, 0.05)
sim("free feed +10 min, only stale >=5c", lambda tf, tfree: tfree + 10 * m if tfree is not None else None, 0.05)
