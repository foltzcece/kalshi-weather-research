# Research updates

## November 24, 2026: what changed since the Nov 22 upload

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
