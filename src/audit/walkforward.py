"""
Walk-forward test of the *procedure* that picked 50-65c and 3c: each month, choose the price band
and offset that did best on all earlier months only (min 4 months of history), then trade that
month with them. Also a paired test of 7 tuned cities vs 11 newer cities on the same dates.
Usage: python3 audit/walkforward.py
"""
import collections, random, datetime as dt
import audit as A

R = random.Random(11)
BANDS = [(lo / 100, (lo + w) / 100) for lo in range(35, 75, 5) for w in (10, 15) if lo + w <= 85]
OFFS = [0, 1, 2, 3, 5]


def pnl(xs, lo, hi, off):
    c = p = 0.0
    for x in xs:
        if lo <= x["mid"] < hi and x["ask"] < 1 and (off == 0 or x["has_low"]):
            t = A.trade(x, off=off)
            if t:
                c += t[0]; p += t[1] - t[0]
    return c, p


def run(xs, label):
    month = lambda d: (d.year, d.month)
    by = collections.defaultdict(list)
    for x in xs:
        by[month(x["date"])].append(x)
    ms = sorted(by)
    tot_c = tot_p = 0.0; picked = []; daily = collections.defaultdict(lambda: [0.0, 0.0])
    for i, m in enumerate(ms):
        if i < 4:
            continue
        past = [x for k in ms[:i] for x in by[k]]
        best = max(((lo, hi, off) for lo, hi in BANDS for off in OFFS),
                   key=lambda s: (lambda cp: cp[1] / cp[0] if cp[0] > 20 else -9)(pnl(past, *s)))
        picked.append((m, best))
        for x in by[m]:
            c, p = pnl([x], *best)
            daily[x["date"]][0] += c; daily[x["date"]][1] += p
    days = list(daily)
    agg = lambda ds: sum(daily[d][1] for d in ds) / max(1e-9, sum(daily[d][0] for d in ds))
    bs = sorted(agg([R.choice(days) for _ in days]) for _ in range(2000))
    print(f"{label}: walk-forward return {agg(days):+.1%}  95% range [{bs[50]:+.1%}, {bs[1950]:+.1%}]  "
          f"(money staked ${sum(v[0] for v in daily.values()):.0f} at $1/contract)")
    for m, b in picked:
        print(f"    {m[0]}-{m[1]:02d}: chose band {b[0]:.0%}-{b[1]:.0%}, offset {b[2]}c")


if __name__ == "__main__":
    ins, extra, oos = A.load_all()
    run(oos + ins, "7 cities, all months")
    # paired: same dates, 7 vs 11 cities, lead strategy
    w = lambda xs: [x for x in xs if dt.date(2026, 8, 23) <= x["date"] <= dt.date(2026, 11, 19)]
    def daily(xs):
        d = collections.defaultdict(lambda: [0.0, 0.0])
        for x in xs:
            if 0.5 <= x["mid"] < 0.65 and x["ask"] < 1 and x["has_low"]:
                t = A.trade(x)
                if t:
                    d[x["date"]][0] += t[0]; d[x["date"]][1] += t[1] - t[0]
        return d
    a, b = daily(w(ins)), daily(w(extra)); days = sorted(set(a) | set(b))
    r = lambda D, ds: sum(D[x][1] for x in ds if x in D) / max(1e-9, sum(D[x][0] for x in ds if x in D))
    diff = r(a, days) - r(b, days)
    bs = sorted((lambda s: r(a, s) - r(b, s))([R.choice(days) for _ in days]) for _ in range(2000))
    print(f"\nSame dates Aug 23-Nov 19 2026: 7 cities minus 11 cities = {diff:+.1%} "
          f"[{bs[50]:+.1%}, {bs[1950]:+.1%}]; chance the gap is really <=0: {sum(x <= 0 for x in bs) / 2000:.0%}")
    allc = w(ins) + w(extra)
    print(A.fmt("All 18 cities pooled, same window", A.evaluate(allc)))
