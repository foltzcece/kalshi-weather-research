"""Multiple-testing check, step 2: t-stats, corrections, placebo, deflated Sharpe for the live leads.
Reads noise/lead_rows.csv (from leads.py). Writes noise/noise_results.txt.
Research only. Usage: python3 noise/stats.py
"""
import os, numpy as np, pandas as pd
from scipy import stats as S
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); H = os.path.dirname(os.path.abspath(__file__))
OUT = []
def say(s=""): print(s); OUT.append(s)

# ---------------- 1. Honest tally of every idea / variant looked at (Nov 20-24 2026) ----------------
# Counts are result lines that compare a rule with zero/market (discovery runs only; re-runs of an already
# fixed rule on held-out data are confirmations, not new trials). Rounded UP where a count was fuzzy.
TALLY = [
    ("45-day + 1-year backtests: long-shot YES, favourite bands, snapshots", 40, "backtest_results.txt, favorite_results.txt"),
    ("Limit-order offset / fill-rule tuning (1-6c, touch/through, halves)", 60, "tune_results.txt, limit_results*.txt"),
    ("Forecast models v1, v2 (ensembles, blends), live.py filters, HRRR", 12, "v2_backtest_results.txt, archive/live_before_*"),
    ("Out-of-sample audit variants + walk-forward price bands", 20, "audit/audit_results.txt, walkforward_results.txt"),
    ("Niche hunt: pre-registered temperature slices", 116, "niches/slice_results.csv (disc rows)"),
    ("Niche hunt: rain slices + launch / new-market checks", 35, "niches/rain_slices.py, launch_check.py"),
    ("Rain radar + cece storm-motion models (by hour, fall + summer)", 36, "rain_radar_results*.txt"),
    ("Rain price-band trading rules (bands x hourly/7 AM x season)", 20, "rain slices, rainno"),
    ("Execution study cells (timing, offset, cancel, chase)", 116, "exec/results_main.txt"),
    ("Market making (spreads, sides, bands, holding times)", 74, "mm/mm_results*.txt"),
    ("Thanksgiving liquidity-reward placements", 5, "mm/tg_*"),
    ("Speed-edge lock harvest variants (latency, caps, min price)", 36, "edge/capture_test_period/latency/capped.txt"),
    ("Out-of-box: momentum, lead-lag, bucket sums, carry-over, lows lock", 54, "ootb/*_results.txt"),
]
M = sum(c for _, c, _ in TALLY)
say("1. HOW MANY THINGS WE TRIED (honest tally, Nov 20-24 2026)")
for f, c, src in TALLY: say(f"   {c:4d}  {f}   [{src}]")
say(f"   ----\n   {M:4d}  total trials (counting every variant; many are correlated, so the 'effective' number is lower)")
say(f"   ~{len(TALLY)} distinct idea families\n")

# ---------------- 2. Hurdles ----------------
z2 = lambda p: S.norm.isf(p / 2)
say("2. THE HURDLE (|t| needed for a 5% false-alarm rate, two-sided)")
say(f"   classic single test:                      t > {z2(0.05):.2f}")
say(f"   'p < 0.005' (Benjamin et al. 2018):        t > {z2(0.005):.2f}   <- this is where 2.8 comes from")
say(f"   Harvey-Liu-Zhu 2016 (finance factor zoo): t > 3.00")
for m in (len(TALLY), 116, M, 1000):
    say(f"   Bonferroni for {m:4d} trials:              t > {z2(0.05 / m):.2f}")
say("")

# ---------------- 3. Leads: t-stats (dates clustered) ----------------
R = pd.read_csv(os.path.join(H, "lead_rows.csv"))
LABEL = {
    "highs_lock_fast2min": ("Highs lock, fast feed (+2 min, 20 ctr)", "held-out 21 mo"),
    "highs_lock_free": ("Highs lock, free feed (paper-traded)", "held-out 21 mo"),
    "lows_lock_free15": ("Lows lock, free feed (+15 min)", "discovery 3 mo"),
    "carry_over_60min": ("Midnight carry-over highs (+60 min)", "held-out 21 mo"),
    "limit_minus_ask_untouched": ("Limit order vs paying ask (per chance)", "untouched yr+11 cities"),
    "fav_limit_untouched": ("Favourite 50-65c + limit", "untouched yr+11 cities"),
    "fav_limit_tuning_year": ("  (same, on the year it was tuned on)", "tuning year"),
    "rain_no_hourly": ("Rain NO at 50-70c, first hour seen", "fall discovery 3 mo"),
    "rain_no_7am": ("Rain NO at 50-70c, 7 AM run only", "fall 3 mo"),
}
def tstat(g):
    d = g.groupby("date")[["cost", "pnl"]].sum(); r = d.pnl.sum() / d.cost.sum(); D = len(d)
    e = d.pnl - r * d.cost; se = np.sqrt((e ** 2).sum() * D / (D - 1)) / d.cost.sum()
    return r, se, r / se, D, d
res = []
for lead, (lab, per) in LABEL.items():
    g = R[R.lead == lead]; r, se, t, D, d = tstat(g)
    res.append(dict(lead=lead, label=lab, period=per, n=len(g), days=D, ret=r, se=se, t=t, p=2 * S.norm.sf(abs(t)), daily=d))
T = pd.DataFrame(res)

# ---------------- 4. Corrections ----------------
# The other M - k trials have no stored p-values; we treat them as p = 1 (none significant). That is the
# conservative choice for BH (it makes BH stricter) and makes no difference to Bonferroni/Holm.
fam = T[T.lead != "fav_limit_tuning_year"].copy()
ps = np.sort(fam.p.values); k = len(ps)
def holm_pass(p):
    for i, q in enumerate(ps):                  # step-down: stop at first failure
        if q > 0.05 / (M - i): return p < q
        if q == p: return True
    return True
