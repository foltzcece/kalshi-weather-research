"""Paper market-making backtest on Kalshi weather markets, from tick-level trades (mm/trades.csv).

Strategy: every STEP seconds (default once an hour), for every market priced 10-90c, rest a YES bid at the best bid and a YES ask
(= NO bid) at the best ask, SIZE contracts each, until the next re-quote. Stop quoting at CUTOFF local hour on the
market's day. Never hold more than CAP contracts net in one market. Hold everything to settlement.

The best bid/ask at each hour is rebuilt from trades: a taker selling YES prints at the bid, a taker
buying YES prints at the ask (last of each within 2 h, and the last trade must sit between them).

Fills (we can't see the historical queue, so three cases):
  front   - we are first in line: any trade at our price fills us (best case)
  queue   - QUEUE contracts are ahead of us (median size at the best price in today's live books):
            they must trade first; a trade through our price fills us
  through - only a trade strictly through our price fills us (worst case)
Weather series charge no maker fee (fee_type 'quadratic', maker multiplier 0).
Usage: python3 mm_backtest.py  -> mm/mm_results.txt"""
import csv, os, math, collections, datetime as dt, bisect
HERE = os.path.dirname(os.path.abspath(__file__))
OFF = {"KXHIGHNY": -5, "KXHIGHPHIL": -5, "KXHIGHMIA": -5, "KXHIGHCHI": -6, "KXHIGHAUS": -6, "KXHIGHDEN": -7, "KXHIGHLAX": -8}
for g in csv.DictReader(open(os.path.join(os.path.dirname(HERE), "gis", "rain_gauges.csv"))):
    OFF["RAIN-" + g["market_code"]] = round(float(g["lon"]) / 15)
OFF.update({"RAIN-HNL": -10, "RAIN-ANC": -9})
SIZE, CAP = 10, 50
SIDE = os.environ.get("SIDE", "both")      # both | bid (buy YES only) | ask (sell YES only)
LO, HI = float(os.environ.get("LO", "0.10")), float(os.environ.get("HI", "0.90"))   # quote only when mid is in [LO, HI]
STEP = int(os.environ.get("STEP", "3600"))   # seconds between re-quotes (each quote lives this long)
QUEUE = {"high": 25, "rain": 55}


def load():
    mk = {}
    for r in csv.DictReader(open(os.path.join(HERE, "trades.csv"))):
        t = r["ticker"]
        if t not in mk:
            kind = "rain" if r["series"] == "KXRAIN" else "high"
            key = ("RAIN-" + t.rsplit("-", 1)[1]) if kind == "rain" else r["series"]
            mk[t] = dict(kind=kind, off=OFF.get(key, -6), date=r["date"], Y=1.0 if r["result"] == "yes" else 0.0, tr=[])
        ts = dt.datetime.fromisoformat(r["ts"].replace("Z", "+00:00")).timestamp()
        mk[t]["tr"].append((ts, float(r["yes_price"]), float(r["count"]), r["taker_side"] == "yes"))
    for m in mk.values():
        m["tr"].sort()
    return mk


def simulate(m, cutoff, rule):
    """Return list of fills (pnl, cost, contracts, local hour relative to market-day midnight)."""
    tr = m["tr"]; times = [x[0] for x in tr]
    d = dt.date.fromisoformat(m["date"]); tz = dt.timezone(dt.timedelta(hours=m["off"]))
    start = dt.datetime.combine(d - dt.timedelta(days=1), dt.time(12), tz).timestamp()
    end = dt.datetime.combine(d, dt.time(0), tz).timestamp() + cutoff * 3600
    q0 = QUEUE[m["kind"]]; pos = 0.0; fills = []
    T = start
    while T < end:
        i = bisect.bisect_left(times, T)
        bid = ask = last = None
        for j in range(i - 1, -1, -1):
            ts, p, n, ty = tr[j]
            if T - ts > 7200: break
            if last is None: last = p
            if ty and ask is None: ask = p
            if not ty and bid is None: bid = p
            if bid is not None and ask is not None: break
        if bid is not None and ask is not None and bid < ask and bid <= last <= ask and LO <= (bid + ask) / 2 <= HI:
            rb = min(SIZE, CAP - pos) if SIDE != "ask" else 0; ra = min(SIZE, CAP + pos) if SIDE != "bid" else 0; qb = qa = q0
            hr = (T - dt.datetime.combine(d, dt.time(0), tz).timestamp()) / 3600
            k = i
            while k < len(tr) and tr[k][0] < T + STEP and (rb > 0 or ra > 0):
                ts, p, n, ty = tr[k]; k += 1
                if not ty and rb > 0:                      # taker sold YES: can hit our bid
                    f = 0
                    if p < bid - 1e-9: f = min(rb, n)
                    elif abs(p - bid) < 1e-9 and rule != "through":
                        if rule == "front": f = min(rb, n)
                        else:
                            use = min(qb, n); qb -= use; f = min(rb, n - use)
                    if f > 0:
                        rb -= f; pos += f; ra = min(SIZE, CAP + pos) if ra > 0 else 0
                        fills.append((f * (m["Y"] - bid), f * bid, f, hr))
                elif ty and ra > 0:                        # taker bought YES: can lift our ask
                    f = 0
                    if p > ask + 1e-9: f = min(ra, n)
                    elif abs(p - ask) < 1e-9 and rule != "through":
                        if rule == "front": f = min(ra, n)
                        else:
                            use = min(qa, n); qa -= use; f = min(ra, n - use)
                    if f > 0:
                        ra -= f; pos -= f; rb = min(SIZE, CAP - pos) if rb > 0 else 0
                        fills.append((f * (ask - m["Y"]), f * (1 - ask), f, hr))
        T += STEP
    return fills


