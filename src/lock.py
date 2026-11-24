"""
Lock harvester paper test (free NWS feed). Approved by cece 2026-11-23. Paper only: places NO real orders.

Why: Kalshi's official high = round(max 5-minute average temp) (edge/gap_check.py, 97-98%). Once the
high-so-far provably passes a bucket's edge, that bucket is decided, yet it often keeps trading at stale
prices. Backtest (edge/capture2.py): ~+15% per $ on 21 held-out months; free feed finds ~1/10 as many as
a fast 1-minute feed. Unknown: are the stale bids really there to take? This test answers that by reading
the LIVE order book every time the free feed proves a bucket decided.

Free-feed proof (same as backtest): hourly METAR T-group (tenths degC) = exact; 5-minute obs in whole degC
=> true value >= c - 0.5 degC. QC fixed before the held-out test: ignore readings >3C above the median of
readings within +-45 min; skip buckets first proven before 2 AM local. 6-hour max groups NOT used.

Paper rule: dead bucket (can't win) -> buy NO by hitting stale YES bids priced 3-50c; locked "greater"
bucket (already won) -> buy YES by hitting stale NO bids 3-50c. Up to 20 contracts per bucket per day,
best price first, taker fee 0.07*p*(1-p). One entry per ticker. Every pass also logs the stale book for
every decided bucket (lock_snapshots.csv) so we can see how long stale bids last.

Usage: python3 lock.py pass | loop [passes] [minutes] | settle | report
"""
import csv, math, os, re, sys, time, statistics as st, datetime as dt
from picks import CITIES, KALSHI, get
from live import STATIONS, UA

HERE = os.path.dirname(os.path.abspath(__file__))
PICKS = os.path.join(HERE, "paper_picks_lock.csv")
SNAPS = os.path.join(HERE, "lock_snapshots.csv")
MIN_PX, MAX_PX, MAX_CTR = 0.03, 0.50, 20
PCOLS = ["logged_utc", "series", "date", "ticker", "bucket", "kind", "side", "proof_utc", "proof_local", "settle_lb",
         "contracts", "avg_price", "cost", "fee", "levels", "status", "result", "pnl"]
SCOLS = ["snap_utc", "series", "date", "ticker", "kind", "proof_utc", "mins_since_proof", "settle_lb",
         "best_stale", "stale_ctr_3_50c", "stale_ctr_any"]
C2F = lambda c: c * 9 / 5 + 32


def obs_lower_bounds(station, midnight_utc):
    """[(time, provable lower bound on the official settle value)] from the free NWS feed."""
    d = get(f"https://api.weather.gov/stations/{station}/observations?start="
            f"{midnight_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=500", UA)
    raw = []
    for f in d["features"]:
        p = f["properties"]; c = p["temperature"]["value"]
        if c is None: continue
        ts = dt.datetime.fromisoformat(p["timestamp"])
        if ts < midnight_utc: continue
        m = re.search(r"(?<!\S)T([01])(\d{3})[01]\d{3}(?!\S)", p.get("rawMessage") or "")
        if m:
            raw.append((ts, (-1 if m.group(1) == "1" else 1) * int(m.group(2)) / 10, True))
        else:
            raw.append((ts, float(c), False))
    out = []
    for ts, c, exact in raw:
        near = [x for t2, x, _ in raw if t2 != ts and abs((t2 - ts).total_seconds()) <= 2700]
        if len(near) >= 2 and c > st.median(near) + 3:      # spike QC
            continue
        if exact:
            lb = math.floor(C2F(c) + 0.5)
        else:
            c0 = round(c)                                    # whole degC report
            lb = math.floor(C2F(c0 - 0.5) + 0.5)
        out.append((ts, lb))
    return sorted(out)


def decided(m, bounds):
    """(kind, threshold, proof time, lb) if the free feed proves the market decided, else None."""
    stype = m.get("strike_type")
    if stype == "between": kind, thr = "dead", m["cap_strike"] + 1
    elif stype == "less": kind, thr = "dead", m["cap_strike"]
    elif stype == "greater": kind, thr = "lock", m["floor_strike"] + 1
    else: return None
    best = -999
    for ts, lb in bounds:
        best = max(best, lb)
        if best >= thr:
            return kind, thr, ts, max(b for _, b in bounds)
    return None


def stale_levels(m, kind):
    """Bids on the WRONG side we could sell into, as (price of wrong side, qty), best first."""
    ob = get(f"{KALSHI}/markets/{m['ticker']}/orderbook").get("orderbook_fp", {}) or {}
    lv = ob.get("yes_dollars" if kind == "dead" else "no_dollars") or []
    return sorted(((float(p), float(q)) for p, q in lv), reverse=True)


def read(path):
    return list(csv.DictReader(open(path))) if os.path.exists(path) else []


