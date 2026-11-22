"""
Fine-tune the favourite + limit strategy on the year of history (no new downloads: uses
limit_cache.csv, the lowest trade price after each snapshot).
For each limit offset (cents under the ask) and each snapshot (6 PM eve / 7 AM morning):
fill rate, win rate, return per $ with a standard error, profit per 100 opportunities, and the
same split into the two halves of the year and by city. Two fill rules:
  touch  = fills if any later trade printed at our price (optimistic: assumes we're first in line)
  through = fills only if a trade printed BELOW our price (pessimistic: we were surely filled)
A setting is only worth adopting if it wins in BOTH halves under BOTH fill rules.
Usage: python3 tune_favorite.py > tune_results.txt
"""
import csv, math, os, statistics as st
import limit_backtest as lb

HERE = os.path.dirname(os.path.abspath(__file__))
cache = {(r["ticker"], r["snap"]): r["low"] for r in csv.DictReader(open(os.path.join(HERE, "limit_cache.csv")))}
favs = [f for f in lb.fav_trades() if cache.get((f["ticker"], f["snap"])) not in (None, "")]
dates = sorted(f["date"] for f in favs)
MID = dates[len(dates) // 2]


def stats(fs, off, rule):
    rets, profit = [], 0.0
    for f in fs:
        ask = float(f["yes_ask"])
        low = float(cache[(f["ticker"], f["snap"])])
        if off == 0:
            cost = ask + lb.kalshi_fee(ask)
        else:
            lim = round(ask - off / 100, 2)
            ok = low <= lim + 1e-9 if rule == "touch" else low < lim - 1e-9
            if not ok:
                continue
            cost = lim + lb.maker_fee(lim)
        won = f["result"] == "yes"
        rets.append(((1 if won else 0) - cost) / cost)
        profit += (1 if won else 0) - cost
    if len(rets) < 2:
        return None
    return dict(n=len(rets), fill=len(rets) / len(fs), ret=st.mean(rets),
                se=st.stdev(rets) / math.sqrt(len(rets)), per100=100 * profit / len(fs))


def line(label, s):
    if not s:
        return f"  {label:<22} too few"
    return (f"  {label:<22} filled {s['fill']:>4.0%}  n={s['n']:<4} return {s['ret']:+6.1%} ± {s['se']:.1%}"
            f"   profit per 100 chances ${s['per100']:+6.2f} (per $1 contract)")


for snap in ("eve_6pm", "morn_7am"):
    fs = [f for f in favs if f["snap"] == snap]
    print(f"\n===== {snap}: {len(fs)} favourites priced 50-65c (halves split at {MID}) =====")
    for rule in ("touch", "through"):
        print(f"-- fill rule: {rule}")
        for off in (0, 1, 2, 3, 4, 5, 6):
            label = "pay the ask" if off == 0 else f"limit {off}c under"
            print(line(label, stats(fs, off, rule)))
            if off:
                h1 = stats([f for f in fs if f["date"] < MID], off, rule)
                h2 = stats([f for f in fs if f["date"] >= MID], off, rule)
                print(f"      halves: {h1['ret'] if h1 else float('nan'):+.1%} / {h2['ret'] if h2 else float('nan'):+.1%}")
    print("-- by city, limit 3c, touch rule (n is small: read as a hint only)")
    for city in sorted({f["series"] for f in fs}):
        print(line(city, stats([f for f in fs if f["series"] == city], 3, "touch")))
