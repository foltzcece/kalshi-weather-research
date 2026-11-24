"""Snapshot the live order book for open weather markets: spread and size resting at the best bid/ask.
Appends to mm/depth.csv so repeated runs build a picture across times of day."""
import csv, os, sys, datetime as dt, statistics as st
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from picks import KALSHI, get, CITIES
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "depth.csv")
now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
rows = []
for s in list(CITIES) + ["KXRAIN"]:
    ms = get(f"{KALSHI}/markets?series_ticker={s}&status=open&limit=200")["markets"]
    for m in ms:
        ob = get(f"{KALSHI}/markets/{m['ticker']}/orderbook").get("orderbook_fp", {})
        yes = [(float(p), float(q)) for p, q in ob.get("yes_dollars") or []]
        no = [(float(p), float(q)) for p, q in ob.get("no_dollars") or []]
        if not yes or not no: continue
        bid, bq = max(yes); nb, nq = max(no); ask = round(1 - nb, 2)
        mid = (bid + ask) / 2
        within = lambda lv, ref: sum(q for p, q in lv if p >= ref - 0.03 - 1e-9)
        rows.append([now, s, m["ticker"], bid, ask, bq, nq, within(yes, bid), within(no, nb), mid])
new = not os.path.exists(OUT)
with open(OUT, "a", newline="") as f:
    w = csv.writer(f)
    if new: w.writerow(["snap_utc", "series", "ticker", "bid", "ask", "bid_size", "ask_size", "bid_depth_3c", "ask_depth_3c", "mid"])
    w.writerows(rows)
live = [r for r in rows if 0.1 <= r[9] <= 0.9]
for k, f in (("high", lambda r: r[1] != "KXRAIN"), ("rain", lambda r: r[1] == "KXRAIN")):
    L = [r for r in live if f(r)]
    if L:
        sizes = [r[5] for r in L] + [r[6] for r in L]; depth = [r[7] for r in L] + [r[8] for r in L]
        print(f"{k}: {len(L)} markets priced 10-90c, median spread {100 * st.median(r[4] - r[3] for r in L):.0f}c, "
              f"median size at best price {st.median(sizes):.0f} ctr, median size within 3c {st.median(depth):.0f} ctr")
