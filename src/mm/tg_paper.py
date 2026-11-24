"""Forward paper test of earning Kalshi liquidity rewards on the Thanksgiving rain/snow markets.

At every book snapshot (mm/tg_books.jsonl, ~hourly) we re-place a YES bid and a NO bid of Q contracts
at the chosen placement (see tg_rewards.py), as long as the market closes more than STOP_H hours away
and our net position is under CAP. Between snapshots, fills come from Kalshi's trade tape: a trade
through our price fills us; a trade at our price fills us only after the size that was ahead of us
in the queue has traded. Reward share at each snapshot comes from tg_rewards.side_share.
Rewards: share averaged over snapshots x period reward x included fraction (same formula as Kalshi).
Positions are held to settlement (or marked at the last mid if not settled yet).
Usage: python3 tg_paper.py  -> prints a summary and writes mm/tg_paper_results.txt"""
import json, os, sys, time, collections, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from picks import KALSHI, get
from tg_rewards import side_share
HERE = os.path.dirname(os.path.abspath(__file__))
Q, CAP, STOP_H = int(os.environ.get("Q", "100")), int(os.environ.get("CAP", "200")), float(os.environ.get("STOP_H", "30"))
PLACES = os.environ.get("PLACES", "best,ref,ref+1").split(",")
ts = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def trades(ticker, start):
    out, cur = [], ""
    for _ in range(50):
        d = get(f"{KALSHI}/markets/trades?ticker={ticker}&limit=1000&min_ts={int(start)}" + (f"&cursor={cur}" if cur else ""))
        out += [(ts(x["created_time"]), float(x["yes_price_dollars"]), float(x["count_fp"]), x["taker_side"]) for x in d.get("trades", [])]
        cur = d.get("cursor")
        if not cur or not d.get("trades"): break
        time.sleep(0.2)
    return sorted(out)


def main():
    progs = {p["market_ticker"]: p for p in json.load(open(os.path.join(HERE, "tg_programs.json")))
             if not p["paid_out"] and "THANKSGIVING" in p["series_ticker"]}
    snaps = collections.defaultdict(list)
    for line in open(os.path.join(HERE, "tg_books.jsonl")):
        r = json.loads(line)
        if r["ticker"] in progs: snaps[r["ticker"]].append(r)
    out = [__doc__.split("Usage")[0].strip(), "", f"Q={Q}/side, CAP={CAP} net, stop quoting {STOP_H:.0f} h before close", ""]
    summary = {p: collections.Counter() for p in PLACES}
    for t, ss in sorted(snaps.items()):
        time.sleep(0.3); p = progs[t]; m = get(f"{KALSHI}/markets/{t}")["market"]
        close = ts(m["close_time"]); result = m.get("result")
        tick = 0.001 if any(abs(float(x[0]) * 100 - round(float(x[0]) * 100)) > 1e-6 for s in ss for x in s["yes"] + s["no"]) else 0.01
        tr = trades(t, ts(ss[0]["t"]))
        target, disc, pool = float(p["target_size_fp"]), p["discount_factor_bps"] / 10000, p["period_reward"] / 10000
        ybids = lambda s: [float(x[0]) for x in s["yes"]]; nbids = lambda s: [float(x[0]) for x in s["no"]]
        last_mid = None
        for place in PLACES:
            pos = cash = 0.0; filled = 0.0; shares = []; ok_n = 0
            for i, s in enumerate(ss):
                t0 = ts(s["t"]); t1 = ts(ss[i + 1]["t"]) if i + 1 < len(ss) else t0 + 3600
                yb, nb = max(ybids(s) or [0]), max(nbids(s) or [0])
                last_mid = (yb + 1 - nb) / 2
                quoting = close - t0 > STOP_H * 3600
                if not quoting:
                    shares.append(0.0); ok_n += 1; continue
                ys, yok, yp = side_share(s["yes"], Q, place, target, disc, tick, nb)
                ns, nok, np_ = side_share(s["no"], Q, place, target, disc, tick, yb)
                ok = yok and nok; ok_n += ok; shares.append((ys + ns) / 2 if ok else 0.0)
                # queue ahead of us at our price
                qy = sum(float(q) for pr, q in s["yes"] if abs(float(pr) - (yp or -1)) < 1e-9)
                qn = sum(float(q) for pr, q in s["no"] if abs(float(pr) - (np_ or -1)) < 1e-9)
                ry, rn = min(Q, CAP - pos), min(Q, CAP + pos)
                for (tt, price, n, side) in tr:
                    if not (t0 <= tt < t1): continue
                    if side == "no" and yp and ry > 0:           # taker sells YES -> may hit our YES bid
                        if price < yp - 1e-9: f = min(ry, n)
                        elif abs(price - yp) < 1e-9: use = min(qy, n); qy -= use; f = min(ry, n - use)
                        else: f = 0
                        if f > 0: ry -= f; pos += f; cash -= f * yp; filled += f
                    elif side == "yes" and np_ and rn > 0:       # taker buys YES -> may hit our NO bid at 1-np
                        yes_px = 1 - np_
                        if price > yes_px + 1e-9: f = min(rn, n)
                        elif abs(price - yes_px) < 1e-9: use = min(qn, n); qn -= use; f = min(rn, n - use)
                        else: f = 0
                        if f > 0: rn -= f; pos -= f; cash -= f * np_; filled += f
            # NO contracts held = -pos when pos<0; value at settlement
            if result in ("yes", "no"): Y = 1.0 if result == "yes" else 0.0; settled = True
            else: Y = last_mid; settled = False
            value = pos * Y if pos > 0 else -pos * (1 - Y)
            matched = (filled - abs(pos)) / 2                     # a YES + NO pair always pays $1 at settlement
            trade_pnl = cash + value + matched
            frac = ok_n / len(ss); avg = sum(shares) / ok_n if ok_n else 0.0
            reward = avg * pool * frac
            c = summary[place]; c["reward"] += reward; c["trade"] += trade_pnl; c["filled"] += filled; c["markets"] += 1; c["settled"] += settled
            out.append(f"  {t:<34} {place:<6} share {avg:5.1%}  reward ${reward:6.2f}  filled {filled:6.0f}  net pos {pos:+5.0f}  trading P&L ${trade_pnl:+7.2f}{'' if settled else ' (marked to mid)'}")
    out.append("")
    for place, c in summary.items():
        out.append(f"TOTAL {place:<6}: rewards ${c['reward']:,.2f}  trading P&L ${c['trade']:+,.2f}  net ${c['reward'] + c['trade']:+,.2f}  "
                   f"contracts filled {c['filled']:,.0f}  markets {c['markets']} ({c['settled']} settled)")
    txt = "\n".join(out); print("\n".join(out[-len(summary):]))
    open(os.path.join(HERE, "tg_paper_results.txt"), "w").write(txt + "\n")


if __name__ == "__main__":
    main()
