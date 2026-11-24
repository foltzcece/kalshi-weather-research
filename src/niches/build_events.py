"""Build one table of temperature-market rows with pre-registered slice features.
Inputs: history.csv (7 cities highs, 1 yr), history_more.csv (11 more cities + lows, 90 days).
Output: niches/temp_rows.csv"""
import pandas as pd, numpy as np, os, holidays
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(HERE)
frames = []
for f, src in [("history.csv", "main7"), ("history_more.csv", "more")]:
    d = pd.read_csv(os.path.join(P, f)); d["src"] = src; frames.append(d)
for f in ["history_launch_apr.csv", "history_launch_aug.csv"]:
    fp = os.path.join(HERE, f)
    if os.path.exists(fp):
        d = pd.read_csv(fp); d["src"] = f.split(".")[0].replace("history_", ""); frames.append(d)
d = pd.concat(frames)
d = d[d.series != "KXRAIN"].copy()
d = d.drop_duplicates(["ticker", "snap"])
d["kind"] = np.where(d.series.str.contains("LOW"), "low", "high")
d["city"] = d.series.str.replace(r"^KX(HIGH|LOW)T?", "", regex=True)
d["date"] = pd.to_datetime(d.date)
d["mid"] = (d.yes_bid + d.yes_ask) / 2
d["y"] = (d.result == "yes").astype(int)
d["center"] = np.where(d.strike_type == "between", (d.floor + d.cap) / 2,
               np.where(d.strike_type == "less", d.cap - 1.5, d.floor + 1.5))
d = d[(d.yes_ask > 0)]
g = d.groupby(["series", "date", "snap"])
d["msum"] = g.mid.transform("sum")
d["pn"] = d.mid / d.msum
d["imean"] = (d.pn * d.center).groupby([d.series, d.date, d.snap]).transform("sum")
d["isd"] = np.sqrt((d.pn * (d.center - d.imean) ** 2).groupby([d.series, d.date, d.snap]).transform("sum"))
d["favp"] = g.mid.transform("max")
d["is_fav"] = (d.mid == d.favp).astype(int)
d = d.sort_values(["series", "date", "snap", "center"])
d["rank"] = d.groupby(["series", "date", "snap"]).cumcount()
favrank = d[d.is_fav == 1].groupby(["series", "date", "snap"])["rank"].first().rename("favrank")
d = d.join(favrank, on=["series", "date", "snap"])
d["offset"] = d["rank"] - d["favrank"]
d["tail"] = (d.strike_type != "between").astype(int)
d["warm"] = (d.center > d.imean).astype(int)
# actual (settled value) per series-date
d["actual"] = pd.to_numeric(d.actual, errors="coerce")
win = d[d.y == 1].groupby(["series", "date"]).center.first().rename("wincenter")
d = d.join(win, on=["series", "date"])
d["actual"] = d.actual.fillna(d.wincenter)
act = d.groupby(["series", "date"]).actual.first().reset_index()
act["prev_actual"] = act.groupby("series").actual.shift(1)
act["prev_gap"] = (act.date - act.groupby("series").date.shift(1)).dt.days
act["trail15"] = act.groupby("series").actual.transform(lambda s: s.shift(1).rolling(15, min_periods=8).mean())
d = d.merge(act[["series", "date", "prev_actual", "prev_gap", "trail15"]], on=["series", "date"])
d.loc[d.prev_gap != 1, "prev_actual"] = np.nan
d["chg"] = d.imean - d.prev_actual           # market-expected change vs yesterday
d["anom"] = d.imean - d.trail15              # market-expected departure from last 15 days
d["dow"] = d.date.dt.dayofweek
d["weekend"] = (d.dow >= 5).astype(int)
us = holidays.US(years=[2025, 2026])
hol = set(us.keys())
import datetime as dt
for y in (2025, 2026):
    hol |= {dt.date(y, 12, 24), dt.date(y, 12, 31)}
    # day after Thanksgiving
    tg = [k for k, v in us.items() if "Thanksgiving" in v and k.year == y]
    hol |= {t + dt.timedelta(days=1) for t in tg}
d["holiday"] = d.date.dt.date.isin(hol).astype(int)
d["month"] = d.date.dt.month
d["fee_yes"] = np.ceil(0.07 * d.yes_ask * (1 - d.yes_ask) * 100 - 1e-9) / 100
noa = 1 - d.yes_bid
d["fee_no"] = np.ceil(0.07 * noa * (1 - noa) * 100 - 1e-9) / 100
d.to_csv(os.path.join(HERE, "temp_rows.csv"), index=False)
print(d.shape, d.groupby("src").size().to_dict())
