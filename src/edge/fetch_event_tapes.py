"""Held-out extension: trades around every decided-bucket moment, 7 cities, Dec 2024 - Sep 21 2026
(the period before mm/trades.csv). Window = 30 min before to 6 h after the 1-min data decides the bucket.
Resumable. Output: event_tapes.csv"""
import csv, os, sys, time, threading, concurrent.futures as cf, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(HERE); sys.path.insert(0, P)
from picks import KALSHI, get
from lock_events import S2C, OFF, run_settle, first
z = np.load(os.path.join(HERE, "days.npz")); days = {(s, d): t for s, d, t in zip(z["stn"], z["date"], z["temps"])}
mk = {}
for fn in ["history.csv", "audit/history_oos.csv"]:
    for r in csv.DictReader(open(os.path.join(P, fn))):
        if r["series"] in S2C and r["date"] < "2026-09-22": mk[r["ticker"]] = r
jobs = []
for tk, r in mk.items():
    stn = S2C[r["series"]]
    if (stn, r["date"]) not in days: continue
    rm, s = run_settle(days[(stn, r["date"])])
    st = r["strike_type"]
    try:
        thr = float(r["cap"]) + 1 if st == "between" else float(r["cap"]) if st == "less" else float(r["floor"]) + 1
    except ValueError: continue
    m = first(s >= thr)
    if m is None: continue
    t0 = pd.Timestamp(r["date"], tz="UTC") - pd.Timedelta(hours=OFF[stn]) + pd.Timedelta(minutes=m)
    jobs.append((tk, r["series"], r["date"], r["result"], int(t0.timestamp()) - 1800, int(t0.timestamp()) + 6 * 3600))
OUT = os.path.join(HERE, "event_tapes.csv"); DONE = os.path.join(HERE, "event_tapes.done")
done = set(open(DONE).read().split()) if os.path.exists(DONE) else set()
f = open(OUT, "a", newline=""); w = csv.writer(f); df_ = open(DONE, "a")
if not done: w.writerow(["series", "ticker", "date", "result", "ts", "yes_price", "count", "taker_side"])
todo = [j for j in jobs if j[0] not in done]; lock = threading.Lock()
print(len(jobs), "decided buckets,", len(todo), "to fetch", flush=True)
def one(j):
    tk, s, d, res, a, b = j; base = f"{KALSHI}/historical/trades" if d < "2026-09-21" else f"{KALSHI}/markets/trades"
    rows = []; cur = ""
    try:
        for _ in range(200):
            x = get(f"{base}?ticker={tk}&limit=1000&min_ts={a}&max_ts={b}" + (f"&cursor={cur}" if cur else ""), tries=6)
            rows += [[s, tk, d, res, t["created_time"], t["yes_price_dollars"], t["count_fp"], t["taker_side"]] for t in x.get("trades", [])]
            cur = x.get("cursor")
            if not cur or not x.get("trades"): break
    except Exception as e:
        print("!", tk, e, flush=True); return
    with lock:
        w.writerows(rows); f.flush(); df_.write(tk + "\n"); df_.flush()
n = 0
with cf.ThreadPoolExecutor(6) as ex:
    for _ in ex.map(one, todo):
        n += 1
        if n % 500 == 0: print(n, flush=True)
print("done", flush=True)
