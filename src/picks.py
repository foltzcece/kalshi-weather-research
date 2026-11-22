"""
Kalshi daily-high-temperature pick model (v0.1).

How it works, in plain terms:
1. Pull open Kalshi "highest temperature" markets for several US cities.
2. Pull the National Weather Service (NWS) forecast high for each city's settlement station.
3. Treat the real high as a bell curve (normal distribution) centred on the NWS forecast,
   with a spread (SIGMA) that grows the further out the day is.
4. For each price bucket, our probability = area of the bell curve inside that bucket.
5. Edge = our probability - price you pay - Kalshi fee. Only positive-edge picks qualify.
6. Stake = a quarter of the Kelly fraction (cautious sizing).

Run: python3 picks.py [bankroll_dollars]
"""
import json, math, os, sys, urllib.request, datetime as dt

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
UA = {"User-Agent": "kalshi-research-model", "Accept": "application/geo+json"}

# series ticker -> (city, settlement station lat, lon, local timezone UTC offset in standard time)
CITIES = {
    "KXHIGHNY":   ("New York (Central Park)", 40.7789, -73.9692, -5),
    "KXHIGHCHI":  ("Chicago (Midway)",        41.7868, -87.7522, -6),
    "KXHIGHMIA":  ("Miami (MIA airport)",     25.7932, -80.2906, -5),
    "KXHIGHAUS":  ("Austin (AUS airport)",    30.1945, -97.6699, -6),
    "KXHIGHDEN":  ("Denver (DEN airport)",    39.8466, -104.6562, -7),
    "KXHIGHLAX":  ("Los Angeles (LAX)",       33.9382, -118.3866, -8),
    "KXHIGHPHIL": ("Philadelphia (PHL)",      39.8733, -75.2268, -5),
}

# Forecast error spread in deg F by how many days ahead. Starting assumption;
# the tracker will tell us whether to widen or narrow these.
SIGMA = {0: 2.0, 1: 2.7, 2: 3.3}
MIN_YES_PRICE = 0.35   # backtest: YES bets under 35c lost 5-80% after fees, so never pick them (cece approved 2026-11-20)
KELLY_FRACTION = 0.25
MIN_EDGE = 0.04          # need at least 4 cents of edge per $1 contract after fees
MAX_PRICE, MIN_PRICE = 0.90, 0.08   # skip near-certain and lottery-ticket prices


def get(url, headers=None, tries=4):
    """Fetch JSON, backing off and retrying if a site says we're asking too often (HTTP 429)."""
    import time, urllib.error
    for i in range(tries):
        req = urllib.request.Request(url, headers=headers or {"User-Agent": UA["User-Agent"]})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            # dropped or reset connections: wait and retry
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def norm_cdf(x, mu, s):
    return 0.5 * (1 + math.erf((x - mu) / (s * math.sqrt(2))))


def kalshi_fee(price, contracts=1):
    """Kalshi taker fee: round up to the cent of 0.07 * C * P * (1 - P)."""
    return math.ceil(0.07 * contracts * price * (1 - price) * 100 - 1e-9) / 100


def nws_daily_highs(lat, lon, utc_off):
    """Return {local date: forecast max temp in F} from the NWS gridpoint data."""
    pt = get(f"https://api.weather.gov/points/{lat},{lon}", UA)
    grid = get(pt["properties"]["forecastGridData"], UA)
    highs = {}
    for v in grid["properties"]["maxTemperature"]["values"]:
        start = dt.datetime.fromisoformat(v["validTime"].split("/")[0])
        local = (start + dt.timedelta(hours=utc_off + 12)).date()  # the daytime period's date
        if v["value"] is not None:
            highs[local] = v["value"] * 9 / 5 + 32
    return highs


def bucket_prob(m, mu, s):
    """Probability that the reported (whole-degree) high lands in this market's range."""
    st = m.get("strike_type")
    if st == "greater":            # e.g. "70 or above": floor_strike 69 -> high >= 70
        return 1 - norm_cdf(m["floor_strike"] + 0.5, mu, s)
    if st == "less":               # e.g. "61 or below": cap_strike 62 -> high <= 61
        return norm_cdf(m["cap_strike"] - 0.5, mu, s)
    if st == "between":            # e.g. 66 to 67
        return norm_cdf(m["cap_strike"] + 0.5, mu, s) - norm_cdf(m["floor_strike"] - 0.5, mu, s)
    return None


def evaluate(bankroll=100.0):
    today_utc = dt.datetime.now(dt.timezone.utc)
    rows = []
    for series, (city, lat, lon, off) in CITIES.items():
        try:
            highs = nws_daily_highs(lat, lon, off)
            mkts = get(f"{KALSHI}/markets?series_ticker={series}&status=open&limit=100")["markets"]
        except Exception as e:
            print(f"! {city}: {e}", file=sys.stderr)
            continue
        local_today = (today_utc + dt.timedelta(hours=off)).date()
        for m in mkts:
            date = dt.datetime.strptime(m["event_ticker"].split("-")[1], "%y%b%d").date()
            lead = (date - local_today).days
            if date not in highs or lead not in SIGMA:
                continue
            mu, s = highs[date], SIGMA[lead]
            p = bucket_prob(m, mu, s)
            if p is None:
                continue
            for side, prob, ask in (("YES", p, m.get("yes_ask_dollars")), ("NO", 1 - p, m.get("no_ask_dollars"))):
                ask = float(ask or 0)
                if not (MIN_PRICE <= ask <= MAX_PRICE):
                    continue
                fee = kalshi_fee(ask)
                edge = prob - ask - fee
                cost = ask + fee
                kelly = max(0.0, (prob - cost) / (1 - cost)) * KELLY_FRACTION
                rows.append(dict(
                    city=city, date=str(date), lead=lead, ticker=m["ticker"], side=side,
                    bucket=m.get("yes_sub_title"), forecast=round(mu, 1), sigma=s,
                    our_prob=round(prob, 3), price=ask, fee=fee, edge=round(edge, 3),
                    ev_per_dollar=round(edge / cost, 3),
                    stake=round(bankroll * kelly, 2), contracts=int(bankroll * kelly // cost),
                    volume=float(m.get("volume_fp") or 0),
                ))
    picks = sorted([r for r in rows if r["edge"] >= MIN_EDGE and not (r["side"] == "YES" and r["price"] < MIN_YES_PRICE)], key=lambda r: -r["ev_per_dollar"])
    return picks, rows


if __name__ == "__main__":
    bankroll = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
    picks, rows = evaluate(bankroll)
    print(f"Scored {len(rows)} sides; {len(picks)} clear the {MIN_EDGE:.0%} edge bar.\n")
    for r in picks[:10]:
        print(f"{r['city']:<24} {r['date']} {r['side']:<3} {r['bucket']:<14} "
              f"NWS {r['forecast']}F  ours {r['our_prob']:.0%} vs price {r['price']:.2f}+fee {r['fee']:.2f}  "
              f"edge {r['edge']:+.2f}  stake ${r['stake']} ({r['contracts']} contracts)  {r['ticker']}")
    json.dump(picks, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "latest_picks.json"), "w"), indent=1)
