"""
Out-of-sample audit of the lead strategy: buy YES on the favourite bucket (mid 50-65c) of
next-day high-temp markets, limit = min(ask-3c, best bid), filled only if a later trade prints
strictly below our limit, maker fee 0 (stress: 1.75%), held to settlement.
Uncertainty: bootstrap resampling whole dates (all cities/snapshots on a date move together,
since weather and market moods are shared across cities on a day). Research only.
Usage: python3 audit/audit.py
"""
import csv, math, os, random, collections, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(HERE)
R = random.Random(7)


def taker_fee(p):
    return math.ceil(0.07 * p * (1 - p) * 100 - 1e-9) / 100


def maker_fee(p, rate):
    return math.ceil(rate * p * (1 - p) * 100 - 1e-9) / 100


def favs(hist_path, lows):
    ev = collections.defaultdict(list)
    for r in csv.DictReader(open(hist_path)):
        if not r["series"].startswith("KXHIGH"):
            continue           # high-temp only (history_more also holds low-temp and rain markets)
        if 0 < float(r["yes_ask"]) <= 1:
            ev[(r["snap"], r["event"])].append(r)
    out = []
    for (snap, e), ms in ev.items():
        f = max(ms, key=lambda r: float(r["yes_bid"]) + float(r["yes_ask"]))
        bid, ask = float(f["yes_bid"]), float(f["yes_ask"])
        low = lows.get((f["ticker"], snap))
        out.append(dict(series=f["series"], date=dt.date.fromisoformat(f["date"]), snap=snap, bid=bid, ask=ask,
                        mid=(bid + ask) / 2, won=f["result"] == "yes",
                        low=None if low in (None, "") else float(low), has_low=low is not None))
    return out


def trade(x, off=3, rule="through", maker=0.0, use_bid=True):
    """Returns (cost, payoff) or None if no fill. off=0 -> pay the ask with taker fee."""
    if off == 0:
        return x["ask"] + taker_fee(x["ask"]), 1.0 if x["won"] else 0.0
    lim = round(x["ask"] - off / 100, 2)
    if use_bid:
        lim = min(lim, x["bid"])
    if lim <= 0 or x["low"] is None:
        return None
    ok = x["low"] < lim - 1e-9 if rule == "through" else x["low"] <= lim + 1e-9
    if not ok:
        return None
    return lim + maker_fee(lim, maker), 1.0 if x["won"] else 0.0


def evaluate(xs, lo=0.50, hi=0.65, boots=2000, **kw):
    cand = [x for x in xs if lo <= x["mid"] < hi and x["ask"] < 1 and (kw.get("off", 3) == 0 or x["has_low"])]
    by = collections.defaultdict(lambda: [0.0, 0.0, 0, 0])   # date -> cost, profit, n chances, n fills
    for x in cand:
        t = trade(x, **kw); b = by[x["date"]]; b[2] += 1
        if t:
            b[0] += t[0]; b[1] += t[1] - t[0]; b[3] += 1
    if not by:
        return None
    days = list(by)
    def agg(ds):
        c = sum(by[d][0] for d in ds); p = sum(by[d][1] for d in ds)
        return (p / c if c else float("nan")), 100 * p / max(1, sum(by[d][2] for d in ds))
    ret, per100 = agg(days)
    bs = sorted(agg([R.choice(days) for _ in days])[0] for _ in range(boots))
    fills = sum(by[d][3] for d in days); n = sum(by[d][2] for d in days)
    return dict(n=n, fills=fills, ret=ret, lo95=bs[int(.025 * boots)], hi95=bs[int(.975 * boots)],
                p_loss=sum(b <= 0 for b in bs) / boots, per100=per100)


def fmt(label, s):
    if not s or not s["fills"]:
        return f"  {label:<44} no trades"
    return (f"  {label:<44} chances {s['n']:>4}  filled {s['fills']:>4}  return {s['ret']:+6.1%}  "
            f"95% range [{s['lo95']:+6.1%}, {s['hi95']:+6.1%}]  chance it's really <=0: {s['p_loss']:4.0%}")


def load_all():
    lows = {(r["ticker"], r["snap"]): r["low"] for r in csv.DictReader(open(os.path.join(P, "limit_cache.csv")))}
    ins = favs(os.path.join(P, "history.csv"), lows)
    extra = favs(os.path.join(P, "history_more.csv"), lows)
    oos = []
    hp = os.path.join(HERE, "history_oos.csv")
    if os.path.exists(hp):
        l2 = {(r["ticker"], r["snap"]): r["low"] for r in csv.DictReader(open(os.path.join(HERE, "lows_oos.csv")))}
        oos = favs(hp, l2)
    return ins, extra, oos


if __name__ == "__main__":
    ins, extra, oos = load_all()
    L = dt.date
    print("Lead strategy: favourite 50-65c, limit min(ask-3c, bid), strict fills, maker fee 0.\n")
    sets = [("A. 7 cities, untouched year (Dec 2024-Nov 2025)", oos),
            ("B. 7 cities, tuning year (Nov 2025-Nov 2026)", ins),
            ("C. 11 newer cities, high temp only (Aug-Nov 2026)", extra)]
    for name, xs in sets:
        if not xs:
            print(name, ": no data yet\n"); continue
        print(name)
        for snap in ("eve_6pm", "morn_7am", None):
            ys = [x for x in xs if snap is None or x["snap"] == snap]
            lab = snap or "both runs"
            print(fmt(f"{lab}: lead strategy", evaluate(ys)))
            if snap is None:
                print(fmt(f"{lab}: limit ask-3c only (old rule)", evaluate(ys, use_bid=False)))
                print(fmt(f"{lab}: lead, 'touch' fills (optimistic)", evaluate(ys, rule="touch")))
                print(fmt(f"{lab}: lead, stress maker fee 1.75%", evaluate(ys, maker=0.0175)))
                print(fmt(f"{lab}: pay the ask + taker fee", evaluate(ys, off=0)))
        print()

    print("Same window, Aug 23-Nov 19 2026: is the extra-city loss about cities or about the period?")
    w = lambda xs: [x for x in xs if L(2026, 8, 23) <= x["date"] <= L(2026, 11, 19)]
    print(fmt("7 tuned cities, same window", evaluate(w(ins))))
    print(fmt("11 newer cities, same window", evaluate(w(extra))))
    print()

    allx = oos + ins
    print("By quarter, 7 cities, both runs (A then B)")
    q = collections.defaultdict(list)
    for x in allx:
        q[f"{x['date'].year}-Q{(x['date'].month - 1) // 3 + 1}"].append(x)
    for k in sorted(q):
        print(fmt(k, evaluate(q[k], boots=500)))
    print()
    print("By city (A + B, both runs)")
    for c in sorted({x["series"] for x in allx}):
        print(fmt(c, evaluate([x for x in allx if x["series"] == c], boots=500)))
    print("By city, newer cities (C)")
    for c in sorted({x["series"] for x in extra}):
        print(fmt(c, evaluate([x for x in extra if x["series"] == c], boots=500)))
    print()
    print("Price band check on untouched year A (was 50-65c chosen by luck?)")
    for lo, hi in ((0.35, 0.45), (0.40, 0.50), (0.45, 0.55), (0.50, 0.65), (0.55, 0.70), (0.65, 0.80)):
        print(fmt(f"band {lo:.0%}-{hi:.0%}", evaluate(oos, lo, hi, boots=500)))
