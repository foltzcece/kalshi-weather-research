"""Pooled checks across all three tape sets (main + year + extra). Research only."""
import collections, random, numpy as np
import tape, exp
R = random.Random(3)
sets = {n: tape.load(n) for n in ("main", "year", "extra")}

def paired(decs, fa, fb, boots=1000):
    """Day-clustered bootstrap of profit difference per 100 chances, policy a minus b."""
    by = collections.defaultdict(lambda: [0.0, 0])
    ra = exp.run(decs, **fa); rb = exp.run(decs, **fb)
    for (d, ca, w, _), (_, cb, _, _) in zip(ra, rb):
        pa = 0 if ca is None else (1 if w else 0) - ca
        pb = 0 if cb is None else (1 if w else 0) - cb
        by[d][0] += pa - pb; by[d][1] += 1
    days = list(by); tot = sum(v[0] for v in by.values()) / sum(v[1] for v in by.values())
    bs = sorted(sum(by[x][0] for x in s) / sum(by[x][1] for x in s) for s in ([R.choice(days) for _ in days] for _ in range(boots)))
    return 100 * tot, 100 * bs[25], 100 * bs[975]

near_bid = lambda x: min(x["ask"] - .03, x["bid"])
base = dict(off=3, rule="through", cancel=("close",))
print("Paired: 'min(ask-3c, best bid)' minus 'ask-3c', profit per 100 chances [95% range]")
for u in ("fav", "generic"):
    for do, h, lab in ((-1, 18, "6 PM"), (0, 7, "7 AM")):
        D = []
        for n, M in sets.items():
            D += exp.favourite_decisions(M, do, h) if u == "fav" else exp.all_decisions(M, do, h)
        print(f"  {u:<8}{lab}: n={len(D):>6}  %+.2f [%+.2f, %+.2f]" % paired(D, dict(base, price=near_bid), base))
        print(f"  {u:<8}{lab}: cancel noon vs never: n={len(D):>6}  %+.2f [%+.2f, %+.2f]" % paired(D, dict(base, cancel=("abs", 0, 12)), base))

print("\nPlacement time, fav, all 3 sets pooled, ask-3c through, cancel noon (pay-ask in brackets)")
for do, h, lab in ((-1, 12, "noon day before"), (-1, 15, "3 PM day before"), (-1, 18, "6 PM day before"), (0, 7, "7 AM"), (0, 11, "11 AM")):
    D = []; ages = []
    for M in sets.values():
        d = exp.favourite_decisions(M, do, h); D += d
        for x in d:
            m = x["m"]; i = np.searchsorted(m["ts"], x["t0"]); ages.append((x["t0"] - m["ts"][i - 1]) / 60)
    c = ("abs", 0, 12) if (do, h) < (0, 12) else ("rel", 1)
    print(exp.fmt(lab + " limit", exp.summarize(exp.run(D, off=3, rule="through", cancel=c))))
    print(exp.fmt(lab + " pay ask", exp.summarize(exp.run(D, off=0))), f" median minutes since last trade {np.median(ages):.0f}")