def stats(per_day):
    """per_day: {event: [pnl, contracts, cost]} -> summary with event-clustered SE on $/day."""
    k = len(per_day)
    if k == 0: return None
    pnl = sum(v[0] for v in per_day.values()); n = sum(v[1] for v in per_day.values()); c = sum(v[2] for v in per_day.values())
    mean = pnl / k; sd = math.sqrt(sum((v[0] - mean) ** 2 for v in per_day.values()) / max(k - 1, 1))
    return dict(days=k, n=n, pnl=pnl, cents=100 * pnl / n if n else 0, ret=pnl / c if c else 0, se_ret=sd * math.sqrt(k) / c if c else 0)


def fmt(s):
    if not s or not s["n"]: return "no fills"
    return (f"{s['n']:>8,.0f} ctr filled  P&L ${s['pnl']:>8,.0f}  {s['cents']:+5.2f}c/ctr  "
            f"return {s['ret']:+6.1%} ± {1.96 * s['se_ret']:.1%}")


def main():
    mk = load()
    dates = sorted({m["date"] for m in mk.values()}); mid = dates[len(dates) // 2]
    out = [__doc__.split("Usage")[0].strip(), "", f"Markets settled {dates[0]}..{dates[-1]}, re-quote every {STEP}s, side={SIDE}, mid {LO:.2f}-{HI:.2f}, SIZE={SIZE}, CAP={CAP}, queue ahead={QUEUE}",
           "± = 95% range on return, clustered by event-day (all buckets/cities of one day move together).",
           "$/day = average P&L per event-day (high: per city-day; rain: per day across all cities).", ""]
    new = lambda: collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    for kind in ("high", "rain"):
        out.append(f"=== {kind.upper()} ===")
        for cutoff in (9, 13, 17, 24):
            for rule in ("front", "queue", "through"):
                days, h1, h2 = new(), new(), new()
                byhr = collections.defaultdict(new)
                for t, m in mk.items():
                    if m["kind"] != kind: continue
                    ev = t.rsplit("-", 1)[0]
                    for pnl, cost, q, hr in simulate(m, cutoff, rule):
                        b = "day before" if hr < 0 else "00-09h" if hr < 9 else "09-13h" if hr < 13 else "13-17h" if hr < 17 else "17-24h"
                        for D in (days[ev], (h2 if m["date"] >= mid else h1)[ev], byhr[b][ev]):
                            D[0] += pnl; D[1] += q; D[2] += cost
                s = stats(days)
                a, b2 = stats(h1), stats(h2)
                out.append(f"  stop {cutoff:>2}h  {rule:<8} {fmt(s)}  ${s['pnl'] / s['days'] if s else 0:+.2f}/day"
                           f"  halves {a['ret'] if a else 0:+.1%} / {b2['ret'] if b2 else 0:+.1%}")
                if cutoff == 24 and rule == "queue":
                    for b in ("day before", "00-09h", "09-13h", "13-17h", "17-24h"):
                        out.append(f"      fills during {b:<10} {fmt(stats(byhr[b]))}")
        out.append("")
    txt = "\n".join(out); print(txt)
    open(os.path.join(HERE, "mm_results" + "".join(f"_{k}{os.environ[k]}" for k in ("STEP", "SIDE", "LO", "HI") if os.environ.get(k)) + ".txt"), "w").write(txt + "\n")


if __name__ == "__main__":
    main()
