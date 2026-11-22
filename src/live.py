"""
Same-day "live readings" model for today's Kalshi high-temperature markets.

Idea: by afternoon the thermometer has already shown most of the day. So:
1. Read today's airport observations (every ~5 minutes, from the NWS) since local midnight.
2. Take the highest reading so far. 5-minute readings are rounded to whole degrees Celsius,
   so a reading of 20C means the truth was somewhere between 19.5C and 20.5C; hourly reports
   carry tenths. We simulate that rounding instead of pretending we know the exact value.
3. Read the NWS hourly forecast for the rest of today and allow some forecast error.
4. Final high = the larger of (high so far) and (rest-of-day peak). We simulate this 4,000
   times to get each bucket's probability.
5. Blend 70% with our probability and 30% with the market price (observations are strong
   evidence, so they get more weight than the overnight forecast model does).

Run: python3 live.py [bankroll]
"""
import json, math, random, re, sys, datetime as dt
from picks import CITIES, KALSHI, get, kalshi_fee

UA = {"User-Agent": "kalshi-research-model", "Accept": "application/geo+json"}
STATIONS = {"KXHIGHNY": "KNYC", "KXHIGHCHI": "KMDW", "KXHIGHMIA": "KMIA", "KXHIGHAUS": "KAUS",
            "KXHIGHDEN": "KDEN", "KXHIGHLAX": "KLAX", "KXHIGHPHIL": "KPHL"}
SIMS = 4000
REST_SIGMA = 1.5          # error on the forecast peak for the rest of today, deg F
# Official value vs airport readings, measured on 377 city-days of 1-minute data (onemin_results.txt):
# Kalshi settles at the 1-minute max or 1F below it, almost never above. Best fit: shift -0.2F, spread 0.4F.
# (Was +|N(0, 0.3)|, i.e. ~0.4F too warm. Changed 2026-11-21, cece approved.)
SETTLE_SHIFT, SETTLE_SD = -0.2, 0.4
MODEL_WEIGHT = 0.7
SUSPECT_GAP = 0.35
MIN_YES_PRICE = 0.35   # backtest: YES bets under 35c lost 5-80% after fees, so never pick them (cece approved 2026-11-20)
KELLY_FRACTION = 0.25
MIN_EDGE = 0.03
MAX_PRICE, MIN_PRICE = 0.92, 0.05
BOUNDARY_MARGIN = 0.5     # deg F of extra room around the uncertain high-so-far (cece approved 2026-11-21)
C2F = lambda c: c * 9 / 5 + 32


def observations(station, local_midnight_utc):
    d = get(f"https://api.weather.gov/stations/{station}/observations?start="
            f"{local_midnight_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=500", UA)
    obs = []
    for f in d["features"]:
        p = f["properties"]
        c = p["temperature"]["value"]
        if c is None:
            continue
        raw = p.get("rawMessage") or ""
        precise = bool(raw)                       # hourly METARs carry tenths of a degree
        ts = dt.datetime.fromisoformat(p["timestamp"])
        obs.append((ts, c, precise))
        # 6-hour max group "1sTTT" in the remarks (e.g. 10211 = 21.1C): it comes from the
        # 1-minute sensor data, so it catches peaks that fall between the hourly reports.
        rmk = raw.split(" RMK ", 1)[1] if " RMK " in raw else ""
        for g in re.findall(r"(?<!\S)1([01])(\d{3})(?!\S)", rmk):
            if ts - dt.timedelta(hours=6) >= local_midnight_utc - dt.timedelta(minutes=10):
                obs.append((ts, (-1 if g[0] == "1" else 1) * int(g[1]) / 10, True))
    return obs


def rest_of_day_peak(lat, lon, now_utc, local_end_utc):
    pt = get(f"https://api.weather.gov/points/{lat},{lon}", UA)
    hourly = get(pt["properties"]["forecastHourly"], UA)["properties"]["periods"]
    temps = [p["temperature"] for p in hourly
             if now_utc <= dt.datetime.fromisoformat(p["startTime"]).astimezone(dt.timezone.utc) < local_end_utc]
    return max(temps) if temps else None, len(temps)


