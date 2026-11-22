# Kalshi weather markets research

**[Read the one-page research summary (PDF)](Kalshi_Weather_Research_Summary.pdf)**

Backtests and paper-trading models for Kalshi's daily weather markets (city high temperature and daily rain), Nov 2025 to Nov 2026.

**Status:** research and paper trading only. No real money has been traded yet. Results so far do not show a proven forecasting edge. See the [research summary](Kalshi_Weather_Research_Summary.pdf) for the findings.

Built with Claude as a coding assistant; research questions, testing decisions and GIS methods are mine.

## Main findings

- Kalshi weather prices are well calibrated. The one consistent bias is cheap long shots: buying YES under 35¢ lost 14% to 74% per dollar.
- My forecast models (NWS, and a multi-model ensemble) were less accurate than the market (Brier 0.122 vs 0.106) and lost money when traded.
- Buying the favorite bucket at 50 to 65¢ returned about +4% in the 7 cities I tuned on, and lost 6 to 8% in 11 new cities. I read the in-sample result as mostly luck.
- Placing limit orders 3¢ under the ask added 3 to 5 points in both sets of cities, with about 95% of orders filling. This is the one result that held up out of sample.
- Radar storm-motion timing for rain markets did not beat the market overall (Brier 0.1349 vs 0.1347).

## Layout

| Path | What it is |
| --- | --- |
| `src/backfill.py`, `src/analyze_history.py` | Download one year of Kalshi prices and check calibration by price band |
| `src/favorite.py`, `src/analyze_favorite.py` | Favorite-bucket strategy and its backtest |
| `src/limit_backtest.py`, `src/tune_favorite.py` | Limit-order fill simulation and tuning (touch vs trade-through fill rules) |
| `src/picks.py`, `src/picks_v2.py`, `src/v2_backtest.py` | Forecast models: NWS (v1) and Open-Meteo ensemble (v2) |
| `src/live.py`, `src/onemin_calibrate.py` | Same-day model from live airport readings, calibrated on one-minute ASOS data |
| `src/tracker.py` | Scores paper picks, Brier, and HRRR shadow test |
| `src/radar_sample.py`, `src/storm_eta.py`, `src/rain_candles.py`, `src/rain_radar_test.py` | Radar features and storm-cell arrival times for rain markets |
| `gis/` | Rain gauge locations for each Kalshi rain market (CSV and GeoJSON) |
| `results/` | Text output of each backtest |

## Data

Raw data is not included. It comes from public sources: the Kalshi public API, the National Weather Service API, Open-Meteo, and the Iowa State Mesonet archive (radar and one-minute ASOS). `backfill.py` rebuilds the price history.

Requires Python 3.10+; `numpy` for the radar scripts. Everything else is standard library.
