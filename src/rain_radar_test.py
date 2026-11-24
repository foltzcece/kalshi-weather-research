"""
Does radar add anything to Kalshi rain prices? (baseline for cece's GIS ideas)
At 9 AM, 11 AM, 1 PM and 3 PM Central (15/17/19/21Z) on uncertain rain city-days, compare:
  market   = the market's mid price at that hour
  radar    = logistic model using the market price PLUS radar near the gauge (now and so far today)
Scored out-of-sample: the model is fit on 4/5 of the dates and tested on the other 1/5, five times.
If radar can't beat the market's own price here, simple radar features carry no edge.
Output: rain_radar_results.txt
"""
import csv, math, os, collections
import numpy as np
from picks import kalshi_fee
HERE = os.path.dirname(os.path.abspath(__file__))
SET = os.environ.get("RAIN_SET", "")            # "" = Aug-Nov (history_more.csv); "summer" = Jun-Aug
SFX = f"_{SET}" if SET else ""
SRC = "history_summer.csv" if SET == "summer" else "history_more.csv"

price, result = {}, {}
for r in csv.DictReader(open(os.path.join(HERE, f"rain_candles{SFX}.csv"))):
    try:
        b, a = float(r["bid"]), float(r["ask"])
    except ValueError:
        continue
    if a > 0:
        price[(r["ticker"], r["hour_utc"])] = (b, a)
    result[r["ticker"]] = 1 if r["result"] == "yes" else 0
radar = {}
for r in csv.DictReader(open(os.path.join(HERE, f"radar_features{SFX}.csv"))):
    radar[(r["code"], r["valid"])] = [float(r[k]) for k in ("dbz_2km", "dbz_10km", "dbz_30km", "dbz_60km")]
eta = {}
if os.path.exists(os.path.join(HERE, f"storm_eta{SFX}.csv")):
    for r in csv.DictReader(open(os.path.join(HERE, f"storm_eta{SFX}.csv"))):
        e1, e2 = float(r["eta_any"]), float(r["eta_strong"])
        eta[(r["code"], r["valid"])] = [math.exp(-e1 / 60), math.exp(-e2 / 60), math.log1p(float(r["n_arriving"])), float(r["cell_here"])]
X, y, meta = [], [], []
for tk in result:
    code, date = tk.split("-")[-1], None
    ds = tk.split("-")[1]
    import datetime as dt
    date = dt.datetime.strptime(ds, "%y%b%d").date()
    for H in (15, 17, 19, 21):
        hstr = f"{date}T{H:02d}:00Z"
        if (tk, hstr) not in price:
            continue
        b, a = price[(tk, hstr)]
        mid = (b + a) / 2
        if not (0.03 <= mid <= 0.97):
            continue
        now = radar.get((code, hstr))
        if now is None:
            continue
        sofar = [radar.get((code, f"{date}T{h:02d}:00Z")) for h in range(12, H + 1)]
        sofar = [s for s in sofar if s]
        mx2 = max(s[0] for s in sofar); mx10 = max(s[1] for s in sofar)
        feats = [math.log(mid / (1 - mid)),
                 max(now[0], 0) / 50, max(now[1], 0) / 50, max(now[2], 0) / 50, max(now[3], 0) / 50,
                 max(mx2, 0) / 50, max(mx10, 0) / 50, float(mx2 >= 30), float(now[2] >= 30)]
        if eta and (code, hstr) not in eta:
            continue
        feats += eta.get((code, hstr), [])
        X.append(feats); y.append(result[tk]); meta.append((str(date), H, mid, b, a, tk))
X, y = np.array(X), np.array(y)


def fit(X, y, l2=1.0):
    Xb = np.c_[np.ones(len(X)), X]; w = np.zeros(Xb.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-Xb @ w))
        g = Xb.T @ (p - y) + l2 * np.r_[0, w[1:]]
        Hm = Xb.T @ (Xb * (p * (1 - p))[:, None]) + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w -= np.linalg.solve(Hm, g)
    return w


def pred(w, X):
    return 1 / (1 + np.exp(-np.c_[np.ones(len(X)), X] @ w))