def hrrr_peak(lat, lon, now_utc, local_end_utc):
    """Warmest HRRR temperature left today (15-minute steps). HRRR is NOAA's 3 km model that
    re-runs every hour and is built for the next ~18 hours, so it should know about this
    afternoon's clouds and sea breezes better than the NWS hourly forecast does. Free via Open-Meteo."""
    d = get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&minutely_15=temperature_2m&models=gfs_hrrr&temperature_unit=fahrenheit"
            "&timezone=GMT&forecast_days=2")
    temps = [t for ts, t in zip(d["minutely_15"]["time"], d["minutely_15"]["temperature_2m"])
             if t is not None and now_utc <= dt.datetime.fromisoformat(ts).replace(tzinfo=dt.timezone.utc) < local_end_utc]
    return max(temps) if temps else None


# Shadow test (cece approved 2026-11-21): each run also scores every market with HRRR as the
# rest-of-day peak. Those rows go only to the calibration log as model "live_hrrr"; picks
# still use the NWS hourly forecast until the comparison says otherwise.
HRRR_ROWS = []
PEAK_LOG = []   # one row per city per run: final-high estimate from each source, for forecast_log


def simulate(obs, rest_peak, hours_left):
    """Return a list of simulated final whole-degree highs.
    Readings of the same plateau share one rounding error, so we draw it once per simulation
    (drawing it per reading would let the max of many draws drift upward)."""
    precise = [c for _, c, p in obs if p]
    coarse = [c for _, c, p in obs if not p]
    out = []
    for _ in range(SIMS):
        best = -999
        if precise:
            best = C2F(max(precise) + random.uniform(-0.05, 0.05))
        if coarse:
            best = max(best, C2F(max(coarse) + random.uniform(-0.5, 0.5)))
        best += random.gauss(SETTLE_SHIFT, SETTLE_SD)
        if rest_peak is not None and hours_left > 0:
            best = max(best, random.gauss(rest_peak, REST_SIGMA))
        out.append(round(best))
    return out


def high_so_far_range(obs):
    """Range the true high so far could be in. Whole-degC readings (e.g. 18C) only say the truth
    was between 17.5C and 18.5C, i.e. a ~1.8F window. Returns (lo, hi) in deg F, or None when the
    precise readings already pin the high down."""
    precise = [c for _, c, p in obs if p]
    coarse = [c for _, c, p in obs if not p]
    p_hi = C2F(max(precise)) if precise else -999
    if not coarse or C2F(max(coarse) + 0.5) <= p_hi:
        return None
    return max(p_hi, C2F(max(coarse) - 0.5)), C2F(max(coarse) + 0.5) + max(0.0, SETTLE_SHIFT + SETTLE_SD)


def market_edges(m):
    """Temperatures (deg F) where this market flips from win to loss. Highs settle in whole
    degrees, so a 64-65 bucket flips at 63.5 and 65.5; 'greater than 65' flips at 65.5."""
    st = m.get("strike_type")
    if st == "greater":
        return [m["floor_strike"] + 0.5]
    if st == "less":
        return [m["cap_strike"] - 0.5]
    if st == "between":
        return [m["floor_strike"] - 0.5, m["cap_strike"] + 0.5]
    return []


def near_boundary(m, rng):
    """Skip rule (live model deep dive, item 1): if the high so far is only known to whole degC and
    a bucket edge falls inside that fuzzy range (plus a margin), traders with exact 1-minute data
    know the answer and we don't, so a 'cheap' price is cheap for a reason."""
    if rng is None:
        return False
    lo, hi = rng
    return any(lo - BOUNDARY_MARGIN <= e <= hi + BOUNDARY_MARGIN for e in market_edges(m))


def prob_for(m, sims):
    st = m.get("strike_type")
    if st == "greater":
        hit = [s > m["floor_strike"] for s in sims]
    elif st == "less":
        hit = [s < m["cap_strike"] for s in sims]
    elif st == "between":
        hit = [m["floor_strike"] <= s <= m["cap_strike"] for s in sims]
    else:
        return None
    # keep a little humility: never claim more than 98% / less than 2%
    return min(0.98, max(0.02, sum(hit) / len(hit)))


