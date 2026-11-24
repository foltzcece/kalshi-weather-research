"""Hourly Kalshi prices (bid/ask at the close of each hour) for the uncertain rain city-days.
Output: rain_candles.csv (resumable)."""
import csv, os, sys, time, datetime as dt
from picks import KALSHI, get
HERE = os.path.dirname(os.path.abspath(__file__))
SET = os.environ.get("RAIN_SET", "")            # "" = Aug-Nov (history_more.csv); "summer" = Jun-Aug
SFX = f"_{SET}" if SET else ""
SRC = "history_summer.csv" if SET == "summer" else "history_more.csv"
OUT = os.path.join(HERE, f"rain_candles{SFX}.csv")
CUTOFF = dt.date(2026, 9, 21)
rows = [r for r in csv.DictReader(open(os.path.join(HERE, SRC))) if r["series"] == "KXRAIN" and r["snap"] == "morn_7am" and (SET != "summer" or r["date"] <= "2026-08-22")]
todo = [r for r in rows if 0.03 <= (float(r["yes_bid"]) + float(r["yes_ask"])) / 2 <= 0.97]
done = {r["ticker"] for r in csv.DictReader(open(OUT))} if os.path.exists(OUT) else set()
f = open(OUT, "a", newline=""); w = csv.writer(f)
if not done:
    w.writerow(["ticker", "date", "result", "hour_utc", "bid", "ask", "last", "volume"])
for i, r in enumerate(todo):
    if r["ticker"] in done:
        continue
    d = dt.date.fromisoformat(r["date"])
    s = int(dt.datetime.combine(d, dt.time(10), dt.timezone.utc).timestamp()); e = s + 20 * 3600
    base = f"{KALSHI}/historical/markets/{r['ticker']}/candlesticks" if d < CUTOFF else f"{KALSHI}/series/KXRAIN/markets/{r['ticker']}/candlesticks"
    try:
        cs = get(f"{base}?start_ts={s}&end_ts={e}&period_interval=60").get("candlesticks", [])
    except Exception as ex:
        print("!", r["ticker"], ex, file=sys.stderr); continue
    for c in cs:
        hr = dt.datetime.fromtimestamp(c["end_period_ts"], dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        g = lambda k: (c.get(k) or {}).get("close_dollars") or (c.get(k) or {}).get("close") or ""
        p = c.get("price") or {}
        w.writerow([r["ticker"], r["date"], r["result"], hr, g("yes_bid"), g("yes_ask"),
                    p.get("close_dollars") or p.get("close") or "", c.get("volume_fp") or c.get("volume") or ""])
    f.flush()
    if i % 50 == 0: print(i, len(todo), file=sys.stderr)
    time.sleep(0.1)