def write_rows(path, cols, rows, append=True):
    new = not os.path.exists(path) or not append
    with open(path, "a" if append else "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        if new: w.writeheader()
        w.writerows(rows)


def one_pass():
    now = dt.datetime.now(dt.timezone.utc)
    have = {r["ticker"] for r in read(PICKS)}
    snaps, picks, errs = [], [], []
    for series, (city, lat, lon, off) in CITIES.items():
        local_now = now + dt.timedelta(hours=off); today = local_now.date()
        midnight = dt.datetime.combine(today, dt.time(0), dt.timezone.utc) - dt.timedelta(hours=off)
        try:
            mkts = [m for m in get(f"{KALSHI}/markets?series_ticker={series}&status=open&limit=100")["markets"]
                    if dt.datetime.strptime(m["event_ticker"].split("-")[1], "%y%b%d").date() == today]
            bounds = obs_lower_bounds(STATIONS[series], midnight) if mkts else []
        except Exception as e:
            errs.append(f"{series}: {e}"); continue
        for m in mkts:
            dec = decided(m, bounds)
            if not dec: continue
            kind, thr, proof, lb = dec
            proof_local = proof + dt.timedelta(hours=off)
            if proof_local.hour < 2: continue                   # midnight carry-over rule
            try:
                lv = stale_levels(m, kind)
            except Exception as e:
                errs.append(f"{m['ticker']}: {e}"); continue
            stale = [(p, q) for p, q in lv if MIN_PX - 1e-9 <= p <= MAX_PX + 1e-9]
            snaps.append(dict(snap_utc=now.strftime("%Y-%m-%d %H:%M"), series=series, date=str(today), ticker=m["ticker"],
                              kind=kind, proof_utc=proof.strftime("%Y-%m-%d %H:%M"),
                              mins_since_proof=round((now - proof).total_seconds() / 60), settle_lb=lb,
                              best_stale=stale[0][0] if stale else "", stale_ctr_3_50c=round(sum(q for _, q in stale), 1),
                              stale_ctr_any=round(sum(q for p, q in lv if p >= MIN_PX), 1)))
            if m["ticker"] in have or not stale: continue
            got = cost = fee = 0.0; used = []
            for p, q in stale:
                take = min(q, MAX_CTR - got)
                if take <= 0: break
                got += take; cost += take * (1 - p); fee += take * 0.07 * p * (1 - p); used.append(f"{p:.2f}x{take:g}")
            fee = math.ceil(fee * 100) / 100
            picks.append(dict(logged_utc=now.strftime("%Y-%m-%d %H:%M"), series=series, date=str(today), ticker=m["ticker"],
                              bucket=m.get("yes_sub_title") or m.get("subtitle") or "", kind=kind,
                              side="NO" if kind == "dead" else "YES", proof_utc=proof.strftime("%Y-%m-%d %H:%M"),
                              proof_local=proof_local.strftime("%H:%M"), settle_lb=lb, contracts=round(got, 2),
                              avg_price=round(cost / got, 4), cost=round(cost, 2), fee=fee, levels=" ".join(used),
                              status="open", result="", pnl=""))
            have.add(m["ticker"])
    if snaps: write_rows(SNAPS, SCOLS, snaps)
    if picks: write_rows(PICKS, PCOLS, picks)
    print(f"{now:%H:%M} UTC: {len(snaps)} decided buckets seen, {len(picks)} new paper picks"
          + (f", errors: {'; '.join(errs)}" if errs else ""))
    for p in picks:
        print(f"  {p['side']} {p['ticker']} {p['contracts']:g} ctr @ {p['avg_price']:.2f} (levels {p['levels']}), proven {p['proof_local']} local")
    return errs


def settle():
    rows = read(PICKS); changed = 0
    for r in rows:
        if r["status"] != "open": continue
        try:
            m = get(f"{KALSHI}/markets/{r['ticker']}")["market"]
        except Exception:
            continue
        res = m.get("result")
        if res not in ("yes", "no"): continue
        won = (res == "no") == (r["side"] == "NO")
        r["status"], r["result"] = "settled", res
        r["pnl"] = round((float(r["contracts"]) if won else 0) - float(r["cost"]) - float(r["fee"]), 2); changed += 1
    if changed: write_rows(PICKS, PCOLS, rows, append=False)
    return changed


def report():
    settle()
    rows = read(PICKS); s = [r for r in rows if r["status"] == "settled"]
    snaps = read(SNAPS)
    cost = sum(float(r["cost"]) + float(r["fee"]) for r in s); pnl = sum(float(r["pnl"]) for r in s)
    wins = sum(float(r["pnl"]) > 0 for r in s)
    seen = {x["ticker"] for x in snaps}; with_stale = {x["ticker"] for x in snaps if x["best_stale"]}
    line = (f"Lock (free feed): {len(rows)} paper picks, {len(s)} settled, {wins}/{len(s)} right, "
            f"P&L ${pnl:+.2f} on ${cost:.2f} staked ({(pnl / cost if cost else 0):+.1%}; backtest ~+13-15%). "
            f"Decided buckets seen {len(seen)}, with stale bids 3-50c at our look {len(with_stale)}.")
    print(line); return line


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pass"
    if cmd == "pass":
        one_pass(); settle()
    elif cmd == "loop":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 6; gap = float(sys.argv[3]) if len(sys.argv) > 3 else 9
        for i in range(n):
            one_pass()
            if i < n - 1: time.sleep(gap * 60)
        settle()
    elif cmd == "settle":
        print(settle(), "settled")
    elif cmd == "report":
        report()
