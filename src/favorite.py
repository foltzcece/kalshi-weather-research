"""
"Buy the favourite" strategy, from the 45-day backtest (backtest_results.txt).

In 315 past city-days across 7 cities, when the market's most likely bucket was priced
50-65 cents, it won about 66% of the time: roughly +10% return after fees. Cheap long shots
did the opposite (YES under 35 cents lost 5% to 80%). This is a pricing bias, not a weather
forecast, so it is paper-tested on its own here before we trust it.
"""
import datetime as dt, sys
from picks import CITIES, KALSHI, get, kalshi_fee

LO, HI = 0.50, 0.65
KELLY_FRACTION = 0.25
HIST_WIN = 0.66   # backtest hit rate in this band; shrunk toward the price when sizing


def evaluate(bankroll=100.0):
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    for series, (city, lat, lon, off) in CITIES.items():
        try:
            mkts = get(f"{KALSHI}/markets?series_ticker={series}&status=open&limit=100")["markets"]
        except Exception as e:
            print(f"! {city}: {e}", file=sys.stderr)
            continue
        local_today = (now + dt.timedelta(hours=off)).date()
        events = {}
        for m in mkts:
            events.setdefault(m["event_ticker"], []).append(m)
        for ev, ms in events.items():
            date = dt.datetime.strptime(ev.split("-")[1], "%y%b%d").date()
            lead = (date - local_today).days
            if lead not in (0, 1):
                continue
            fav = max(ms, key=lambda m: float(m.get("yes_bid_dollars") or 0) + float(m.get("yes_ask_dollars") or 0))
            yb, ya = float(fav.get("yes_bid_dollars") or 0), float(fav.get("yes_ask_dollars") or 0)
            mid = (yb + ya) / 2
            if not (LO <= mid < HI) or not (0 < ya < 1):
                continue
            fee = kalshi_fee(ya)
            cost = ya + fee
            prob = 0.5 * HIST_WIN + 0.5 * mid      # half backtest, half market: stay humble
            edge = prob - cost
            kelly = max(0.0, edge / (1 - cost)) * KELLY_FRACTION
            rows.append(dict(city=city, date=str(date), lead=lead, ticker=fav["ticker"], side="YES",
                             bucket=fav.get("yes_sub_title"), forecast="", sigma="", model_prob=HIST_WIN,
                             market_prob=round(mid, 3), our_prob=round(prob, 3), price=ya, fee=fee,
                             edge=round(edge, 3), ev_per_dollar=round(edge / cost, 3), suspect=0,
                             stake=round(bankroll * kelly, 2), contracts=max(1, int(bankroll * kelly // cost)),
                             sources=""))
    picks = sorted([r for r in rows if r["edge"] > 0], key=lambda r: -r["edge"])
    return picks, rows


if __name__ == "__main__":
    p, r = evaluate()
    for x in p:
        print(x["city"], x["date"], x["bucket"], x["price"], x["our_prob"], x["contracts"])
