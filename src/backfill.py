"""
Backfill past settled Kalshi high-temperature markets: the outcome, the actual high,
and the market's price at two snapshot times that match our scheduled runs
(6 PM Central the evening before, and 7 AM Central the same morning).
Writes history.csv. Usage: python3 backfill.py [days]
"""
import csv, os, sys, time, datetime as dt
from picks import CITIES, KALSHI, get

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, os.environ.get("HISTORY_FILE", "history.csv"))
CT = dt.timezone(dt.timedelta(hours=-6))   # Central standard time
COLS = ["series", "event", "date", "ticker", "bucket", "strike_type", "floor", "cap", "result",
        "actual", "snap", "yes_bid", "yes_ask", "volume"]


def price_at(series, ticker, ts, historical=False):
    """Yes bid/ask at the hourly candle ending at ts (or the latest one before it).
    Markets settled before Kalshi's archive cutoff live under /historical with plain field names."""
    q = f"candlesticks?start_ts={ts - 3 * 3600}&end_ts={ts}&period_interval=60"
    url = f"{KALSHI}/historical/markets/{ticker}/{q}" if historical else f"{KALSHI}/series/{series}/markets/{ticker}/{q}"
    c = [x for x in get(url).get("candlesticks", []) if x["end_period_ts"] <= ts]
    if not c:
        return None
    last = c[-1]
    val = lambda side: last[side].get("close_dollars", last[side].get("close"))
    if val("yes_bid") is None or val("yes_ask") is None:
        return None
    return float(val("yes_bid")), float(val("yes_ask")), float(last.get("volume_fp") or last.get("volume") or 0)


def main(days, series_list=None):
    done = set()
    rows = []
    if os.path.exists(OUT):
        rows = list(csv.DictReader(open(OUT)))
        done = {(r["ticker"], r["snap"]) for r in rows}
    cutoff = dt.date.today() - dt.timedelta(days=days)
    for series in (series_list or CITIES):
        cursor = ""
        events = []
        while True:
            d = get(f"{KALSHI}/events?series_ticker={series}&status=settled&limit=100&with_nested_markets=true" + (f"&cursor={cursor}" if cursor else ""))
            for e in d["events"]:
                date = dt.datetime.strptime(e["event_ticker"].split("-")[1], "%y%b%d").date()
                if date >= cutoff:
                    events.append((date, e))
            cursor = d.get("cursor")
            if not cursor or (d["events"] and dt.datetime.strptime(d["events"][-1]["event_ticker"].split("-")[1], "%y%b%d").date() < cutoff):
                break
        print(series, len(events), "events", file=sys.stderr)
        for k, (date, e) in enumerate(events):
            if k and k % 25 == 0:
                with open(OUT, "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)
            snaps = {
                "eve_6pm": int(dt.datetime.combine(date - dt.timedelta(days=1), dt.time(18), CT).timestamp()),
                "morn_7am": int(dt.datetime.combine(date, dt.time(7), CT).timestamp()),
            }
            markets, hist = e.get("markets") or [], False
            if not markets:
                try:
                    markets = get(f"{KALSHI}/historical/markets?event_ticker={e['event_ticker']}").get("markets", [])
                except Exception as ex:
                    print("!", e["event_ticker"], ex, file=sys.stderr)
                    markets = []
                hist = True
            for m in markets:
                if m.get("result") not in ("yes", "no"):
                    continue
                for snap, ts in snaps.items():
                    if (m["ticker"], snap) in done:
                        continue
                    try:
                        p = price_at(series, m["ticker"], ts, hist)
                    except Exception as ex:
                        print("!", m["ticker"], ex, file=sys.stderr)
                        p = None
                    time.sleep(0.15)
                    if not p:
                        continue
                    rows.append(dict(series=series, event=e["event_ticker"], date=str(date), ticker=m["ticker"],
                                     bucket=m.get("yes_sub_title"), strike_type=m.get("strike_type"),
                                     floor=m.get("floor_strike", ""), cap=m.get("cap_strike", ""),
                                     result=m["result"], actual=m.get("expiration_value", ""), snap=snap,
                                     yes_bid=p[0], yes_ask=p[1], volume=p[2]))
        with open(OUT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)
    print(len(rows), "rows", file=sys.stderr)


if __name__ == "__main__":
    # usage: python3 backfill.py DAYS [SERIES ...]   (HISTORY_FILE env var picks the output file)
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 45, sys.argv[2:] or None)
