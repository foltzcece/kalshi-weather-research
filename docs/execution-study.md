# Limit-order execution study

*November 23, 2026. Code: `src/exec/`. Results: `results/exec/`.*

## Question

Given the same picks, how much does the way the order is placed matter: price, time of day, cancelling unfilled orders, and how fills are counted?

## Method

I replayed full Kalshi trade tapes for three datasets (7 cities Sep to Nov 2026, 7 cities Jan to Sep 2026, and 11 extra cities Aug to Nov 2026) through a simulator that tracks the queue ahead of each order.

## Findings

- **Fill rules.** Queue-realistic fills come out close to the strict "trade prints through my price" rule and 0.5 to 3 points below the optimistic "price touched" rule. The tracker now uses the strict rule.
- **Limit vs ask.** A limit 3¢ under the ask beat paying the ask for every bucket type in all three datasets (paying the ask: −5% to −7%; limit: 0% to −3% across all buckets).
- **Price.** Placing at min(ask − 3¢, best bid) beat plain ask − 3¢ in 12 of 12 cells, by 0.2 to 0.4¢ per contract. Adopted.
- **Timing.** Placing at 11 AM on the event day was the worst in every dataset. Noon the day before was best pooled (+9.0%, n = 648) but is only a lead.
- **Cancelling at noon** looked large on one dataset and vanished on the other two, so I read it as luck.
- **Chasing at the ask** after a limit fails to fill did no better than skipping the trade.

## Not adopted

Noon cancel, chasing, and moving placement to noon the day before.
