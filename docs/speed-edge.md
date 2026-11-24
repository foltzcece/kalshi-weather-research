# Speed edge: stale prices on decided buckets

*November 23 to 24, 2026. Code: `src/edge/`, `src/lock.py`. Results: `results/edge/`.*

## Settlement rule

Using Iowa State Mesonet one-minute ASOS temperatures, the official daily high equals **round(max of the 5-minute running mean)**. This matched 98.4% of complete days, compared with 58% for the raw one-minute maximum.

## Strategy

During the day the running value only goes up, so once it passes a bucket's upper edge that bucket cannot win. If the market still prices it at 3 to 50¢, buy NO on it (or YES on the bucket that is now certain) as a taker, and hold to settlement.

## Simulation

The simulation assumes I get 25% of the later trades at the stale price, caps size at 20 or 100 contracts per bucket, charges the taker fee, and uses real settlements. Light quality control (despiking, skipping buckets decided before 2 AM local) removes almost all losses.

| Period | Fast feed, +2 min, max 20 | Free feed, +15 min, max 20 |
| --- | --- | --- |
| Dec 2024 to Nov 2025 (held out) | +16.4% | +14.4% |
| Nov 2025 to Sep 2026 (held out) | +15.0% | +12.9% |
| Sep to Nov 2026 (discovery) | +15.1% | +10.8% |

Per active day at 20 contracts, a fast feed is worth about $10 and the free NWS feed about $2 to $3, on roughly one day in four.

## Why this might not survive

- Stale bids were hit on 2,644 of 6,078 decided buckets, with a median of 3.3 minutes to the first hit and about 600 contracts per bucket. Faster traders are already competing for this, and the simulation's 25% share is an assumption.
- The latency and reliability of a paid real-time feed are unverified. One station (Central Park) has no live one-minute feed anywhere I could find.
- Whole-degree-Celsius feeds are unsafe for this: they match the settlement rule only 65% of the time.

## Run window

92% of the free-feed value falls between 10 AM and 6 PM Central. Running 1 to 5 PM Central captures about two-thirds (`src/edge/run_window.py`).

## Status

Paper testing only: an hourly cloud pass and an every-minute local loop during 1 to 5 PM Central, both on the free feed. No paid feed and no real orders before the December 4 review.
