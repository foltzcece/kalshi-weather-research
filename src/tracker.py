"""
Paper-trading tracker for the Kalshi pick model.

  python3 tracker.py run      settle old picks, score live markets, log the 2 best as paper picks
  python3 tracker.py settle   only settle finished picks
  python3 tracker.py report   print the scorecard

Files (same folder):
  paper_picks.csv  the 2 picks per run, with result and profit/loss
  shadow_log.csv   every side the model scored, so we can check calibration on far more data
"""
import csv, json, os, sys, datetime as dt, urllib.request
import picks, picks_v2, live, favorite
from picks import KALSHI, get
MODELS = {"v1": picks.evaluate, "v2": picks_v2.evaluate, "live": live.evaluate, "fav": favorite.evaluate}

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.join(HERE, "paper_picks.csv")          # v1 (kept so its history stays put)
PAPER_FILES = {"v1": PAPER, "v2": os.path.join(HERE, "paper_picks_v2.csv"),
               "live": os.path.join(HERE, "paper_picks_live.csv"),
               "fav": os.path.join(HERE, "paper_picks_fav.csv")}
FORECASTS = os.path.join(HERE, "forecast_log.csv")    # each source's forecast vs the actual high
BIAS = os.path.join(HERE, "bias.json")
SHADOW = os.path.join(HERE, "shadow_log.csv")
START_BANKROLL = 100.0
MAX_STAKE_SHARE = 0.05   # never risk more than 5% of the paper bankroll on one pick (more picks per run now)
PICKS_PER_RUN = 6        # up to 6 per strategy per run, still max one per city-day

PAPER_COLS = ["run_time", "ticker", "city", "date", "side", "bucket", "forecast", "sigma",
              "our_prob", "price", "fee", "edge", "contracts", "cost", "status", "result",
              "won", "pnl", "settle_value", "limit", "limit_filled", "limit_pnl"]
SHADOW_COLS = ["model", "run_time", "ticker", "city", "date", "lead", "side", "bucket", "forecast",
               "sigma", "our_prob", "price", "edge", "status", "won", "settle_value", "boundary"]
FC_COLS = ["run_time", "series", "city", "date", "lead", "source", "forecast", "status", "actual"]


