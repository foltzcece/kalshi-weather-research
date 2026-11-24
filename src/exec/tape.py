"""Shared helpers for execution research: load trade tapes, rebuild quotes, simulate a resting
limit order. Research only (does not touch the live pick scripts).

Quote rebuild: on Kalshi a trade whose taker bought YES printed at the best YES ask; a trade whose
taker bought NO printed at the best YES bid. So the last YES-taker price before time t ~ the ask,
and the last NO-taker price ~ the bid.

Fill rules for our resting buy-YES order at price L placed at time t0:
  touch   : any later trade at <= L (optimistic, we are first in line at L)
  through : a later trade strictly below L (pessimistic, we were surely reached)
  queue Q : we fill once Q contracts have traded AT L after we joined (we sit behind Q contracts
            of older orders at that price), or as soon as any trade prints below L.
"""
import csv, os, pickle, collections, datetime as dt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
CACHE = os.environ.get("TAPE_CACHE", "/tmp/claude-0/tapecache")

# standard-time UTC offsets of each city's settlement station
TZ = {"NY": -5, "CHI": -6, "MIA": -5, "AUS": -6, "DEN": -7, "LAX": -8, "PHIL": -5,
      "ATL": -5, "BOS": -5, "DAL": -6, "DC": -5, "HOU": -6, "LV": -8, "MIN": -6, "OKC": -6,
      "PHX": -7, "SEA": -8, "SFO": -8}


def city(series):
    return series.replace("KXHIGHT", "").replace("KXHIGH", "")


def utc_offset(series, date):
    """Local clock offset incl. US daylight time (2nd Sun Mar - 1st Sun Nov; Phoenix none)."""
    c = city(series); off = TZ[c]
    if c == "PHX":
        return off
    y = date.year
    mar = dt.date(y, 3, 8); mar += dt.timedelta(days=(6 - mar.weekday()) % 7)
    nov = dt.date(y, 11, 1); nov += dt.timedelta(days=(6 - nov.weekday()) % 7)
    return off + 1 if mar <= date < nov else off


def local_ts(series, date, day_offset, hour):
    """Unix time of `hour` local on (event date + day_offset)."""
    d = date + dt.timedelta(days=day_offset)
    tz = dt.timezone(dt.timedelta(hours=utc_offset(series, d)))
    return dt.datetime.combine(d, dt.time(0), tz).timestamp() + hour * 3600


def load(name):
    """name in {'main' (mm/trades.csv highs), 'extra', 'year'} -> dict ticker -> market dict."""
    os.makedirs(CACHE, exist_ok=True)
    pk = os.path.join(CACHE, name + ".pkl")
    if os.path.exists(pk):
        return pickle.load(open(pk, "rb"))
    path = {"main": os.path.join(PARENT, "mm", "trades.csv"),
            "extra": os.path.join(HERE, "tapes_extra.csv"),
            "year": os.path.join(HERE, "tapes_year.csv")}[name]
    tmp = collections.defaultdict(list); meta = {}
    for r in csv.DictReader(open(path)):
        if not r["series"].startswith("KXHIGH"):
            continue
        t = r["ticker"]
        meta[t] = (r["series"], r["date"], r["result"])
        ts = dt.datetime.fromisoformat(r["ts"].replace("Z", "+00:00")).timestamp()
        tmp[t].append((ts, float(r["yes_price"]), float(r["count"]), r["taker_side"] == "yes"))
    out = {}
    for t, L in tmp.items():
        L.sort()
        a = np.array(L)
        s, d, res = meta[t]
        out[t] = dict(series=s, date=dt.date.fromisoformat(d), won=res == "yes", event=t.rsplit("-", 1)[0],
                      ts=a[:, 0], px=np.round(a[:, 1], 2), qty=a[:, 2], yes_taker=a[:, 3].astype(bool))
    pickle.dump(out, open(pk, "wb"))
    return out


def quote(m, t, max_age=6 * 3600):
    """(bid, ask) rebuilt from the last NO-taker / YES-taker prints before t (None if stale)."""
    i = np.searchsorted(m["ts"], t)
    bid = ask = None
    yt, ts, px = m["yes_taker"][:i], m["ts"][:i], m["px"][:i]
    if i:
        ky = np.flatnonzero(yt); kn = np.flatnonzero(~yt)
        if len(ky) and t - ts[ky[-1]] <= max_age:
            ask = px[ky[-1]]
        if len(kn) and t - ts[kn[-1]] <= max_age:
            bid = px[kn[-1]]
    if bid is not None and ask is not None and bid >= ask:   # crossed after a sweep: trust the later print
        if ts[ky[-1]] > ts[kn[-1]]:
            bid = round(ask - 0.01, 2)
        else:
            ask = round(bid + 0.01, 2)
    return bid, ask


def fill(m, t0, t1, L, rule="touch", Q=0.0):
    """Time our resting buy-YES at L (placed t0, cancelled t1) fills, or None."""
    i0 = np.searchsorted(m["ts"], t0, "right"); i1 = np.searchsorted(m["ts"], t1, "right")
    px, ts, q = m["px"][i0:i1], m["ts"][i0:i1], m["qty"][i0:i1]
    if not len(px):
        return None
    below = np.flatnonzero(px < L - 1e-9)
    tb = ts[below[0]] if len(below) else None
    if rule == "through":
        return tb
    at = np.flatnonzero(np.abs(px - L) < 1e-9)
    if rule == "touch":
        cands = [x for x in (tb, ts[at[0]] if len(at) else None) if x is not None]
        return min(cands) if cands else None
    # queue: need cumulative size traded at L (sellers hitting bids at L) to exceed Q
    ta = None
    if len(at):
        cum = np.cumsum(q[at])
        k = np.searchsorted(cum, Q + 1e-9, "right")
        if k < len(at):
            ta = ts[at[k]]
    cands = [x for x in (tb, ta) if x is not None]
    return min(cands) if cands else None


def taker_fee(p):
    import math
    return math.ceil(0.07 * p * (1 - p) * 100 - 1e-9) / 100
