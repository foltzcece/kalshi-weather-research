"""
Calibrate the live model with IEM 1-minute airport temperatures (Sep-Nov 2026).
For each city-day: the 1-minute max, the max the free 5-minute whole-degC feed would show,
and the Kalshi settlement value. Measures:
  settle gap  = Kalshi value - 1-minute max          (what SETTLE_BUMP tries to capture)
  coarse gap  = Kalshi value - whole-degC 5-min max   (what the live model actually sees)
Output: onemin_results.txt
"""
import csv, collections, datetime as dt, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
STN = {"KXHIGHNY": ("NYC", -5), "KXHIGHCHI": ("MDW", -6), "KXHIGHMIA": ("MIA", -5), "KXHIGHAUS": ("AUS", -6),
       "KXHIGHDEN": ("DEN", -7), "KXHIGHLAX": ("LAX", -8), "KXHIGHPHIL": ("PHL", -5)}
actual = {}
for r in csv.DictReader(open(os.path.join(HERE, "history.csv"))):
    if r["actual"] not in ("", None):
        try:
            actual[(r["series"], r["date"])] = float(r["actual"])
        except ValueError:
            pass
out = []
for series, (stn, off) in STN.items():
    m1 = collections.defaultdict(lambda: -999.0)
    m5 = collections.defaultdict(lambda: -999.0)
    n = collections.Counter()
    for r in csv.DictReader(open(os.path.join(HERE, "onemin", stn + ".csv"))):
        try:
            f = float(r["tmpf"])
        except (ValueError, KeyError):
            continue
        t = dt.datetime.strptime(r["valid(UTC)"], "%Y-%m-%d %H:%M") + dt.timedelta(hours=off)  # local standard time
        d = t.date().isoformat()
        n[d] += 1
        m1[d] = max(m1[d], f)
        if t.minute % 5 == 0:
            c = round((f - 32) * 5 / 9)
            m5[d] = max(m5[d], c * 9 / 5 + 32)
    for d in m1:
        if n[d] >= 1200 and (series, d) in actual:
            out.append(dict(series=series, date=d, m1=m1[d], m5=m5[d], act=actual[(series, d)]))
lines = [f"{len(out)} city-days with full 1-minute data and a Kalshi settlement\n"]
def summ(label, xs):
    c = collections.Counter(round(x) for x in xs)
    dist = "  ".join(f"{k:+d}F:{c[k] / len(xs):.0%}" for k in sorted(c) if c[k] / len(xs) >= 0.01)
    return f"  {label:<10} mean {st.mean(xs):+.2f}  sd {st.pstdev(xs):.2f}   {dist}"
lines.append("Settle gap (Kalshi value minus 1-minute max):")
lines.append(summ("ALL", [o["act"] - o["m1"] for o in out]))
for s in STN:
    xs = [o["act"] - o["m1"] for o in out if o["series"] == s]
    if xs: lines.append(summ(s[6:], xs) + f"  (n={len(xs)})")
lines.append("\nCoarse gap (Kalshi value minus what the free whole-degC 5-minute feed shows):")
lines.append(summ("ALL", [o["act"] - o["m5"] for o in out]))
for s in STN:
    xs = [o["act"] - o["m5"] for o in out if o["series"] == s]
    if xs: lines.append(summ(s[6:], xs) + f"  (n={len(xs)})")
open(os.path.join(HERE, "onemin_results.txt"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))

# --- How the live model's "high so far" assumption compares with what actually settled ---
# Live model: true high = C2F(c + U(-0.5,0.5)) + |N(0, SETTLE_BUMP)|, rounded. Compare by where the
# whole-degC reading lands in Fahrenheit (18C = 64.4F, 19C = 66.2F, ...), end of day (high is in).
import random
SETTLE_BUMP = 0.3
lines2 = ["\nFinal settled value given the whole-degC feed's max (end of day), actual vs live model:"]
by = collections.defaultdict(list)
for o in out:
    by[round(o["m5"] % 1, 1)].append(o["act"] - round(o["m5"]))
for fr in sorted(by):
    xs = by[fr]
    c = collections.Counter(int(x) for x in xs)
    # model's implied distribution for a reading with this fractional part
    sims = collections.Counter()
    for _ in range(20000):
        base = 60 + fr
        cdeg = (base - 32) * 5 / 9
        v = (cdeg + random.uniform(-0.5, 0.5)) * 9 / 5 + 32 + abs(random.gauss(0, SETTLE_BUMP))
        sims[round(v) - round(base)] += 1
    act = "  ".join(f"{k:+d}:{c[k] / len(xs):.0%}" for k in sorted(c) if abs(k) <= 2)
    mod = "  ".join(f"{k:+d}:{sims[k] / 20000:.0%}" for k in sorted(sims))
    lines2.append(f"  reading ends in .{int(fr * 10)}F (n={len(xs)}): actual {act}\n{'':26}model  {mod}")
open(os.path.join(HERE, "onemin_results.txt"), "a").write("\n".join(lines2) + "\n")
print("\n".join(lines2))
