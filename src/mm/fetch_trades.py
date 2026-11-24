"""Download every Kalshi trade (with taker side) for settled weather markets since 2026-09-22
(the live /markets/trades endpoint). Output: mm/trades.csv (resumable).
Each trade row tells us who crossed the spread (taker_side), so the other side was a resting maker."""
import csv, os, sys, time, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from picks import KALSHI, get
HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "trades.csv")
mk = {}
for r in csv.DictReader(open(os.path.join(PARENT, "history.csv"))):
    if r["date"] >= "2026-09-22": mk[r["ticker"]] = (r["series"], r["date"], r["result"])
for r in csv.DictReader(open(os.path.join(PARENT, "rain_candles.csv"))):
    if r["date"] >= "2026-09-22": mk[r["ticker"]] = ("KXRAIN", r["date"], r["result"])
done = set()
if os.path.exists(OUT):
    done = {r["ticker"] for r in csv.DictReader(open(OUT))}
f = open(OUT, "a", newline=""); w = csv.writer(f)
if not done: w.writerow(["series", "ticker", "date", "result", "ts", "yes_price", "count", "taker_side"])
todo = [t for t in sorted(mk) if t not in done]
import threading, concurrent.futures as cf
lock = threading.Lock()
def one(t):
    s, d, res = mk[t]; cursor = ""; rows = []
    try:
        for _ in range(60):
            j = get(f"{KALSHI}/markets/trades?ticker={t}&limit=1000" + (f"&cursor={cursor}" if cursor else ""))
            for x in j.get("trades", []):
                rows.append([s, t, d, res, x["created_time"], x["yes_price_dollars"], x["count_fp"], x["taker_side"]])
            cursor = j.get("cursor")
            if not cursor or not j.get("trades"): break
            time.sleep(0.05)
    except Exception as e:
        print("!", t, e, file=sys.stderr); return
    with lock:
        w.writerows(rows); f.flush()
with cf.ThreadPoolExecutor(6) as ex:
    for i, _ in enumerate(ex.map(one, todo)):
        if i % 100 == 0: print(i, len(todo), file=sys.stderr, flush=True)
print("done", file=sys.stderr)
