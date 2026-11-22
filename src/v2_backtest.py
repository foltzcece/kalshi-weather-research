"""
Backtest of the version 2 forecast approach on the past year, with no peeking ahead.

For each city-day we use the four models' day-ahead forecasts (Open-Meteo previous-runs
archive: the model run from roughly a day before), take each model's daily high, correct
each city's bias using only the PREVIOUS 30 days of results, and turn that into a bell
curve whose width comes from how much the models disagree (plus a floor).
Then we compare against Kalshi's 6 PM-the-evening-before prices from history.csv:
  - accuracy (Brier score) of our model vs the market
  - the v2 trading rule (blend 50/50 with market, need 3c edge after fees, no YES under 35c)
  - the favourite strategy filtered by "our forecast agrees"
Usage: python3 v2_backtest.py
"""
import csv, json, math, os, statistics as st, collections, datetime as dt
from picks import CITIES, get, norm_cdf, kalshi_fee

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = {-5: "America/New_York", -6: "America/Chicago", -7: "America/Denver", -8: "America/Los_Angeles"}
MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_seamless"]
FLOOR = 2.0
BIAS_DAYS = 30
SNAP = "eve_6pm"

rows = [r for r in csv.DictReader(open(os.path.join(HERE, "history.csv"))) if r["snap"] == SNAP and 0 < float(r["yes_ask"]) <= 1]
start = min(r["date"] for r in rows)
end = max(r["date"] for r in rows)
cache_path = os.path.join(HERE, "past_forecasts.json")
cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}

# 1. past day-ahead forecasts: daily max per model per city
for series, (city, lat, lon, off) in CITIES.items():
    if series in cache:
        continue
    url = (f"https://previous-runs-api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           f"&hourly=temperature_2m_previous_day1&temperature_unit=fahrenheit&timezone={TZ[off]}"
           f"&start_date={start}&end_date={end}&models={','.join(MODELS)}")
    h = get(url)["hourly"]
    daily = collections.defaultdict(dict)
    for m in MODELS:
        vals = h.get(f"temperature_2m_previous_day1_{m}", [])
        by = collections.defaultdict(list)
        for t, v in zip(h["time"], vals):
            if v is not None:
                by[t[:10]].append(v)
        for d, vs in by.items():
            if len(vs) >= 20:
                daily[d][m] = max(vs)
    cache[series] = daily
    json.dump(cache, open(cache_path, "w"))

