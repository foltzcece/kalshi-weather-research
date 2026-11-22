"""
Kalshi daily-high pick model, version 2.

What changed from version 1 (picks.py):
1. SEVERAL FORECAST MODELS. Besides the NWS forecast, it pulls the ensemble forecasts of the
   American (GEFS, 31 runs), European (ECMWF, 51 runs), German (ICON, 40 runs) and
   Canadian (GEM, 21 runs) models from Open-Meteo. Our centre estimate is the average of the
   five sources, plus a per-city bias correction.
2. REAL UNCERTAINTY. The spread of the bell curve now comes from how much the models
   disagree with each other and within their own runs, with a minimum floor, instead of
   one fixed guess.
3. RESPECT THE MARKET. Our final probability is a blend: MODEL_WEIGHT of our model plus the
   rest from the market's mid price. A pick also needs our raw model to disagree with the
   market by less than SUSPECT_GAP; a bigger gap is treated as a sign our model is wrong.
4. CITY BIAS. bias.json holds how many degrees each city's forecasts run too warm (+) or
   too cold (-). tracker.py updates it from settled results.

Run: python3 picks_v2.py [bankroll]
"""
import json, math, os, sys, statistics as st, urllib.request, datetime as dt
from picks import CITIES, KALSHI, get, norm_cdf, kalshi_fee, nws_daily_highs, bucket_prob

HERE = os.path.dirname(os.path.abspath(__file__))
ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"
ENS_MODELS = {"ncep_gefs025": "gfs025", "ecmwf_ifs025": "ecmwf_ifs025", "icon": "icon_seamless", "gem": "gem_global"}
TZ = {-5: "America/New_York", -6: "America/Chicago", -7: "America/Denver", -8: "America/Los_Angeles"}

SIGMA_FLOOR = {0: 1.5, 1: 2.0, 2: 2.5}   # forecasts at a point station are never perfect
MODEL_WEIGHT = 0.5                         # 50% our model, 50% the market
SUSPECT_GAP = 0.25                         # model vs market gap above this = don't trust it
MIN_YES_PRICE = 0.35   # backtest: YES bets under 35c lost 5-80% after fees, so never pick them (cece approved 2026-11-20)
KELLY_FRACTION = 0.25
MIN_EDGE = 0.03
MAX_PRICE, MIN_PRICE = 0.90, 0.08


def load_bias():
    try:
        return json.load(open(os.path.join(HERE, "bias.json")))
    except Exception:
        return {}


def ensemble_highs(lat, lon, off):
    """{date: {model: [member highs in F]}}"""
    url = (f"{ENSEMBLE}?latitude={lat}&longitude={lon}&daily=temperature_2m_max&temperature_unit=fahrenheit"
           f"&timezone={TZ[off]}&forecast_days=3&models={','.join(ENS_MODELS.values())}")
    d = get(url)["daily"]
    out = {}
    for i, day in enumerate(d["time"]):
        date = dt.date.fromisoformat(day)
        per = {}
        for key, vals in d.items():
            if key == "time" or vals[i] is None:
                continue
            for name in ENS_MODELS:
                if name in key:
                    per.setdefault(name, []).append(vals[i])
        out[date] = per
    return out


def combine(nws, ens, lead, bias):
    """Return centre, spread and each source's forecast for one city-day."""
    sources = {}
    if nws is not None:
        sources["nws"] = nws
    within = []
    for name, members in ens.items():
        sources[name] = st.mean(members)
        if len(members) > 1:
            within.append(st.pstdev(members))
    if len(sources) < 2:
        return None
    centre = st.mean(sources.values()) - bias
    between = st.pstdev(sources.values())
    within_avg = st.mean(within) if within else 0
    sigma = max(SIGMA_FLOOR[lead], math.sqrt(between ** 2 + within_avg ** 2 + 1.0))
    return centre, sigma, sources


def evaluate(bankroll=100.0):
    now = dt.datetime.now(dt.timezone.utc)
    bias = load_bias()
    rows = []
    for series, (city, lat, lon, off) in CITIES.items():
        try:
            mkts = get(f"{KALSHI}/markets?series_ticker={series}&status=open&limit=100")["markets"]
            ens = ensemble_highs(lat, lon, off)
        except Exception as e:
            print(f"! {city}: {e}", file=sys.stderr)
            continue
        try:
            nws = nws_daily_highs(lat, lon, off)
        except Exception as e:
            print(f"! {city} NWS: {e}", file=sys.stderr)
            nws = {}
        local_today = (now + dt.timedelta(hours=off)).date()
        for m in mkts:
            date = dt.datetime.strptime(m["event_ticker"].split("-")[1], "%y%b%d").date()
            lead = (date - local_today).days
            if lead not in SIGMA_FLOOR or date not in ens:
                continue
            c = combine(nws.get(date), ens[date], lead, bias.get(series, 0.0))
            if not c:
                continue
            mu, s, sources = c
            p_model = bucket_prob(m, mu, s)
            if p_model is None:
                continue
            yb, ya = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
            mid = (yb + ya) / 2 if ya else yb
            for side, pm, mk, ask in (("YES", p_model, mid, ya), ("NO", 1 - p_model, 1 - mid, float(m.get("no_ask_dollars") or 0))):
                if not (MIN_PRICE <= ask <= MAX_PRICE):
                    continue
                prob = MODEL_WEIGHT * pm + (1 - MODEL_WEIGHT) * mk
                fee = kalshi_fee(ask)
                cost = ask + fee
                edge = prob - cost
                suspect = abs(pm - mk) > SUSPECT_GAP
                kelly = max(0.0, (prob - cost) / (1 - cost)) * KELLY_FRACTION
                rows.append(dict(
                    city=city, date=str(date), lead=lead, ticker=m["ticker"], side=side,
                    bucket=m.get("yes_sub_title"), forecast=round(mu, 1), sigma=round(s, 2),
                    model_prob=round(pm, 3), market_prob=round(mk, 3), our_prob=round(prob, 3),
                    price=ask, fee=fee, edge=round(edge, 3), ev_per_dollar=round(edge / cost, 3),
                    suspect=int(suspect), stake=round(bankroll * kelly, 2), contracts=int(bankroll * kelly // cost),
                    sources=json.dumps({k: round(v, 1) for k, v in sources.items()}),
                ))
    picks = sorted([r for r in rows if r["edge"] >= MIN_EDGE and not r["suspect"] and not (r["side"] == "YES" and r["price"] < MIN_YES_PRICE)], key=lambda r: -r["edge"])  # rank by cents of edge, not return per dollar, so cheap long shots don't dominate
    return picks, rows


if __name__ == "__main__":
    bankroll = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
    picks, rows = evaluate(bankroll)
    print(f"v2 scored {len(rows)} sides; {len(picks)} clear the bar ({sum(r['suspect'] for r in rows)} flagged suspect).\n")
    for r in picks[:10]:
        print(f"{r['city']:<24} {r['date']} {r['side']:<3} {r['bucket']:<14} centre {r['forecast']}F ±{r['sigma']}  "
              f"model {r['model_prob']:.0%} market {r['market_prob']:.0%} -> ours {r['our_prob']:.0%} vs cost {r['price']+r['fee']:.2f}  "
              f"edge {r['edge']:+.2f}  {r['sources']}")
