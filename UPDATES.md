# Research updates

## November 24, 2026 (evening): luck check and new stale-price variants

Still research and paper trading only. No real money has been traded.

### How many ideas I have tested, and the bar that implies

Counting every variant since Nov 20, I have run about **624 trials** across roughly 13 idea families. If you test that many things, some will look good by chance. A Bonferroni correction for 624 trials puts the bar at **t > 3.94** for a 5% false-alarm rate, compared with 1.96 for a single test. Many of the trials are correlated, so this bar is conservative. Each t-statistic below clusters bets by day. Full table: [results/noise/noise_results.txt](results/noise/noise_results.txt); code: `src/noise/`.

### Clears the bar

| Idea | Data | Bets | Return per $ | t |
| --- | --- | ---: | ---: | ---: |
| Stale prices on decided high buckets, fast feed | 21 held-out months | 2,654 | +19.2% | 33.2 |
| Same, free feed (the version being paper-traded) | 21 held-out months | 242 | +15.0% | 8.2 |
| Limit order vs paying the ask | untouched year + 11 cities | 1,885 | +2.5¢ per chance | 7.8 |
| Midnight carry-over highs | 21 held-out months | 47 | +19.1% | 5.3 |
| Stale prices on decided low buckets, free feed | 3 months, **no hold-out yet** | 94 | +10.3% | 5.1 |

The carry-over result rests on only 47 bets, and the lows result was found and measured on the same three months.

### Does not clear the bar

| Idea | Data | Bets | Return per $ | t |
| --- | --- | ---: | ---: | ---: |
| Favorite 50 to 65¢ + limit | untouched year + 11 cities | 1,716 | +0.7% | 0.26 |
| (same, on the year it was tuned on) | tuning year | 1,454 | +8.5% | 2.99 |
| Rain NO at 50 to 70¢ | fall 2026 | 127 to 296 | +4% to +14% | 0.4 to 1.9 |

### Placebo test

To check whether the stale-price profit really comes from knowing a bucket is decided, I bought random buckets at the same stale prices instead. The placebo lost 2% to 5% on average, while the real versions made +10% to +19% (placebo p = 0.0005 for all four). The profit comes from the information, not from something about cheap prices in general.

### What is still untested

Luck is not the main risk for the stale-price strategies, because the outcome is nearly known when the bet is placed. The real risk is execution. The simulations assume I would get 25% of the later trades at the stale price. Faster traders hit these prices within about 2 to 3 minutes, and my actual fills, queue position and live feed timing have not been measured. That is what the paper tests are for.

### New out-of-the-box tests

Daily lows follow the same settlement rule as highs, and the stale-price idea worked there in a first test (+10%, no hold-out yet). Highs decided just after midnight also work and are not a speed race, but they are rare. Momentum, neighboring-city lead-lag and bucket-sum arbitrage were dead ends. Details: [docs/out-of-the-box-edges.md](docs/out-of-the-box-edges.md).

The paper test `src/lock.py` now covers decided lows and carry-over highs (excluding New York) alongside decided highs. All of these are scored at the December 4 review.

### New code and results

| Path | What it is |
| --- | --- |
| `src/noise/`, `results/noise/` | Trial tally, multiple-testing hurdles, day-clustered t-stats, deflated Sharpe, placebo |
| `src/ootb/`, `results/ootb/` | Lows lock, midnight carry-over, momentum, lead-lag, bucket sums |
| `src/lock.py` | Paper test now includes lows and carry-over highs |
| `src/edge/run_window.py` | Updated run-window study |

## November 24, 2026 (morning): what changed since the Nov 22 upload

Still research and paper trading only. No real money has been traded. Every return below is from backtests or paper trades, and most of the ranges are wide.

### What got weaker

- **Favorite + 3¢ limit.** I re-ran the lead strategy on a year of data it was never tuned on (7 cities, Dec 2024 to Nov 2025). It returned **+2.1%** (95% range −5.0% to +9.3%, 991 fills). Pooling every untouched dataset gives **+0.7%** (−4.6% to +5.8%). The +8% I reported before was mostly luck and selection, so I now plan around break-even. Details: [docs/favorite-oos-audit.md](docs/favorite-oos-audit.md).
- **Rain NO at 50 to 70¢.** At the 7 AM run time it returned only about +2% this fall, with a range of roughly ±20%. It stays in paper testing as a long shot.
- **Market making.** Quoting both sides at the best price lost money in backtests (high-temp markets −1.5% to −3.8%, rain +0.4% to −1.6%). Faster firms capture most of the maker profit. I am not pursuing it.
- **Niche hunt.** I pre-registered 116 slices of the temperature markets (city, weekday, price band, timing, big forecast swings) plus rain and new-market launches, and tested them with a strict significance bar and held-out data. Nothing was tradeable. The only robust pattern, long shots overpriced by 1 to 3¢, is about the size of the spread.

### What held up

- **Limit orders instead of paying the ask** add about 4 to 5 points in every dataset, tuned or not. This is the most reliable result in the project. Details: [docs/execution-study.md](docs/execution-study.md).
- **Paper tracker fixes.** Daily weather markets charge no maker fee, so the tracker's maker fee is now 0. Limits are now placed at the lower of (ask − 3¢) and the current best bid, and an order only counts as filled when a trade prints strictly below my price (`src/tracker.py`).

### New lead: stale prices on settled buckets

- I found the settlement rule: the official high equals the rounded maximum of the 5-minute running mean of the one-minute ASOS temperature (98.4% exact on complete days).
- Once the running value rules a bucket out, its price sometimes stays up for a few minutes. In simulation, buying the winning side of those stale prices returned about **+15% per dollar** in each of three periods, including 21 held-out months. That simulation assumes I would get 25% of later trades at those prices.
- **The catch:** stale bids were hit on 2,644 of 6,078 decided buckets, with a median of 3.3 minutes to the first hit. Fast traders are already doing this, and I don't know what share I would actually get. With a free (slower) data feed the simulated value is about a tenth of what a fast feed would catch.
- **Testing now:** an hourly paper test with the free feed (`src/lock.py`), plus an every-minute local version run 1 to 5 PM Central. That window held about two-thirds of the free-feed opportunities (`src/edge/run_window.py`). I have not bought a paid feed. Details: [docs/speed-edge.md](docs/speed-edge.md).

### Also running

- The previous live model (no bucket-edge filter, old settlement handling) runs next to the new one as its own paper strategy.
- A paper test of Kalshi's liquidity rewards on the Thanksgiving rain/snow markets (`src/mm/tg_*.py`), scored after the markets close. Rewards look meaningful at the reference price, but fills so far cost money, so the net is unclear.

All paper tests are reviewed together on December 4, 2026.

### New code and results in this update

| Path | What it is |
| --- | --- |
| `src/audit/`, `results/audit/` | Out-of-sample audit and walk-forward test of the favorite strategy |
| `src/exec/`, `results/exec/` | Limit-order execution study on full trade tapes (placement time, price, cancel rules, queue-realistic fills) |
| `src/edge/`, `results/edge/` | Settlement rule from one-minute data, stale-price capture simulations, run-window study |
| `src/mm/`, `results/mm/` | Market-making backtests, maker markouts, Thanksgiving liquidity-reward paper test |
| `src/niches/`, `results/niches/` | Pre-registered niche scan, launch and rain checks |
| `src/lock.py` | Paper test for the stale-price strategy |
| `src/rainno.py`, `src/hrrr_noaa.py` | Rain NO paper strategy; HRRR pulled directly from NOAA |
| `src/tracker.py` | Zero maker fee, new limit price, strict fill rule |