# 2. actual highs per city-day from settled markets
actual = {}
import re
def parse_actual(v):
    """Recent markets report the exact high; archived ones report the winning bucket label
    (e.g. '70° to 71°'), so we use the bucket's middle (within half a degree)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", v or "")]
        if not nums:
            return None
        if "above" in v:
            return nums[0] + 1
        if "below" in v:
            return nums[0] - 1
        return sum(nums) / len(nums)

for r in rows:
    a = parse_actual(r["actual"])
    if a is not None:
        actual[(r["series"], r["date"])] = a

# 3. walk-forward bias + probabilities
def centre_sigma(series, date):
    fc = cache[series].get(date)
    if not fc or len(fc) < 3:
        return None
    raw = st.mean(fc.values())
    # bias from the previous BIAS_DAYS days only
    d0 = dt.date.fromisoformat(date)
    errs = []
    for k in range(1, BIAS_DAYS + 1):
        dd = str(d0 - dt.timedelta(days=k))
        f2, a2 = cache[series].get(dd), actual.get((series, dd))
        if f2 and len(f2) >= 3 and a2 is not None:
            errs.append(st.mean(f2.values()) - a2)
    bias = st.mean(errs) if len(errs) >= 10 else 0.0
    # recent forecast error size sets the floor of the spread
    spread = st.pstdev(fc.values())
    recent_sd = st.pstdev(errs) if len(errs) >= 10 else 3.0
    sigma = max(FLOOR, math.sqrt(spread ** 2 + recent_sd ** 2))
    return raw - bias, sigma


def bucket_p(r, mu, s):
    st_ = r["strike_type"]
    if st_ == "greater":
        return 1 - norm_cdf(float(r["floor"]) + 0.5, mu, s)
    if st_ == "less":
        return norm_cdf(float(r["cap"]) - 0.5, mu, s)
    if st_ == "between":
        return norm_cdf(float(r["cap"]) + 0.5, mu, s) - norm_cdf(float(r["floor"]) - 0.5, mu, s)
    return None


scored = []
for r in rows:
    cs = centre_sigma(r["series"], r["date"])
    if not cs:
        continue
    p = bucket_p(r, *cs)
    if p is None:
        continue
    mid = (float(r["yes_bid"]) + float(r["yes_ask"])) / 2
    scored.append(dict(r=r, p=min(.99, max(.01, p)), mid=mid, win=r["result"] == "yes", mu=cs[0], sigma=cs[1]))

def brier(xs, key):
    return sum((x[key] - x["win"]) ** 2 for x in xs) / len(xs)

def ret_summary(trades):
    if len(trades) < 5:
        return f"n={len(trades)} (too few)"
    rets = [(1 if w else 0) / c - 1 for c, w in trades]
    m = sum(rets) / len(rets)
    se = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1)) / math.sqrt(len(rets))
    return f"n={len(trades)} won {sum(w for _, w in trades) / len(trades):.0%} return per $ {m:+.1%} (+/- {1.96 * se:.1%}) {'LIKELY REAL' if m - 1.96 * se > 0 else 'not proven'}"

print(f"Scored {len(scored)} past market-prices over {len({(x['r']['series'], x['r']['date']) for x in scored})} city-days ({start} to {end}).")
print(f"Accuracy (Brier, lower is better): our model {brier(scored, 'p'):.4f}  |  market {brier(scored, 'mid'):.4f}  |  50/50 blend "
      f"{sum(((x['p'] + x['mid']) / 2 - x['win']) ** 2 for x in scored) / len(scored):.4f}")
errs = [x["mu"] - actual[(x["r"]["series"], x["r"]["date"])] for x in scored if (x["r"]["series"], x["r"]["date"]) in actual]
print(f"Bias-corrected forecast miss: average {sum(map(abs, errs)) / len(errs):.2f}F")

for w in (0.3, 0.5):
    for min_edge in (0.03, 0.06):
        best = {}
        for x in scored:
            r = x["r"]
            for side, pm, mk, ask in (("YES", x["p"], x["mid"], float(r["yes_ask"])), ("NO", 1 - x["p"], 1 - x["mid"], 1 - float(r["yes_bid"]))):
                if not (0.08 <= ask <= 0.90) or (side == "YES" and ask < 0.35) or abs(pm - mk) > 0.25:
                    continue
                cost = ask + kalshi_fee(ask)
                edge = w * pm + (1 - w) * mk - cost
                if edge >= min_edge:
                    k = (r["series"], r["date"])
                    if k not in best or edge > best[k][0]:
                        best[k] = (edge, cost, x["win"] == (side == "YES"))
        print(f"v2 rule, model weight {w:.0%}, min edge {min_edge * 100:.0f}c: {ret_summary([(c, win) for _, c, win in best.values()])}")

# favourite filtered by forecast agreement
ev = collections.defaultdict(list)
for x in scored:
    ev[(x["r"]["series"], x["r"]["date"])].append(x)
for thresh in (None, 0.0, 0.05, 0.10):
    tr = []
    for k, xs in ev.items():
        fav = max(xs, key=lambda x: x["mid"])
        if 0.50 <= fav["mid"] < 0.65:
            if thresh is not None and fav["p"] - fav["mid"] < thresh:
                continue
            ask = float(fav["r"]["yes_ask"])
            if ask < 1:
                tr.append((ask + kalshi_fee(ask), fav["win"]))
    label = "favourite, no filter" if thresh is None else f"favourite + our model at least {thresh * 100:.0f} pts above price"
    print(f"{label}: {ret_summary(tr)}")
