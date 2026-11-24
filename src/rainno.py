"""
"Bet NO on rain priced 50-70c" paper strategy (cece approved 2026-11-22).
From rain_radar_results*.txt: on Kalshi daily rain markets, when YES (it rains) is priced 50-70c,
it rained less often than the price said. Aug-Nov 2026: buying NO returned +11.8% +/- 7.9% over
226 city-days (not proven: several cities often share one weather system). The first 5 weeks of
the market (Jul-Aug) overpriced rain even more. Same-day markets only, before 4 PM local, which
matches the 7 AM-3 PM window the backtest used.
"""
import csv, datetime as dt, os, sys
from picks import KALSHI, get, kalshi_fee

LO, HI = 0.50, 0.70
HIST_NO_WIN = 0.52          # backtest: NO won 52% in this band (avg YES price 59%)
KELLY_FRACTION = 0.25
HERE = os.path.dirname(os.path.abspath(__file__))
GAUGES = {r["market_code"]: r for r in csv.DictReader(open(os.path.join(HERE, "gis", "rain_gauges.csv")))}


def utc_offset(lon):        # rough local standard time from longitude (fine for a 4 PM cutoff)
    return -5 if lon > -87.5 else -6 if lon > -101 else -7 if lon > -114.5 else -8


def evaluate(bankroll=100.0):
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    try:
        mkts, cursor = [], ""
        while True:
            d = get(f"{KALSHI}/markets?series_ticker=KXRAIN&status=open&limit=200" + (f"&cursor={cursor}" if cursor else ""))
            mkts += d["markets"]; cursor = d.get("cursor")
            if not cursor or not d["markets"]:
                break
    except Exception as e:
        print(f"! rain markets: {e}", file=sys.stderr)
        return [], []
    for m in mkts:
        code = m["ticker"].split("-")[-1]
        g = GAUGES.get(code)
        if not g:
            continue
        local = now + dt.timedelta(hours=utc_offset(float(g["lon"])))
        date = dt.datetime.strptime(m["event_ticker"].split("-")[1], "%y%b%d").date()
        if date != local.date() or local.hour >= 16:
            continue
        yb, ya = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
        na = float(m.get("no_ask_dollars") or 0) or (1 - yb)
        if not ya:
            continue
        mid = (yb + ya) / 2
        if not (LO <= mid < HI) or not (0 < na < 1):
            continue
        fee = kalshi_fee(na); cost = na + fee
        prob = 0.5 * HIST_NO_WIN + 0.5 * (1 - mid)     # half backtest, half market
        edge = prob - cost
        kelly = max(0.0, edge / (1 - cost)) * KELLY_FRACTION
        rows.append(dict(city=g["city"], date=str(date), lead=0, ticker=m["ticker"], side="NO",
                         bucket="rain (>0.00 in)", forecast="", sigma="", model_prob=HIST_NO_WIN,
                         market_prob=round(1 - mid, 3), our_prob=round(prob, 3), price=na, fee=fee,
                         edge=round(edge, 3), ev_per_dollar=round(edge / cost, 3), suspect=0,
                         stake=round(bankroll * kelly, 2), contracts=max(1, int(bankroll * kelly // cost)), sources=""))
    picks = sorted([r for r in rows if r["edge"] > 0], key=lambda r: -r["edge"])
    return picks, rows


if __name__ == "__main__":
    p, r = evaluate()
    print(f"{len(r)} rain markets in the 50-70c band today, {len(p)} with positive edge")
    for x in p:
        print(x["city"], x["date"], x["price"], x["our_prob"], x["contracts"])