def read(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write(path, cols, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def market(ticker):
    return get(f"{KALSHI}/markets/{ticker}")["market"]


LIMIT_OFFSET = 0.03      # suggested limit order: 3 cents under the asking price (best in limit_backtest.py)
MAKER_FEE_RATE = 0.0175  # resting-order fee (conservative; some markets charge 0)


def maker_fee(price, n):
    import math
    return math.ceil(MAKER_FEE_RATE * n * price * (1 - price) * 100 - 1e-9) / 100


def limit_filled(r):
    """Would a resting order at r['limit'] have filled before the market closed?
    Counts any later trade at or better than our limit on our side."""
    start = int(dt.datetime.strptime(r["run_time"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=dt.timezone.utc).timestamp())
    lim, cursor = float(r["limit"]), ""
    for _ in range(10):
        d = get(f"{KALSHI}/markets/trades?ticker={r['ticker']}&min_ts={start}&limit=1000" + (f"&cursor={cursor}" if cursor else ""))
        for t in d.get("trades", []):
            px = float(t["yes_price_dollars"] if r["side"] == "YES" else t["no_price_dollars"])
            if px <= lim:
                return True
        cursor = d.get("cursor")
        if not cursor:
            return False
    return False


def settle():
    cache, changed = {}, 0

    def fetch(ticker):
        if ticker not in cache:
            try:
                cache[ticker] = market(ticker)
            except Exception as e:
                print(f"! could not fetch {ticker}: {e}", file=sys.stderr)
                cache[ticker] = {}
        return cache[ticker]

    for path, cols in [(f, PAPER_COLS) for f in PAPER_FILES.values()] + [(SHADOW, SHADOW_COLS)]:
        rows = read(path)
        for r in rows:
            if r["status"] != "open":
                continue
            m = fetch(r["ticker"])
            if m.get("result") not in ("yes", "no"):
                continue
            won = (m["result"] == "yes") == (r["side"] == "YES")
            r.update(status="settled", won=int(won), settle_value=m.get("expiration_value", ""))
            if path in PAPER_FILES.values():
                n, cost = int(r["contracts"]), float(r["cost"])
                r.update(result=m["result"], pnl=round((n if won else 0) - cost, 2))
                if r.get("limit"):
                    try:
                        filled = limit_filled(r)
                        lim = float(r["limit"])
                        r.update(limit_filled=int(filled),
                                 limit_pnl=round((n if won else 0) - n * lim - maker_fee(lim, n), 2) if filled else 0)
                    except Exception as e:
                        print(f"! limit check {r['ticker']}: {e}", file=sys.stderr)
            changed += 1
        write(path, cols, rows)

    # actual highs for the forecast log: any settled market of that city-day carries it
    actual = {}
    for r in read(SHADOW):
        if r["status"] == "settled" and r["settle_value"] not in ("", None):
            actual[(r["ticker"].split("-")[0], r["date"])] = float(r["settle_value"])
    fc = read(FORECASTS)
    for r in fc:
        if r["status"] == "open" and (r["series"], r["date"]) in actual:
            r.update(status="settled", actual=actual[(r["series"], r["date"])])
    write(FORECASTS, FC_COLS, fc)
    update_bias(fc)
    return changed


def update_bias(fc):
    """Per city: average of (combined forecast - actual) over settled day-ahead forecasts.
    Shrunk toward 0 until there are ~10 days of data, so one odd day can't swing it."""
    by = {}
    for r in fc:
        if r["status"] == "settled" and r["source"] == "combined_raw" and r["lead"] == "1":
            by.setdefault(r["series"], []).append(float(r["forecast"]) - float(r["actual"]))
    bias = {s: round(sum(e) / (len(e) + 10) , 2) for s, e in by.items()}
    json.dump(bias, open(BIAS, "w"), indent=1)


def bankroll(version="v1"):
    return START_BANKROLL + sum(float(r["pnl"] or 0) for r in read(PAPER_FILES[version]) if r["status"] == "settled")


def choose(picks_list, paper, bank):
    taken = {p["ticker"].rsplit("-", 1)[0] for p in paper}
    chosen = []
    for r in picks_list:                  # best first; one pick per city-day
        ev = r["ticker"].rsplit("-", 1)[0]
        if ev in taken:
            continue
        cost_each = r["price"] + r["fee"]
        n = min(r["contracts"], int(bank * MAX_STAKE_SHARE // cost_each))
        if n < 1:
            continue
        taken.add(ev)
        chosen.append(r | {"contracts": n, "cost": round(n * cost_each, 2),
                           "limit": round(max(0.01, r["price"] - LIMIT_OFFSET), 2)})
        if len(chosen) == PICKS_PER_RUN:
            break
    return chosen


def run(versions=("v1", "v2", "fav")):
    settled = settle()
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    shadow, fc = read(SHADOW), read(FORECASTS)
    for version in versions:
        evaluate = MODELS[version]
        bank = bankroll(version)
        try:
            picks_list, rows = evaluate(bank)
        except Exception as e:
            print(f"! {version} failed: {e}", file=sys.stderr)
            continue
        for r in rows:
            shadow.append({k: r.get(k, "") for k in SHADOW_COLS} | {"model": version, "run_time": now, "status": "open"})
        if version == "live":   # HRRR shadow test: calibration log only, no paper picks
            for r in live.HRRR_ROWS:
                shadow.append({k: r.get(k, "") for k in SHADOW_COLS} | {"model": "live_hrrr", "run_time": now, "status": "open"})
            for pk in live.PEAK_LOG:   # final-high estimate per source (lead 0), settled like the rest
                fc.append(pk | dict(run_time=now, lead=0, status="open", actual=""))
        if version == "v2":   # log each source's forecast once per city-day-run
            seen = set()
            for r in rows:
                key = (r["ticker"].split("-")[0], r["date"])
                if key in seen:
                    continue
                seen.add(key)
                srcs = json.loads(r["sources"])
                srcs["combined_raw"] = sum(srcs.values()) / len(srcs)
                for name, val in srcs.items():
                    fc.append(dict(run_time=now, series=key[0], city=r["city"], date=r["date"], lead=r["lead"],
                                   source=name, forecast=round(val, 1), status="open", actual=""))
        paper = read(PAPER_FILES[version])
        chosen = choose(picks_list, paper, bank)
        new = [{k: c.get(k, "") for k in PAPER_COLS} | {"run_time": now, "status": "open", "result": "",
               "won": "", "pnl": "", "settle_value": "", "limit": c["limit"],
               "limit_filled": "", "limit_pnl": ""} for c in chosen]
        write(PAPER_FILES[version], PAPER_COLS, paper + new)
        print(f"\n[{version}] paper bankroll ${bank:.2f}, scored {len(rows)} sides")
        for c in chosen:
            extra = f" (model {c['model_prob']:.0%}, market {c['market_prob']:.0%})" if version != "v1" else ""
            print(f"PICK {c['side']} {c['bucket']} {c['city']} {c['date']}: ours {c['our_prob']:.0%}{extra} "
                  f"vs price {c['price']} (+fee {c['fee']}), {c['contracts']} contracts = ${c['cost']}; "
                  f"suggested limit order {c['limit']}  [{c['ticker']}]")
        if not chosen:
            print("No pick cleared the edge bar this run.")
    write(SHADOW, SHADOW_COLS, shadow)
    write(FORECASTS, FC_COLS, fc)
    print(f"\nSettled {settled} rows this run.")
    report()


def brier(rows, key):
    return sum((float(r[key]) - int(r["won"])) ** 2 for r in rows) / len(rows)


def report():
    print("\n--- Scorecard ---")
    for version, path in PAPER_FILES.items():
        allp = read(path)
        paper = [r for r in allp if r["status"] == "settled"]
        line = f"[{version}] picks settled {len(paper)}, open {len(allp) - len(paper)}"
        if paper:
            wins = sum(int(r["won"]) for r in paper)
            pnl = sum(float(r["pnl"]) for r in paper)
            staked = sum(float(r["cost"]) for r in paper)
            line += (f". Won {wins}/{len(paper)} (model expected {sum(float(r['our_prob']) for r in paper):.1f}). "
                     f"P&L ${pnl:+.2f} on ${staked:.2f} ({pnl / staked:+.1%}). Bankroll ${bankroll(version):.2f}")
        print(line)
        lim = [r for r in paper if r.get("limit_filled") not in ("", None)]
        if lim:
            f = [r for r in lim if r["limit_filled"] == "1"]
            print(f"    limit orders: filled {len(f)}/{len(lim)}; P&L on filled ones ${sum(float(r['limit_pnl']) for r in f):+.2f} "
                  f"vs ${sum(float(r['pnl']) for r in f):+.2f} paying the ask")

    shadow = [r for r in read(SHADOW) if r["status"] == "settled"]
    if shadow:
        print("\nAccuracy on every scored side (Brier score, lower is better):")
        for version in list(MODELS) + ["live_hrrr"]:
            rows = [r for r in shadow if (r.get("model") or "v1") == version]
            if rows:
                print(f"  {version}: model {brier(rows, 'our_prob'):.3f} vs market {brier(rows, 'price'):.3f}  ({len(rows)} sides)")
                # Hourly models score the same market again every run, which overcounts. Honest
                # version: keep only the first time each market side was scored, and count city-days.
                first = {}
                for r in rows:
                    first.setdefault((r["ticker"], r["side"]), r)
                uniq = list(first.values())
                days = len({(r["city"], r["date"]) for r in uniq})
                if len(uniq) < len(rows):
                    print(f"      first look only: model {brier(uniq, 'our_prob'):.3f} vs market {brier(uniq, 'price'):.3f}  "
                          f"({len(uniq)} sides, {days} independent city-days)")
        print("  If the market's number is lower, the market was more accurate than that model.")

    fc = [r for r in read(FORECASTS) if r["status"] == "settled"]
    if fc:
        print("\nForecast error by source, day-ahead (average miss in degrees; + means forecast ran warm):")
        by = {}
        for r in fc:
            if r["lead"] == "1":
                by.setdefault(r["source"], []).append(float(r["forecast"]) - float(r["actual"]))
        for s, e in sorted(by.items(), key=lambda kv: sum(map(abs, kv[1])) / len(kv[1])):
            print(f"  {s:<14} avg miss {sum(map(abs, e)) / len(e):.1f}F   bias {sum(e) / len(e):+.1f}F   ({len(e)} city-days)")
    # Paid 1-minute feed paper trail: markets the live model skipped because the free whole-degC
    # data couldn't tell which side of a bucket edge the high landed on. If we had known the answer
    # (what a 1-minute feed tells you), buying the right side at the price then was worth (1 - price).
    edge_rows = [r for r in shadow if r.get("model") == "live" and r.get("boundary") == "1"]
    if edge_rows:
        first = {}
        for r in edge_rows:
            first.setdefault((r["ticker"], r["side"]), r)
        wins = [r for r in first.values() if r["won"] == "1"]
        upside = sum(1 - float(r["price"]) - picks.kalshi_fee(float(r["price"])) for r in wins if float(r["price"]) <= 0.92)
        mispriced = [r for r in wins if float(r["price"]) <= 0.80]
        days = len({(r["city"], r["date"]) for r in first.values()})
        print(f"\n1-minute feed paper trail: {len(first)} edge-zone market sides over {days} city-days. Knowing the answer "
              f"at first look would have paid ${upside:.2f} per contract in total; {len(mispriced)} winning sides still cost 80c or less "
              f"(where a fast feed would have real room). Feed costs ~$30/month.")
    if fc:
        same_day = {}
        for r in fc:
            if r["lead"] == "0" and r["source"].startswith("live_"):
                same_day.setdefault(r["source"], []).append(float(r["forecast"]) - float(r["actual"]))
        if same_day:
            print("Same-day final-high estimate, NWS hourly vs HRRR (all afternoon runs):")
            for s, e in sorted(same_day.items()):
                print(f"  {s:<14} avg miss {sum(map(abs, e)) / len(e):.1f}F   bias {sum(e) / len(e):+.1f}F   ({len(e)} runs)")
    bias = json.load(open(BIAS)) if os.path.exists(BIAS) else {}
    if bias:
        print("City bias corrections now in use:", bias)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "run":
        run(tuple(sys.argv[2:]) or ("v1", "v2", "fav"))      # e.g. "tracker.py run live"
    else:
        {"settle": settle, "report": report}[cmd]()
