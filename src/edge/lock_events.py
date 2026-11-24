"""Model-free test of the speed edge.
Official settlement = round(max of the 5-minute running mean of 1-minute temps) (97% match, gap_check.py).
So the moment that running value passes a bucket's edge, the bucket is decided ("dead" or "locked").
For every such event in the trade-tape period (7 cities, Sep 22 - Nov 19 2026), measure what still traded
at stale prices after a fast feed (1-min data, 2 min latency) or the free feed (NWS whole-degC 5-min obs
or hourly METAR tenths, ~10 min latency) would have known.
Output: lock_events.csv (one row per decided bucket) and printed summary."""
import csv, os, datetime as dt, numpy as np, pandas as pd, collections
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(HERE)
S2C = {"KXHIGHNY": "NYC", "KXHIGHCHI": "MDW", "KXHIGHMIA": "MIA", "KXHIGHAUS": "AUS", "KXHIGHDEN": "DEN", "KXHIGHLAX": "LAX", "KXHIGHPHIL": "PHL"}
OFF = {"NYC": -5, "MDW": -6, "MIA": -5, "AUS": -6, "DEN": -7, "LAX": -8, "PHL": -5}
METAR_MIN = 51  # routine hourly METAR minute (tenths of degC); varies 51-56 by station, 51 is the earliest

def run_settle(t):
    rm = pd.Series(t).rolling(5).mean().to_numpy()          # 5-min mean ending at minute m (NaN if gap)
    s = np.floor(np.fmax.accumulate(np.nan_to_num(rm, nan=-999)) + 0.5)
    return rm, s

def free_lower(rm):
    """Lower bound on the settle value the free feed can PROVE by each minute."""
    lb = np.full(1440, -999.0)
    for m in range(1440):
        if not np.isfinite(rm[m]): continue
        if m % 5 == 0:   # whole-degC 5-min obs: true value >= (c - 0.5) degC
            c = np.floor((rm[m] - 32) * 5 / 9 + 0.5)
            lb[m] = np.ceil(((c - 0.5) * 9 / 5 + 32) - 0.5)
        if m % 60 == METAR_MIN:  # METAR tenths: ~exact
            lb[m] = max(lb[m], np.floor(rm[m] + 0.5))
    return np.fmax.accumulate(lb)

def first(mask):
    i = np.argmax(mask); return int(i) if mask[i] else None

def main():
    z = np.load(os.path.join(HERE, "days.npz"))
    days = {(s, d): t for s, d, t in zip(z["stn"], z["date"], z["temps"])}
    mk = {}
    for r in csv.DictReader(open(os.path.join(P, "history.csv"))):
        if r["series"] in S2C and r["date"] >= "2026-09-22":
            mk[r["ticker"]] = r
    tr = pd.read_csv(os.path.join(P, "mm", "trades.csv"), usecols=["series", "ticker", "ts", "yes_price", "count", "taker_side"])
    tr = tr[tr.series.isin(S2C)]
    tr["ts"] = pd.to_datetime(tr.ts, format="ISO8601", utc=True)
    out = []
    for tk, g in tr.groupby("ticker"):
        if tk not in mk: continue
        r = mk[tk]; stn = S2C[r["series"]]; d = r["date"]
        if (stn, d) not in days: continue
        rm, s = run_settle(days[(stn, d)]); lb = free_lower(rm)
        st = r["strike_type"]; fl = float(r["floor"]) if r["floor"] else None; cp = float(r["cap"]) if r["cap"] else None
        if st == "between": kind, thr = "dead", cp + 1          # dead once settle >= cap+1
        elif st == "less": kind, thr = "dead", cp               # value < cap fails once settle >= cap
        else: kind, thr = "lock", fl + 1                        # value > floor once settle >= floor+1
        m_fast = first(s >= thr)
        if m_fast is None: continue
        m_free = first(lb >= thr)
        base = pd.Timestamp(d, tz="UTC") - pd.Timedelta(hours=OFF[stn])
        t_fast = base + pd.Timedelta(minutes=m_fast)
        t_free = base + pd.Timedelta(minutes=m_free) if m_free is not None else None
        # price that is now "wrong": YES for dead, NO for lock
        g = g.assign(wrong=np.where(kind == "dead", g.yes_price, 1 - g.yes_price),
                     mins=(g.ts - t_fast).dt.total_seconds() / 60)
        row = dict(ticker=tk, stn=stn, date=d, kind=kind, settle_final=s[-1], result=r["result"],
                   local_fast=m_fast / 60, free_delay=(m_free - m_fast) if m_free is not None else np.nan)
        for lo, hi in [(-30, 0), (0, 2), (2, 5), (5, 10), (10, 30), (30, 120), (120, 2000)]:
            w = g[(g.mins >= lo) & (g.mins < hi)]
            hot = w[w.wrong >= 0.03]
            row[f"vwap_{lo}_{hi}"] = (w.wrong * w["count"]).sum() / w["count"].sum() if len(w) else np.nan
            row[f"edge$_{lo}_{hi}"] = (hot["count"] * (hot.wrong - 0.07 * hot.wrong * (1 - hot.wrong))).sum()
            row[f"ctr_{lo}_{hi}"] = hot["count"].sum()
        out.append(row)
    df = pd.DataFrame(out); df.to_csv(os.path.join(HERE, "lock_events.csv"), index=False)
    ok = (df.kind == "dead") & (df.result == "no") | (df.kind == "lock") & (df.result == "yes")
    print(f"{len(df)} decided buckets; settle rule agreed with Kalshi result on {ok.mean():.1%}")
    print("free feed proves it later by (min): median", df.free_delay.median(), " mean", round(df.free_delay.mean(), 1))
    for k in ["dead", "lock"]:
        x = df[df.kind == k]
        print(f"\n{k}: n={len(x)}  local hour of event median {x.local_fast.median():.1f}")
        for c in [c for c in df.columns if c.startswith("vwap")]:
            w = c[5:]
            print(f"  window {w:>10} min: avg 'wrong' price {x[c].mean()*100:5.1f}c   contracts at >=3c {x['ctr_'+w].sum():9.0f}"
                  f"   gross profit if all captured ${x['edge$_'+w].sum():8.0f}   (per day ${x['edge$_'+w].sum()/x.date.nunique():.0f})")
if __name__ == "__main__": main()
