"""Download full Kalshi trade tapes (with taker side) for execution research.
  extra : 11 extra cities' daily-high buckets (history_more.csv) priced 20-85c at a snapshot -> exec/tapes_extra.csv
  year  : main 7 cities' buckets priced 20-85c at a snapshot, settled before 2026-09-22
          (older than mm/trades.csv) -> exec/tapes_year.csv
Resumable. Usage: python3 exec/fetch_tapes.py extra|year
Research only: does not touch the live pick scripts."""
import csv, os, sys, time, threading, concurrent.futures as cf, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
sys.path.insert(0, PARENT)
from picks import KALSHI, get

CUTOFF = "2026-09-21"
which = sys.argv[1]
src = "history_more.csv" if which == "extra" else "history.csv"
OUT = os.path.join(HERE, f"tapes_{which}.csv")
mk = {}
for r in csv.DictReader(open(os.path.join(PARENT, src))):
    if which == "extra" and "HIGHT" not in r["series"]:
        continue
    if which == "year" and r["date"] >= "2026-09-22":
        continue
    mid = (float(r["yes_bid"]) + float(r["yes_ask"])) / 2
    if 0.2 <= mid <= 0.85:
        mk[r["ticker"]] = (r["series"], r["date"], r["result"])
done = set()
if os.path.exists(OUT):
    done = {r["ticker"] for r in csv.DictReader(open(OUT))}
f = open(OUT, "a", newline=""); w = csv.writer(f)
if not done:
    w.writerow(["series", "ticker", "date", "result", "ts", "yes_price", "count", "taker_side"])
todo = [t for t in sorted(mk) if t not in done]
lock = threading.Lock()


def one(t):
    s, d, res = mk[t]; cursor = ""; rows = []
    base = f"{KALSHI}/historical/trades" if d < CUTOFF else f"{KALSHI}/markets/trades"
    try:
        for _ in range(80):
            j = get(f"{base}?ticker={t}&limit=1000" + (f"&cursor={cursor}" if cursor else ""), tries=6)
            for x in j.get("trades", []):
                rows.append([s, t, d, res, x["created_time"], x["yes_price_dollars"], x["count_fp"], x["taker_side"]])
            cursor = j.get("cursor")
            if not cursor or not j.get("trades"):
                break
            time.sleep(0.05)
    except Exception as e:
        print("!", t, e, file=sys.stderr, flush=True); return
    with lock:
        w.writerows(rows); f.flush()


print(which, "todo", len(todo), file=sys.stderr, flush=True)
with cf.ThreadPoolExecutor(4) as ex:
    for i, _ in enumerate(ex.map(one, todo)):
        if i % 200 == 0:
            print(i, len(todo), dt.datetime.now().strftime("%H:%M"), file=sys.stderr, flush=True)
print("done", file=sys.stderr, flush=True)