bh_max = max([q for i, q in enumerate(ps) if q <= (i + 1) * 0.05 / M], default=-1)
T["bonf"] = T.p < 0.05 / M
T["holm"] = [holm_pass(p) if l != "fav_limit_tuning_year" else False for p, l in zip(T.p, T.lead)]
T["bh"] = (T.p <= bh_max) & (T.lead != "fav_limit_tuning_year")
T["hlz"] = T.t > 3.0

# ---------------- 5. Deflated Sharpe (Bailey & Lopez de Prado 2014), N = M trials ----------------
def dsr(daily, N):
    x = (daily.pnl / daily.cost).values; Tn = len(x)
    sr = x.mean() / x.std(ddof=1); g3 = S.skew(x); g4 = S.kurtosis(x, fisher=False)
    em = 0.5772156649; v = 1.0 / (Tn - 1)        # spread of Sharpe across N null trials ~ 1/sqrt(T)
    sr0 = np.sqrt(v) * ((1 - em) * S.norm.ppf(1 - 1 / N) + em * S.norm.ppf(1 - 1 / (N * np.e)))
    den = np.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2))
    return sr, S.norm.cdf((sr - sr0) * np.sqrt(Tn - 1) / den)
T["sr_day"], T["dsr"] = zip(*[dsr(d, M) for d in T.daily])

# ---------------- 6. Placebo: same prices, random buckets (lock leads) ----------------
# Question: is the lock profit just "selling cheap YES is profitable", or does the lock signal matter?
# Pool = every bucket snapshot (6 PM / 7 AM) where we could sell YES at the bid, regardless of outcome.
# For each real bet at stale YES price p we draw a random snapshot with bid within 1c of p, same $ size.
fee = lambda p: np.ceil(0.07 * p * (1 - p) * 100 - 1e-9) / 100
def pool(files, pref):
    h = pd.concat([pd.read_csv(os.path.join(P, f)) for f in files])
    h = h[h.series.str.startswith(pref) & (h.yes_bid >= 0.02) & (h.yes_bid <= 0.60)]
    c = 1 - h.yes_bid + fee(h.yes_bid); ret = ((h.result == "no").astype(float) - c) / c
    return pd.DataFrame({"cent": (h.yes_bid * 100).round().astype(int), "ret": ret.values})
rng = np.random.default_rng(11)
def placebo(lead, pl, reps=2000):
    g = R[R.lead == lead]; cents = np.clip((g.price * 100).round().astype(int).values, 3, 50); w = g.cost.values
    by = {c: pl[(pl.cent >= c - 1) & (pl.cent <= c + 1)].ret.values for c in np.unique(cents)}
    sims = np.empty(reps)
    for i in range(reps):
        sims[i] = sum(w[j] * by[c][rng.integers(len(by[c]))] for j, c in enumerate(cents)) / w.sum()
    obs = g.pnl.sum() / g.cost.sum()
    return obs, sims.mean(), np.percentile(sims, 97.5), (np.sum(sims >= obs) + 1) / (reps + 1)
hi_pool = pool(["history.csv", "audit/history_oos.csv"], "KXHIGH"); lo_pool = pool(["history_more.csv"], "KXLOWT")
PL = {"highs_lock_free": hi_pool, "highs_lock_fast2min": hi_pool, "carry_over_60min": hi_pool, "lows_lock_free15": lo_pool}

say("3. THE LEADS (return per $ staked; t uses whole-day clusters; p two-sided)")
say(f"   {'lead':<42}{'data':<24}{'bets':>5}{'days':>5}{'return':>8}{'t':>7}  {'p':>8}  Bonf Holm  BH  HLZ3  DSR")
for _, x in T.iterrows():
    yn = lambda b: " yes" if b else "  no"
    say(f"   {x.label:<42}{x.period:<24}{x.n:5d}{x.days:5d}{x.ret:+8.1%}{x.t:7.2f}  {x.p:8.1e} {yn(x.bonf)} {yn(x.holm)} {yn(x.bh)} {yn(x.hlz)}  {x.dsr:4.2f}")
say(f"   (corrections over M={M} trials; HLZ3 = t > 3.0; DSR = deflated Sharpe, chance the true daily Sharpe > the best of {M} lucky tries)")
say("   'limit vs ask' is a paired difference: dollars per chance (fill or not), so its 'return' = cents gained per $1 contract offered.\n")

say("4. PLACEBO: same stale prices, random buckets (outcome not known) - does the lock signal matter?")
for lead, pl in PL.items():
    obs, mu, hi, pv = placebo(lead, pl)
    say(f"   {LABEL[lead][0]:<42} real {obs:+6.1%}   random-bucket placebo avg {mu:+6.1%} (97.5% of placebos below {hi:+6.1%})   placebo p = {pv:.4f}")
say("")
say("Notes")
say(" - Rain NO rows rebuilt from rain_candles.csv with a simple 'first hour with mid 50-70c' rule (n=296, +13.8%),")
say("   close to but not identical to the original test (n=226, +11.8%); 7 AM uses history_more.csv snapshots.")
say(" - Lock leads: the outcome is almost known when we bet, so luck is NOT the main risk. The untested risks are")
say("   fills (25% of later prints assumed), queue position vs fast competitors, and live data feed timing.")
say(" - Lows lock and rain NO were found and measured on the same ~3 months; they have no held-out test yet.")
open(os.path.join(H, "noise_results.txt"), "w").write("\n".join(OUT) + "\n")
T.drop(columns="daily").to_csv(os.path.join(H, "noise_table.csv"), index=False)
