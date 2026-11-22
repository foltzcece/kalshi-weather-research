"""
Would cheaper limit orders have filled on past 'buy the favourite' trades, and would they
have made more money? For each past favourite priced 50-65c at a snapshot, we pretend to post
a YES buy order OFFSET cents under the ask and check Kalshi's trade history until the market
closed. A resting order fills when a later trade prints at our price or better.
Note: orders tend to fill when the price is falling, which often means the bet is losing
(adverse selection), so we compare returns on exactly the filled trades.
Usage: python3 limit_backtest.py [offset_cents ...]
"""
import csv, os, sys, math, time, collections, datetime as dt
from picks import KALSHI, get, kalshi_fee

HERE = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(HERE, os.environ.get("HISTORY_FILE", "history.csv")))))
CUTOFF = dt.date(2026, 9, 21)     # markets settled before this live in Kalshi's archive
CT = dt.timezone(dt.timedelta(hours=-6))
MAKER_RATE = 0.0175
SNAP_TS = {"eve_6pm": lambda d: dt.datetime.combine(d - dt.timedelta(days=1), dt.time(18), CT),
           "morn_7am": lambda d: dt.datetime.combine(d, dt.time(7), CT)}


def maker_fee(p):
    return math.ceil(MAKER_RATE * p * (1 - p) * 100 - 1e-9) / 100


def fav_trades():
    ev = collections.defaultdict(list)
    for r in rows:
        if 0 < float(r["yes_ask"]) <= 1:
            ev[(r["snap"], r["event"])].append(r)
    out = []
    for (snap, e), ms in ev.items():
        fav = max(ms, key=lambda r: float(r["yes_bid"]) + float(r["yes_ask"]))
        mid = (float(fav["yes_bid"]) + float(fav["yes_ask"])) / 2
        if 0.50 <= mid < 0.65 and float(fav["yes_ask"]) < 1:
            out.append(fav)
    return out


def min_price_after(ticker, date, start):
    """Lowest YES trade price from start until the end of the market's day."""
    end = int((dt.datetime.combine(date + dt.timedelta(days=1), dt.time(0), CT)).timestamp())
    base = f"{KALSHI}/historical/trades" if date < CUTOFF else f"{KALSHI}/markets/trades"
    low, cursor = None, ""
    for _ in range(8):
        d = get(f"{base}?ticker={ticker}&min_ts={start}&max_ts={end}&limit=1000" + (f"&cursor={cursor}" if cursor else ""))
        for t in d.get("trades", []):
            p = float(t["yes_price_dollars"])
            low = p if low is None else min(low, p)
        cursor = d.get("cursor")
        if not cursor or not d.get("trades"):
            break
        time.sleep(0.1)
    return low


def main(offsets):
    cache_path = os.path.join(HERE, "limit_cache.csv")
    cache = {}
    if os.path.exists(cache_path):
        cache = {(r["ticker"], r["snap"]): r["low"] for r in csv.DictReader(open(cache_path))}
    favs = fav_trades()
    for i, f in enumerate(favs):
        key = (f["ticker"], f["snap"])
        if key in cache:
            continue
        date = dt.date.fromisoformat(f["date"])
        start = int(SNAP_TS[f["snap"]](date).timestamp())
        try:
            low = min_price_after(f["ticker"], date, start)
        except Exception as e:
            print("!", f["ticker"], e, file=sys.stderr)
            continue
        cache[key] = "" if low is None else low
        if i % 50 == 0:
            print(f"{i}/{len(favs)}", file=sys.stderr)
            with open(cache_path, "w", newline="") as fh:
                w = csv.writer(fh); w.writerow(["ticker", "snap", "low"])
                w.writerows([[k[0], k[1], v] for k, v in cache.items()])
        time.sleep(0.1)
    with open(cache_path, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "snap", "low"])
        w.writerows([[k[0], k[1], v] for k, v in cache.items()])

    for snap in ("eve_6pm", "morn_7am"):
        fs = [f for f in favs if f["snap"] == snap and (f["ticker"], snap) in cache]
        print(f"\n=== {snap}: {len(fs)} past favourites priced 50-65c ===")
        cost = sum(float(f["yes_ask"]) + kalshi_fee(float(f["yes_ask"])) for f in fs)
        pay = sum(f["result"] == "yes" for f in fs)
        print(f"  pay the ask:        all {len(fs)} filled, return {(pay - cost) / cost:+.1%}")
        for off in offsets:
            filled = []
            for f in fs:
                low = cache[(f["ticker"], snap)]
                lim = round(float(f["yes_ask"]) - off / 100, 2)
                if low not in ("", None) and float(low) <= lim:
                    filled.append((f, lim))
            if not filled:
                print(f"  limit {off}c under ask: none filled"); continue
            c = sum(l + maker_fee(l) for _, l in filled)
            w = sum(f["result"] == "yes" for f, _ in filled)
            c_ask = sum(float(f["yes_ask"]) + kalshi_fee(float(f["yes_ask"])) for f, _ in filled)
            print(f"  limit {off}c under ask: filled {len(filled)}/{len(fs)} ({len(filled) / len(fs):.0%}), "
                  f"won {w / len(filled):.0%}, return {(w - c) / c:+.1%}  "
                  f"(same trades paying the ask: {(w - c_ask) / c_ask:+.1%})")


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]] or [1, 2, 3, 5])
