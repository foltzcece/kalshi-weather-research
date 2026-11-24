# Out-of-sample audit: favorite + limit order

*November 23, 2026. Code: `src/audit/`. Results: `results/audit/`.*

## Question

The favorite strategy (buy the 50 to 65¢ bucket with a limit order) looked like +8% on the year I tuned it on. Does it hold on data I never looked at?

## Rules tested

Favorite 50 to 65¢; limit at min(ask − 3¢, best bid); filled only when a trade prints strictly through the limit; maker fee 0; held to settlement. Confidence ranges use a bootstrap clustered by day.

## Results

| Dataset | Fills | Return | 95% range |
| --- | ---: | ---: | --- |
| 7 cities, untouched year (Dec 2024 to Nov 2025) | 991 | +2.1% | −5.0% to +9.3% |
| 7 cities, tuning year (Nov 2025 to Nov 2026) | 1,454 | +8.5% | +2.8% to +14.0% |
| 11 newer cities, high temp only (Aug to Nov 2026) | 725 | −1.2% | −9.8% to +6.8% |
| All untouched data pooled | | +0.7% | −4.6% to +5.8% |

Paying the ask instead of using a limit order lost 3.4% on the untouched year and 4.1% in the newer cities.

A walk-forward test that re-picked the price band and limit offset each month found no stable choice. One band (65 to 80¢) did well on the untouched year, but it was one of six bands tested and it lost in the tuning year, so I am not chasing it.

## Correction

An earlier "extra cities" result accidentally mixed daily-low and rain markets in with the high-temperature markets. The table above uses high-temperature markets only.

## Verdict

Choosing the favorite is roughly fairly priced. The part that holds up everywhere is using a limit order rather than paying the ask (about +4 to 5 points). I now plan for roughly break-even, not 6%.
