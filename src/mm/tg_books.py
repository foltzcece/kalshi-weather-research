"""Snapshot full order books for the Thanksgiving rain/snow and season snow-days markets in Kalshi's liquidity reward program.
Appends one JSON line per market per run to mm/tg_books.jsonl. Usage: python3 tg_books.py [loop_minutes]"""
import json, os, sys, time, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from picks import KALSHI, get
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "tg_books.jsonl")
SERIES = ["KXRAINTHANKSGIVING", "KXSNOWTHANKSGIVING", "KXSNOWDAYS"]

def snap():
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with open(OUT, "a") as f:
        for s in SERIES:
            for m in get(f"{KALSHI}/markets?series_ticker={s}&status=open&limit=200")["markets"]:
                ob = get(f"{KALSHI}/markets/{m['ticker']}/orderbook").get("orderbook_fp", {})
                f.write(json.dumps({"t": now, "ticker": m["ticker"], "yes": ob.get("yes_dollars") or [],
                                    "no": ob.get("no_dollars") or [], "volume": m.get("volume_fp"),
                                    "last": m.get("last_price_dollars")}) + "\n")
                time.sleep(0.05)

if __name__ == "__main__":
    every = float(sys.argv[1]) if len(sys.argv) > 1 else 0
    while True:
        try: snap()
        except Exception as e: print("!", e, file=sys.stderr, flush=True)
        if not every: break
        time.sleep(every * 60)
