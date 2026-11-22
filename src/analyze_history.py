"""
What past markets teach us, using history.csv from backfill.py.

1. Calibration: when the market priced a bucket at X%, how often did it actually happen?
2. Strategy test: if we had bought YES (at the ask) or NO (at 1 - bid) in each price band,
   after Kalshi fees, what return would we have made? A band with a reliably positive return
   is a pricing bias we can trade, regardless of weather forecasts.
Usage: python3 analyze_history.py [snap]   (snap = eve_6pm or morn_7am; default both)
"""
import csv, os, sys, math
from picks import kalshi_fee

HERE = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(HERE, "history.csv"))))
snaps = sys.argv[1:] or ["eve_6pm", "morn_7am"]
BANDS = [(0.0, .05), (.05, .10), (.10, .20), (.20, .35), (.35, .50), (.50, .65), (.65, .80), (.80, .90), (.90, .95), (.95, 1.0)]


def ci(wins, n):
    """95% range for a hit rate (Wilson interval), to show how much is luck."""
    if n == 0:
        return (0, 0)
    p, z = wins / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


for snap in snaps:
    rs = [r for r in rows if r["snap"] == snap and float(r["yes_ask"]) > 0]
    print(f"\n===== Snapshot {snap}: {len(rs)} market-prices, {len({r['event'] for r in rs})} city-days =====")
    print(f"{'mid price band':<15}{'n':>5}{'happened':>10}{'95% range':>16}   {'buy YES return':>15}{'buy NO return':>15}")
    for lo, hi in BANDS:
        b = [r for r in rs if lo <= (float(r["yes_bid"]) + float(r["yes_ask"])) / 2 < hi]
        if not b:
            continue
        wins = sum(r["result"] == "yes" for r in b)
        l, h = ci(wins, len(b))
        yes_cost = yes_pay = no_cost = no_pay = 0
        for r in b:
            ask, bid = float(r["yes_ask"]), float(r["yes_bid"])
            if 0 < ask < 1:
                c = ask + kalshi_fee(ask); yes_cost += c; yes_pay += r["result"] == "yes"
            no_ask = 1 - bid
            if 0 < no_ask < 1:
                c = no_ask + kalshi_fee(no_ask); no_cost += c; no_pay += r["result"] == "no"
        yr = (yes_pay - yes_cost) / yes_cost if yes_cost else 0
        nr = (no_pay - no_cost) / no_cost if no_cost else 0
        print(f"{lo:>4.0%}-{hi:<9.0%}{len(b):>5}{wins / len(b):>10.0%}   {l:>5.0%} to {h:<5.0%}   {yr:>14.1%}{nr:>15.1%}")

    # by city: how often did the market's favourite bucket win?
    print("\nMarket favourite bucket hit rate by city:")
    by_ev = {}
    for r in rs:
        by_ev.setdefault((r["series"], r["event"]), []).append(r)
    city = {}
    for (s, e), ms in by_ev.items():
        fav = max(ms, key=lambda r: float(r["yes_bid"]) + float(r["yes_ask"]))
        favp = (float(fav["yes_bid"]) + float(fav["yes_ask"])) / 2
        city.setdefault(s, []).append((fav["result"] == "yes", favp))
    for s, v in sorted(city.items()):
        print(f"  {s:<12} favourite won {sum(w for w, _ in v)}/{len(v)}  (market expected {sum(p for _, p in v):.1f})")
