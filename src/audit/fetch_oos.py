"""
Out-of-sample data for the favourite audit: the 7 tuned cities BEFORE history.csv starts
(Dec 2024 - Nov 19 2025), a year the strategy never saw. Same snapshot rule as backfill.py
(hourly candle close at 6 PM CST the evening before and 7 AM CST the same day), then for each
event's favourite the lowest trade price from the snapshot to end of day (limit fill check).
Writes audit/history_oos.csv and audit/lows_oos.csv. Research only.
Usage: python3 audit/fetch_oos.py START END   (dates YYYY-MM-DD)
"""
import csv, os, sys, time, threading, datetime as dt, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from picks import KALSHI, CITIES, get

HERE = os.path.dirname(os.path.abspath(__file__))
CT = dt.timezone(dt.timedelta(hours=-6))
COLS = ["series", "event", "date", "ticker", "bucket", "strike_type", "floor", "cap", "result",
        "actual", "snap", "yes_bid", "yes_ask", "volume"]
lock = threading.Lock()


def g(url):
    for i in range(6):
        try:
            return get(url)
        except Exception as e:
            if "404" in str(e):
                return {}
            time.sleep(1 + 2 * i)
    return {}


def event_rows(series, date):
    et = f"{series}-{date.strftime('%y%b%d').upper()}"
    ms = g(f"{KALSHI}/historical/markets?event_ticker={et}").get("markets", [])
    snaps = {"eve_6pm": int(dt.datetime.combine(date - dt.timedelta(days=1), dt.time(18), CT).timestamp()),
             "morn_7am": int(dt.datetime.combine(date, dt.time(7), CT).timestamp())}
    out = []
    for m in ms:
        if m.get("result") not in ("yes", "no"):
            continue
        lo, hi = snaps["eve_6pm"] - 3 * 3600, snaps["morn_7am"]
        c = g(f"{KALSHI}/historical/markets/{m['ticker']}/candlesticks?start_ts={lo}&end_ts={hi}&period_interval=60").get("candlesticks", [])
        for snap, ts in snaps.items():
            cs = [x for x in c if ts - 3 * 3600 <= x["end_period_ts"] <= ts]
            if not cs:
                continue
            last = cs[-1]
            val = lambda side: last[side].get("close_dollars", last[side].get("close"))
            if val("yes_bid") is None or val("yes_ask") is None:
                continue
            out.append(dict(series=series, event=et, date=str(date), ticker=m["ticker"], bucket=m.get("yes_sub_title"),
                            strike_type=m.get("strike_type"), floor=m.get("floor_strike", ""), cap=m.get("cap_strike", ""),
                            result=m["result"], actual=m.get("expiration_value", ""), snap=snap,
                            yes_bid=float(val("yes_bid")), yes_ask=float(val("yes_ask")),
                            volume=float(last.get("volume_fp") or last.get("volume") or 0)))
    # favourites per snapshot -> lowest trade after snapshot until end of day (CT)
    lows = []
    end = int(dt.datetime.combine(date + dt.timedelta(days=1), dt.time(0), CT).timestamp())
    for snap, ts in snaps.items():
        rs = [r for r in out if r["snap"] == snap and 0 < r["yes_ask"] <= 1]
        if not rs:
            continue
        fav = max(rs, key=lambda r: r["yes_bid"] + r["yes_ask"])
        mid = (fav["yes_bid"] + fav["yes_ask"]) / 2
        if not (0.40 <= mid < 0.80):
            continue
        low, n, cursor = None, 0, ""
        for _ in range(10):
            d = g(f"{KALSHI}/historical/trades?ticker={fav['ticker']}&min_ts={ts}&max_ts={end}&limit=1000" + (f"&cursor={cursor}" if cursor else ""))
            for t in d.get("trades", []):
                p = float(t["yes_price_dollars"]); n += 1
                low = p if low is None else min(low, p)
            cursor = d.get("cursor")
            if not cursor or not d.get("trades"):
                break
        lows.append(dict(ticker=fav["ticker"], snap=snap, low="" if low is None else low, ntrades=n))
    return out, lows


def main(start, end):
    hp, lp = os.path.join(HERE, "history_oos.csv"), os.path.join(HERE, "lows_oos.csv")
    done = set()
    if os.path.exists(hp):
        done = {(r["series"], r["date"]) for r in csv.DictReader(open(hp))}
    jobs = []
    d = start
    while d <= end:
        for s in CITIES:
            if (s, str(d)) not in done:
                jobs.append((s, d))
        d += dt.timedelta(days=1)
    print(len(jobs), "city-days to fetch", file=sys.stderr)
    newh = not os.path.exists(hp); newl = not os.path.exists(lp)
    fh = open(hp, "a", newline=""); fl = open(lp, "a", newline="")
    wh = csv.DictWriter(fh, fieldnames=COLS); wl = csv.DictWriter(fl, fieldnames=["ticker", "snap", "low", "ntrades"])
    if newh: wh.writeheader()
    if newl: wl.writeheader()
    with cf.ThreadPoolExecutor(6) as ex:
        futs = {ex.submit(event_rows, s, d): (s, d) for s, d in jobs}
        for k, f in enumerate(cf.as_completed(futs)):
            try:
                rows, lows = f.result()
            except Exception as e:
                print("!", futs[f], e, file=sys.stderr); continue
            with lock:
                wh.writerows(rows); wl.writerows(lows)
                if k % 50 == 0:
                    fh.flush(); fl.flush(); print(k, "/", len(jobs), file=sys.stderr)
    fh.close(); fl.close()


if __name__ == "__main__":
    main(dt.date.fromisoformat(sys.argv[1]), dt.date.fromisoformat(sys.argv[2]))
