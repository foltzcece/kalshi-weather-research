"""
Deep check of the 'buy the favourite' strategy on history.csv, split by season, by
recency and by city, with how sure we can be (standard error) for each slice.
Usage: python3 analyze_favorite.py
"""
import csv, math, os, collections
from picks import kalshi_fee

HERE = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(HERE, os.environ.get("HISTORY_FILE", "history.csv")))))
SEASON = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
          6: "summer", 7: "summer", 8: "summer", 9: "fall", 10: "fall", 11: "fall"}


def trades(snap, lo, hi):
    ev = collections.defaultdict(list)
    for r in rows:
        if r["snap"] == snap and 0 < float(r["yes_ask"]) <= 1:
            ev[r["event"]].append(r)
    out = []
    for e, ms in ev.items():
        fav = max(ms, key=lambda r: float(r["yes_bid"]) + float(r["yes_ask"]))
        mid = (float(fav["yes_bid"]) + float(fav["yes_ask"])) / 2
        ask = float(fav["yes_ask"])
        if lo <= mid < hi and ask < 1:
            cost = ask + kalshi_fee(ask)
            out.append(dict(date=fav["date"], series=fav["series"], cost=cost, win=fav["result"] == "yes"))
    return out


def summary(ts):
    if len(ts) < 5:
        return f"n={len(ts):<4} (too few)"
    rets = [(1 if t["win"] else 0) / t["cost"] - 1 for t in ts]
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1))
    se = sd / math.sqrt(len(rets))
    return (f"n={len(ts):<4} won {sum(t['win'] for t in ts) / len(ts):>4.0%}  return per $ {m:+6.1%}  "
            f"(+/- {1.96 * se:.1%})  {'LIKELY REAL' if m - 1.96 * se > 0 else 'not proven'}")


for snap in ("eve_6pm", "morn_7am"):
    for lo, hi in ((0.50, 0.65), (0.45, 0.70), (0.40, 0.50), (0.65, 0.80)):
        ts = sorted(trades(snap, lo, hi), key=lambda t: t["date"])
        print(f"\n=== {snap}, favourite priced {lo:.0%}-{hi:.0%} ===")
        print(f"  all          {summary(ts)}")
        if (lo, hi) != (0.50, 0.65):
            continue
        for s in ("winter", "spring", "summer", "fall"):
            print(f"  {s:<12} {summary([t for t in ts if SEASON[int(t['date'][5:7])] == s])}")
        half = len(ts) // 2
        print(f"  older half   {summary(ts[:half])}   ({ts[0]['date']} to {ts[half - 1]['date']})")
        print(f"  newer half   {summary(ts[half:])}   ({ts[half]['date']} to {ts[-1]['date']})")
        print(f"  last 60 days {summary([t for t in ts if t['date'] >= '2026-09-21'])}")
        for c in sorted({t['series'] for t in ts}):
            print(f"  {c:<12} {summary([t for t in ts if t['series'] == c])}")