dates = sorted({m[0] for m in meta}); fold = {d: i % 5 for i, d in enumerate(dates)}
f = np.array([fold[m[0]] for m in meta])
p_mkt = np.array([m[2] for m in meta]); p_cal = np.zeros(len(y)); p_rad = np.zeros(len(y)); p_eta = np.zeros(len(y))
for k in range(5):
    tr, te = f != k, f == k
    p_cal[te] = pred(fit(X[tr][:, :1], y[tr]), X[te][:, :1])     # market price, recalibrated
    p_rad[te] = pred(fit(X[tr][:, :9], y[tr]), X[te][:, :9])      # market + radar
    p_eta[te] = pred(fit(X[tr], y[tr]), X[te])                    # market + radar + storm ETA (if loaded)
ll = lambda p: -np.mean(y * np.log(np.clip(p, 1e-4, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-4, 1)))
br = lambda p: np.mean((p - y) ** 2)
L = [f"{len(y)} decision points ({len(set(m[5] for m in meta))} rain city-days, {len(dates)} dates), {y.mean():.0%} rained\n",
     "Out-of-sample accuracy (lower is better):",
     f"  market price            Brier {br(p_mkt):.4f}  log loss {ll(p_mkt):.4f}",
     f"  market, recalibrated    Brier {br(p_cal):.4f}  log loss {ll(p_cal):.4f}",
     f"  market + radar          Brier {br(p_rad):.4f}  log loss {ll(p_rad):.4f}"]
if eta:
    L.append(f"  + storm-motion ETA      Brier {br(p_eta):.4f}  log loss {ll(p_eta):.4f}   (cece's storm-motion idea)")
for H in (15, 17, 19, 21):
    s = np.array([m[1] == H for m in meta])
    if s.sum() > 10:
        L.append(f"    {H - 6:>2}:00 CT  n={s.sum():<4} market {np.mean((p_mkt[s] - y[s]) ** 2):.4f}   market+radar {np.mean((p_rad[s] - y[s]) ** 2):.4f}"
                 + (f"   +ETA {np.mean((p_eta[s] - y[s]) ** 2):.4f}" if eta else ""))
L.append("\nTrading test (out-of-sample, pay the ask, 1 contract, edge >= 3c after fees, one trade per city-day = first signal):")
for name, p in (("market recalibrated only", p_cal), ("market+radar", p_rad),) + ((("market+radar+storm ETA", p_eta),) if eta else ()):
    taken, pnl, cost = set(), 0.0, 0.0; n = wins = 0
    for i in np.argsort([m[1] for m in meta], kind="stable"):
        d, H, mid, b, a, tk = meta[i]
        if tk in taken: continue
        for side, q, ask in (("YES", p[i], a), ("NO", 1 - p[i], 1 - b)):
            if 0.03 <= ask <= 0.97 and q - ask - kalshi_fee(ask) >= 0.03:
                taken.add(tk); c = ask + kalshi_fee(ask); won = (y[i] == 1) == (side == "YES")
                pnl += won - c; cost += c; n += 1; wins += won
                break
    L.append(f"  {name}: {n} trades, won {wins}, return {pnl / cost if cost else 0:+.1%} per $ (P&L {pnl:+.2f})")
L.append("\nCalibration: average market price vs how often it rained")
for lo, hi in ((0.03, 0.15), (0.15, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.97)):
    s_ = (p_mkt >= lo) & (p_mkt < hi)
    if s_.sum():
        L.append(f"  priced {lo:.0%}-{hi:.0%}: n={s_.sum():<4} avg price {p_mkt[s_].mean():.0%}  rained {y[s_].mean():.0%}")
w = fit(X, y)
L.append("\nWeights (full data): " + ", ".join(f"{k}={v:+.2f}" for k, v in zip(
    ["const", "logit(price)", "now2", "now10", "now30", "now60", "max2_sofar", "max10_sofar", "rained_2km", "storm_30km", "eta_any", "eta_strong", "n_arriving", "cell_here"], w)))
open(os.path.join(HERE, f"rain_radar_results{SFX}.txt"), "w").write("\n".join(L) + "\n"); print("\n".join(L))