def score(city, today, mkts, sims, high_so_far, rest_peak, local_now, bankroll, rng):
    rows = []
    for m in mkts:
        p_model = prob_for(m, sims)
        if p_model is None:
            continue
        yb, ya = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
        mid = (yb + ya) / 2 if ya else yb
        for side, pm, mk, ask in (("YES", p_model, mid, ya),
                                  ("NO", 1 - p_model, 1 - mid, float(m.get("no_ask_dollars") or 0))):
            if not (MIN_PRICE <= ask <= MAX_PRICE):
                continue
            prob = MODEL_WEIGHT * pm + (1 - MODEL_WEIGHT) * mk
            fee = kalshi_fee(ask)
            cost = ask + fee
            edge = prob - cost
            kelly = max(0.0, (prob - cost) / (1 - cost)) * KELLY_FRACTION
            rows.append(dict(
                city=city, date=str(today), lead=0, ticker=m["ticker"], side=side,
                bucket=m.get("yes_sub_title"), forecast=high_so_far, sigma=REST_SIGMA,
                model_prob=round(pm, 3), market_prob=round(mk, 3), our_prob=round(prob, 3),
                price=ask, fee=fee, edge=round(edge, 3), ev_per_dollar=round(edge / cost, 3),
                suspect=int(abs(pm - mk) > SUSPECT_GAP), boundary=int(near_boundary(m, rng)), stake=round(bankroll * kelly, 2),
                contracts=int(bankroll * kelly // cost),
                sources=json.dumps({"high_so_far": high_so_far, "rest_of_day_peak": rest_peak,
                                    "high_range": [round(x, 1) for x in rng] if rng else None,
                                    "local_time": local_now.strftime("%H:%M")}),
            ))
    return rows


def evaluate(bankroll=100.0):
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    HRRR_ROWS.clear()
    PEAK_LOG.clear()
    for series, (city, lat, lon, off) in CITIES.items():
        local_now = now + dt.timedelta(hours=off)
        today = local_now.date()
        midnight_utc = dt.datetime.combine(today, dt.time(0), dt.timezone.utc) - dt.timedelta(hours=off)
        end_utc = midnight_utc + dt.timedelta(days=1)
        if local_now.hour < 11:          # too early: the day's heating hasn't happened yet
            continue
        try:
            mkts = [m for m in get(f"{KALSHI}/markets?series_ticker={series}&status=open&limit=100")["markets"]
                    if dt.datetime.strptime(m["event_ticker"].split("-")[1], "%y%b%d").date() == today]
            obs = observations(STATIONS[series], midnight_utc)
            rest_peak, hours_left = rest_of_day_peak(lat, lon, now, end_utc)
        except Exception as e:
            print(f"! {city}: {e}", file=sys.stderr)
            continue
        if not mkts or not obs:
            continue
        try:
            h_peak = hrrr_peak(lat, lon, now, end_utc)
        except Exception as e:
            print(f"! {city} HRRR: {e}", file=sys.stderr)
            h_peak = None
        high_so_far = round(max(C2F(c) for _, c, _ in obs), 1)
        rng = high_so_far_range(obs)
        sims = simulate(obs, rest_peak, hours_left)
        rows += score(city, today, mkts, sims, high_so_far, rest_peak, local_now, bankroll, rng)
        if h_peak is not None:
            h_rows = score(city, today, mkts, simulate(obs, h_peak, hours_left), high_so_far, h_peak, local_now, bankroll, rng)
            HRRR_ROWS.extend(h_rows)
        for src, pk in (("live_nws", rest_peak), ("live_hrrr", h_peak)):
            if pk is not None or hours_left == 0:
                PEAK_LOG.append(dict(series=series, city=city, date=str(today), source=src,
                                     forecast=round(max(high_so_far, pk if pk is not None else -999), 1)))
    picks = sorted([r for r in rows if r["edge"] >= MIN_EDGE and not r["suspect"] and not r["boundary"] and not (r["side"] == "YES" and r["price"] < MIN_YES_PRICE)], key=lambda r: -r["edge"])
    return picks, rows


if __name__ == "__main__":
    picks, rows = evaluate(float(sys.argv[1]) if len(sys.argv) > 1 else 100.0)
    print(f"live scored {len(rows)} sides; {len(picks)} clear the bar ({sum(r['suspect'] for r in rows)} suspect, "
          f"{sum(r['boundary'] for r in rows)} skipped near a bucket edge).")
    for r in rows:
        if r["side"] == "YES":
            print(f"  {r['city']:<24} {r['bucket']:<14} so far {r['sources']}  model {r['model_prob']:.0%}  market {r['market_prob']:.0%}")
    for r in picks[:6]:
        print(f"PICK {r['city']} {r['side']} {r['bucket']}: ours {r['our_prob']:.0%} vs cost {r['price']+r['fee']:.2f} edge {r['edge']:+.2f}")
