"""Download all trades for KXLOWT (daily low) markets in history_more.csv (6 cities, Aug 23 - Nov 19 2026).
Output: ootb/low_trades.csv (resumable). Same format as mm/trades.csv."""
import csv, os, sys, time, threading, concurrent.futures as cf
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, P)
from picks import KALSHI, get
OUT = os.path.join(P, "ootb", "low_trades.csv")
mk = {r["ticker"]: (r["series"], r["date"], r["result"]) for r in csv.DictReader(open(os.path.join(P, "history_more.csv"))) if r["series"].startswith("KXLOWT")}
done = {r["ticker"] for r in csv.DictReader(open(OUT))} if os.path.exists(OUT) else set()
f = open(OUT, "a", newline=""); w = csv.writer(f)
if not done: w.writerow(["series", "ticker", "date", "result", "ts", "yes_price", "count", "taker_side"])
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
    with lock: w.writerows(rows); f.flush()
todo = [t for t in sorted(mk) if t not in done]
with cf.ThreadPoolExecutor(6) as ex:
    for i, _ in enumerate(ex.map(one, todo)):
        if i % 200 == 0: print(i, len(todo), file=sys.stderr, flush=True)
print("done", file=sys.stderr)
