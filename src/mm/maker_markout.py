"""What did resting (maker) orders earn on Kalshi weather markets?
Every trade has a taker (crossed the spread) and a maker (resting order). Using taker_side we know
which side the maker took, and the market's result tells us whether that maker made money.
Maker P&L per contract: taker bought YES at p -> maker sold YES -> earns p - Y; taker bought NO -> maker bought YES -> earns Y - p.
Return on capital = P&L / cost of the maker's side (p if long YES, 1-p if short YES).
Output: mm/markout_results.txt"""
import csv, os, math, collections, datetime as dt, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
# local standard-time offsets (market day ends at local midnight)
OFF = {"KXHIGHNY": -5, "KXHIGHPHIL": -5, "KXHIGHMIA": -5, "KXHIGHCHI": -6, "KXHIGHAUS": -6, "KXHIGHDEN": -7, "KXHIGHLAX": -8}

for g in csv.DictReader(open(os.path.join(os.path.dirname(HERE), "gis", "rain_gauges.csv"))):
    OFF["RAIN-" + g["market_code"]] = round(float(g["lon"]) / 15)
OFF.update({"RAIN-HNL": -10, "RAIN-ANC": -9})

def maker_fee(p, rate):
    return math.ceil(rate * p * (1 - p) * 100 - 1e-9) / 100 if rate else 0.0

def phase(series, date, ts):
    off = OFF.get(series, -6)
    loc = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")) + dt.timedelta(hours=off)
    d = dt.date.fromisoformat(date)
    if loc.date() < d: return "1 day before"
    if loc.date() > d: return "6 after midnight"
    h = loc.hour
    return "2 00-09h" if h < 9 else "3 09-13h" if h < 13 else "4 13-17h" if h < 17 else "5 17-24h"

def load():
    out = []
    for r in csv.DictReader(open(os.path.join(HERE, "trades.csv"))):
        p, n = float(r["yes_price"]), float(r["count"]); Y = 1.0 if r["result"] == "yes" else 0.0
        if r["taker_side"] == "yes": pnl, cost = p - Y, 1 - p      # maker short YES
        else: pnl, cost = Y - p, p                                   # maker long YES
        r = dict(ticker=r["ticker"], date=r["date"], taker_side=r["taker_side"], series=r["series"], ts=r["ts"])
        r.update(p=p, n=n, pnl=pnl, cost=cost, ph=phase(("RAIN-" + r["ticker"].rsplit("-", 1)[1]) if r["series"] == "KXRAIN" else r["series"], r["date"], r["ts"]),
                 kind="rain" if r["series"] == "KXRAIN" else "high")
        out.append(r)
    return out

def summarize(rows, rate=0.0):
    n = sum(r["n"] for r in rows)
    if n == 0: return None
    pnl = sum(r["n"] * (r["pnl"] - maker_fee(r["p"], rate)) for r in rows)
    cost = sum(r["n"] * r["cost"] for r in rows)
    # standard error: cluster by market-day (outcomes within a market are one coin flip)
    by = collections.defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        by[r["ticker"].rsplit("-", 1)[0]][0] += r["n"] * (r["pnl"] - maker_fee(r["p"], rate))
        by[r["ticker"].rsplit("-", 1)[0]][1] += r["n"] * r["cost"]
    k = len(by); ret = pnl / cost
    se = math.sqrt(sum((a - ret * c) ** 2 for a, c in by.values()) * k / max(k - 1, 1)) / cost if k > 1 else float("nan")
    return dict(contracts=n, trades=len(rows), days=k, cents=100 * pnl / n, ret=ret, se=se)

def line(label, s):
    if not s: return f"  {label:<22} (none)"
    return (f"  {label:<22} {s['trades']:>7,} trades {s['contracts']:>11,.0f} ctr  {s['days']:>4} event-days  "
            f"maker edge {s['cents']:+5.2f}c/ctr  return {s['ret']:+6.1%} ± {1.96*s['se']:.1%}")

def main():
    rows = load()
    out = [f"Maker markout to settlement, Kalshi weather markets settled 2026-09-22..2026-11-19 (rain = only city-days priced 3-97c at 7 AM) (n={len(rows):,} trades)",
           "± = 95% range, clustered by event-day. Fees: weather series are fee_type 'quadratic' (no maker fee charged);",
           "'w/ fee' column shows the result if a 0.0175 maker fee applied.", ""]
    for kind in ("high", "rain"):
        R = [r for r in rows if r["kind"] == kind]
        out.append(f"=== {kind.upper()} markets ===")
        out.append(line("ALL", summarize(R)))
        out.append(line("ALL w/ 0.0175 fee", summarize(R, 0.0175)))
        out.append(" by local time of trade:")
        for ph in sorted({r["ph"] for r in R}):
            out.append(line(ph[2:], summarize([r for r in R if r["ph"] == ph])))
        out.append(" by trade price (YES):")
        for lo, hi in ((0, .1), (.1, .25), (.25, .5), (.5, .75), (.75, .9), (.9, 1.01)):
            out.append(line(f"{lo:.2f}-{hi:.2f}", summarize([r for r in R if lo <= r["p"] < hi])))
        out.append(" by maker side:")
        out.append(line("maker bought YES", summarize([r for r in R if r["taker_side"] == "no"])))
        out.append(line("maker sold YES", summarize([r for r in R if r["taker_side"] == "yes"])))
        out.append(" by trade size:")
        for lo, hi in ((0, 10), (10, 100), (100, 1e9)):
            out.append(line(f"{lo:.0f}-{hi:.0f} ctr", summarize([r for r in R if lo <= r["n"] < hi])))
        out.append(" first half vs second half (by event date):")
        ds = sorted({r["date"] for r in R}); mid = ds[len(ds) // 2] if ds else ""
        out.append(line("first half", summarize([r for r in R if r["date"] < mid])))
        out.append(line("second half", summarize([r for r in R if r["date"] >= mid])))
        out.append("")
    txt = "\n".join(out); print(txt)
    open(os.path.join(HERE, "markout_results.txt"), "w").write(txt + "\n")

if __name__ == "__main__":
    main()
