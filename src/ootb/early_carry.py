"""High-temp buckets decided by MIDNIGHT CARRY-OVER (official high already passed the bucket before 2 AM local,
e.g. a warm evening ahead of a cold front). The edge/ capture test SKIPPED these (qc rule). Here we test only them.
Discovery: Sep 22 - Nov 19 2026 (mm/trades.csv). Held out: Dec 2024 - Sep 21 2026 (edge/event_tapes.csv, +6h after lock).
Usage: python3 early_carry.py TAPES START END"""
import csv, os, sys, numpy as np, pandas as pd
sys.path.insert(0, "/mnt/project-files/kalshi-model/edge")
from lock_events import S2C, OFF, run_settle, free_lower, first
P = "/mnt/project-files/kalshi-model"; tapes, START, END = sys.argv[1:4]
z = np.load(f"{P}/edge/days.npz"); days = {(s, d): t for s, d, t in zip(z["stn"], z["date"], z["temps"])}
mk = {}
for fn in ["history.csv", "audit/history_oos.csv"]:
    for r in csv.DictReader(open(f"{P}/{fn}")):
        if r["series"] in S2C and START <= r["date"] <= END: mk[r["ticker"]] = r
tr = pd.read_csv(tapes, usecols=["series", "ticker", "ts", "yes_price", "count", "taker_side"])
tr = tr[tr.ticker.isin(mk)]; tr["ts"] = pd.to_datetime(tr.ts, format="ISO8601", utc=True)
def despike(t):
    med = pd.Series(t).rolling(7, center=True, min_periods=4).median().to_numpy(); t = t.copy(); t[np.abs(t - med) > 3] = np.nan; return t
ev = []
for tk, g in tr.groupby("ticker"):
    r = mk[tk]; stn = S2C[r["series"]]
    if (stn, r["date"]) not in days: continue
    rm, s = run_settle(despike(days[(stn, r["date"])])); stt = r["strike_type"]
    thr = float(r["cap"]) + 1 if stt == "between" else float(r["cap"]) if stt == "less" else float(r["floor"]) + 1
    kind = "lock" if stt == "greater" else "dead"
    mf = first(s >= thr)
    if mf is None or mf >= 120 or mf < int(os.environ.get("MINMF", 0)): continue
    base = pd.Timestamp(r["date"], tz="UTC") - pd.Timedelta(hours=OFF[stn])
    right = "no" if kind == "dead" else "yes"
    gg = g[g.taker_side == right].copy(); gg["px"] = gg.yes_price if kind == "dead" else 1 - gg.yes_price
    win = (r["result"] == "no") if kind == "dead" else (r["result"] == "yes")
    ev.append((tk, r["date"], stn, mf, base + pd.Timedelta(minutes=mf), win, gg))
print(f"Period {START}..{END}: {len(ev)} early-decided buckets on {len({(e[1], e[2]) for e in ev})} city-days, rule correct {np.mean([e[5] for e in ev]):.1%}")
for e in ev:
    if not e[5]: print("   WRONG:", e[0], "decided at local min", e[3])
def sim(label, delay, minpx=0.03, maxc=20, share=0.25, horizon=360):
    rows = []
    for tk, d, stn, mf, tf, win, gg in ev:
        w = gg[(gg.ts >= tf + pd.Timedelta(minutes=delay)) & (gg.ts < tf + pd.Timedelta(minutes=horizon)) & (gg.px >= minpx)].sort_values("ts")
        got = pnl = cost = 0.0
        for px, c in zip(w.px, w["count"]):
            q = min(c * share, maxc - got)
            if q <= 0: break
            pnl += q * ((1.0 if win else 0.0) - (1 - px) - np.ceil(0.07 * px * (1 - px) * 100 - 1e-9) / 100); cost += q * (1 - px); got += q
        if got: rows.append((d, cost, pnl, win))
    if not rows: print(f"  {label:34s} no trades"); return
    df = pd.DataFrame(rows, columns=["d", "cost", "pnl", "win"]); byd = df.groupby("d")[["cost", "pnl"]].sum(); rng = np.random.default_rng(0)
    rr = [(lambda b: b.pnl / b.cost)(byd.iloc[rng.integers(0, len(byd), len(byd))].sum()) for _ in range(2000)]
    print(f"  {label:34s} buckets {len(df):3d} days {df.d.nunique():3d} staked ${df.cost.sum():6.0f} P&L ${df.pnl.sum():6.0f} "
          f"({df.pnl.sum()/df.cost.sum():+.1%} [{np.percentile(rr,2.5):+.1%},{np.percentile(rr,97.5):+.1%}]) losses {int((~df.win).sum())}")
for dly in (15, 30, 60, 120, 240): sim(f"act {dly} min after decided", dly)
sim("act 60 min, max 100 ctr", 60, maxc=100)
