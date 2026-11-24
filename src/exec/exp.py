"""Execution experiments for the 'favourite' strategy (YES on the event's top bucket, mid 50-65c).
All numbers are per $1 contract. Research only.

Policy = (place time, limit offset under the ask, cancel time, fill rule, what to do if unfilled).
Luck ranges are 95% bootstrap ranges resampling whole event-dates (days are correlated).
"""
import collections, datetime as dt, math, random, sys
import numpy as np
import tape

RNG = random.Random(7)


def mirror(m):
    """The same market seen from the NO side (buying NO at p == selling YES at 1-p)."""
    return dict(m, won=not m["won"], px=np.round(1 - m["px"], 2), yes_taker=~m["yes_taker"])


def events(M):
    ev = collections.defaultdict(list)
    for t, m in M.items():
        ev[m["event"]].append(m)
    return ev


def favourite_decisions(M, day_off, hour, lo=0.50, hi=0.65, snap_quotes=None):
    """One decision per event: top bucket by mid at local time `hour` on event day + day_off."""
    out = []
    for e, ms in events(M).items():
        s, d = ms[0]["series"], ms[0]["date"]
        t0 = tape.local_ts(s, d, day_off, hour)
        best = None
        for m in ms:
            if snap_quotes is not None and (m["ticker"] if "ticker" in m else None):
                pass
            b, a = tape.quote(m, t0)
            if b is None or a is None:
                continue
            mid = (a + b) / 2
            if best is None or mid > best[0]:
                best = (mid, m, b, a)
        if best and lo <= best[0] < hi and best[3] < 1:
            out.append(dict(m=best[1], t0=t0, bid=best[2], ask=best[3], date=d, series=s))
    return out


def all_decisions(M, day_off, hour, lo=0.2, hi=0.85, both_sides=True):
    """Every bucket with mid in [lo, hi) at that time, bought YES (and NO): strategy-free execution test."""
    out = []
    for t, m in M.items():
        t0 = tape.local_ts(m["series"], m["date"], day_off, hour)
        for mm in ([m, mirror(m)] if both_sides else [m]):
            b, a = tape.quote(mm, t0)
            if b is None or a is None:
                continue
            if lo <= (a + b) / 2 < hi:
                out.append(dict(m=mm, t0=t0, bid=b, ask=a, date=m["date"], series=m["series"]))
    return out


def cancel_time(dcs, spec):
    """spec: ('rel', hours) | ('abs', day_off, local hour) | ('close',)"""
    if spec[0] == "rel":
        return dcs["t0"] + spec[1] * 3600
    if spec[0] == "abs":
        return max(dcs["t0"], tape.local_ts(dcs["series"], dcs["date"], spec[1], spec[2]))
    return tape.local_ts(dcs["series"], dcs["date"], 1, 0)


def run(decs, off=3, cancel=("close",), rule="touch", Q=0.0, fallback="skip", price=None):
    """Returns list of (date, cost or None, won, filled). price(x) -> limit price overrides off."""
    res = []
    for x in decs:
        m, a = x["m"], x["ask"]
        t1 = cancel_time(x, cancel)
        if price is None and off <= 0:
            res.append((x["date"], a + tape.taker_fee(a), m["won"], True)); continue
        L = round(price(x), 2) if price else round(a - off / 100, 2)
        if L >= a:   # marketable: pay the ask as a taker
            res.append((x["date"], a + tape.taker_fee(a), m["won"], True)); continue
        if L <= 0:
            res.append((x["date"], None, m["won"], False)); continue
        tf = tape.fill(m, x["t0"], t1, L, rule, Q)
        if tf is not None:
            res.append((x["date"], L, m["won"], True))
        elif fallback == "cross":
            _, a1 = tape.quote(m, t1)
            if a1 is None or a1 >= 1:
                res.append((x["date"], None, m["won"], False))
            else:
                res.append((x["date"], a1 + tape.taker_fee(a1), m["won"], False))
        else:
            res.append((x["date"], None, m["won"], False))
    return res


def summarize(res, boots=400):
    n = len(res)
    traded = [(d, c, w) for d, c, w, f in res if c is not None]
    fills = sum(f for *_, f in res)
    if not traded:
        return dict(n=n, fill=0, ret=float("nan"), lo=float("nan"), hi=float("nan"), ppd=0, k=0)
    by = collections.defaultdict(lambda: [0.0, 0.0])
    for d, c, w in traded:
        by[d][0] += (1 if w else 0) - c; by[d][1] += c
    days = list(by)
    pnl = sum(v[0] for v in by.values()); cost = sum(v[1] for v in by.values())
    bs = []
    for _ in range(boots):
        s = [by[RNG.choice(days)] for _ in days]
        cc = sum(v[1] for v in s)
        bs.append(sum(v[0] for v in s) / cc if cc else 0)
    bs.sort()
    return dict(n=n, k=len(traded), fill=fills / n, ret=pnl / cost, lo=bs[int(.025 * boots)],
                hi=bs[int(.975 * boots)], ppd=100 * pnl / n)


def fmt(label, s):
    return (f"  {label:<34} n={s['n']:>5} traded={s['k']:>5} filled {s['fill']:>4.0%}  "
            f"return {s['ret']:+6.1%} [{s['lo']:+.1%}, {s['hi']:+.1%}]  profit/100 chances ${s['ppd']:+.2f}")


def detail(decs, off=3, rule="through", Q=0.0, cancel=("close",)):
    """Per decision: fill time (local hours after event-day midnight, None if unfilled), limit, etc."""
    out = []
    for x in decs:
        m, a = x["m"], x["ask"]
        L = round(a - off / 100, 2)
        t1 = cancel_time(x, cancel)
        tf = tape.fill(m, x["t0"], t1, L, rule, Q) if L > 0 else None
        mid0 = tape.local_ts(x["series"], x["date"], 0, 0)
        out.append(dict(x, L=L, tf=tf, fill_h=None if tf is None else (tf - mid0) / 3600,
                        spread=round(a - x["bid"], 2), won=m["won"]))
    return out


def group_ret(rows, key, boots=200):
    g = collections.defaultdict(list)
    for r in rows:
        if r["tf"] is not None:
            g[key(r)].append((r["date"], r["L"], r["won"], True))
    return {k: summarize(v, boots) for k, v in sorted(g.items())}
