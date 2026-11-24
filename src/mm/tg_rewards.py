"""Estimate what a paper quoter would earn from Kalshi's Liquidity Incentive Program on the
Thanksgiving rain/snow markets, from order-book snapshots in mm/tg_books.jsonl.

Scoring (Kalshi help center, LIP article): once a second, per side (YES bids, NO bids separately),
walk from the best price outward until resting size reaches TARGET; only those orders qualify (if a
side can't reach TARGET the whole snapshot is excluded and pays nobody). Reference price = first
level where cumulative size reaches TARGET/5. Orders at or better than it score size x 1.0; worse
orders score size x DISCOUNT^(ticks behind). Your side share = your score / all qualifying scores.
Period score = your snapshot shares / all shares (each snapshot is worth 2: one per side).
Reward = period score x period reward x (non-excluded snapshots / all snapshots).

We add our own order of Q contracts per side at a chosen placement and recompute our share.
Placement 'improve' = one tick better than the best (front of the line, first to be filled); 'best' = join the best price; 'ref' = sit at the reference price of the book without us
(full credit, fewer fills); 'ref+1' = one tick behind the reference (half credit)."""
import json, os, sys, collections, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
PROG = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else None


def side_share(levels, q, place, target, disc, tick=0.01, opp_best=0.0):
    """levels: [(price, size)] bids for one side, any order. Returns (our share, both-side-ok flag, our price)."""
    lv = sorted(((round(float(p), 4), float(s)) for p, s in levels), reverse=True)
    if not lv: return 0.0, False, None
    # reference price without us
    cum = 0; ref = lv[-1][0]
    for p, s in lv:
        cum += s
        if cum >= target / 5: ref = p; break
    best = lv[0][0]
    if place == "improve":                          # one tick better than the best bid, if it doesn't cross
        price = round(best + tick, 4) if best + tick < 1 - opp_best - 1e-9 else best
    else:
        price = best if place == "best" else ref if place == "ref" else round(ref - tick, 4)
    # insert our order at the back of the queue at that price
    book = [(p, s, False) for p, s in lv]
    i = 0
    while i < len(book) and book[i][0] >= price - 1e-9: i += 1
    book.insert(i, (price, q, True))
    # qualifying orders up to target
    cum = 0; qual = []
    for p, s, me in book:
        if cum >= target: break
        qual.append((p, s, me)); cum += s
    if cum < target: return 0.0, False, price
    cum = 0; ref2 = qual[-1][0]
    for p, s, me in qual:
        cum += s
        if cum >= target / 5: ref2 = p; break
    score = lambda p, s: s * (1.0 if p >= ref2 - 1e-9 else disc ** round((ref2 - p) / tick))
    tot = sum(score(p, s) for p, s, _ in qual); mine = sum(score(p, s) for p, s, me in qual if me)
    return (mine / tot if tot else 0.0), True, price


def main():
    progs = {}
    for p in PROG or []:
        if not p["paid_out"]:
            progs[p["market_ticker"]] = p
    snaps = collections.defaultdict(list)
    for line in open(os.path.join(HERE, "tg_books.jsonl")):
        r = json.loads(line); snaps[r["ticker"]].append(r)
    Q = int(os.environ.get("Q", "100"))
    rows = []
    for t, ss in snaps.items():
        p = progs.get(t)
        if not p: continue
        reward = p["period_reward"] / 10000; target = float(p["target_size_fp"]); disc = p["discount_factor_bps"] / 10000
        for place in ("improve", "best", "ref", "ref+1"):
            shares, ok_n, capital = [], 0, []
            prices = [float(x[0]) for s in ss for x in s["yes"] + s["no"]]
            tick = 0.001 if any(abs(x * 100 - round(x * 100)) > 1e-6 for x in prices) else 0.01
            for s in ss:
                ys, yok, yp = side_share(s["yes"], Q, place, target, disc, tick, max([float(x[0]) for x in s["no"]] or [0]))
                ns, nok, np_ = side_share(s["no"], Q, place, target, disc, tick, max([float(x[0]) for x in s["yes"]] or [0]))
                ok = yok and nok; ok_n += ok
                shares.append((ys + ns) / 2 if ok else 0.0)
                capital.append(Q * ((yp or 0) + (np_ or 0)))
            frac_ok = ok_n / len(ss)
            # period score ~ our average share over included snapshots; payout scales by included fraction
            avg = (sum(shares) / ok_n) if ok_n else 0.0
            rows.append(dict(t=t, place=place, tick=tick, reward=reward, share=avg, ok=frac_ok, est=avg * reward * frac_ok,
                             cap=st.mean(capital), last=ss[-1].get("last")))
    for place in ("improve", "best", "ref", "ref+1"):
      for grp in ("THANKSGIVING", "SNOWDAYS"):
        R = [r for r in rows if r["place"] == place and grp in r["t"]]
        if not R: continue
        tot = sum(r["est"] for r in R); cap = sum(r["cap"] for r in R)
        print(f"\n{grp} placement={place}, Q={Q}/side: est reward ${tot:,.0f} for the period across {len(R)} markets, "
              f"capital at risk ${cap:,.0f}, markets with both sides at target {sum(r['ok'] > 0 for r in R)}")
        for r in sorted(R, key=lambda r: -r["est"])[:int(os.environ.get("TOP", "8"))]:
            print(f"   {r['t']:<34} pool ${r['reward']:>5.0f}  our share {r['share']:5.1%}  included {r['ok']:4.0%}  est ${r['est']:6.2f}  capital ${r['cap']:,.0f}")
    json.dump(rows, open(os.path.join(HERE, "tg_rewards_est.json"), "w"), indent=0)


if __name__ == "__main__":
    main()
