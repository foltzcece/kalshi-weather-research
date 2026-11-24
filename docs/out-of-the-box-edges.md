# Out-of-the-box edge tests

*November 24, 2026. Code: `src/ootb/`. Results: `results/ootb/`.*

These extend the [stale-price work](speed-edge.md) and test a few unrelated ideas.

## Daily lows: same stale-price idea

- The official daily low follows the mirror rule: round(min of the 5-minute running mean). It matched 337 of 345 days.
- Buying the winning side of stale prices after a low bucket was decided, with a free feed acting 15 minutes late at 20 contracts per bucket, returned **+10%** per dollar (95% range +7% to +14%) on 6 cities, Aug 23 to Nov 19, 2026. That is about $130 over three months.
- Other traders hit stale bids a median 2 minutes after the bucket was decided, the same as for highs.
- Most lows are decided between midnight and 6 AM or 7 and 11 PM local time.
- The only losing case was a sensor dip in New York on Sep 19.
- **Caveat:** this was found and measured on the same three months. There is no held-out test yet.

## Midnight carry-over (highs decided before 2 AM)

- Sometimes the day's high is set just after midnight, carried over from a warm evening. The main stale-price test skips these buckets.
- On held-out data (Dec 2024 to Sep 2026), buying these returned +16% to +23% per dollar, and it still worked when acting 1 to 4 hours late, so it is not a speed race.
- It is small: about $7 a month at 20 contracts, from 47 bets in 21 months at the 60-minute setting.
- All rule failures were New York at 12:04 AM, and the three-month discovery period lost money because of one of them (Nov 13). The paper test excludes New York.

## Dead ends

- **Momentum and under-reaction:** markets did not consistently under-react to their own price moves, including around forecast-model run times.
- **Neighboring-city lead-lag:** no usable signal.
- **Bucket sums away from 100¢:** before fees, bids summed above $1 fairly often, but after fees a full-set trade was profitable in only 5 of 12,384 snapshots.

## Status

The stale-price paper test (`src/lock.py`) now also covers daily lows and carry-over highs (excluding New York). All three are scored at the December 4 review.
