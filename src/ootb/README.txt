Out-of-the-box edge tests (2026-11-24). Research only; no paper strategy changed.
  build_grid.py / momentum.py / momentum_test.py -> momentum_results.txt : under-reaction & neighbour lead-lag (null)
  bucket_sum_results.txt : buckets summing over/under 100c (arb only 5 of 12,384 snapshots after fees)
  early_carry.py -> early_carry_results.txt, early_carry_min15.txt : highs decided before 2 AM local (midnight carry-over)
  fetch_low_tapes.py -> low_trades.csv ; low_lock.py, low_lock_tape.py -> low_lock_tape_results.txt, low_lock_events.csv : lock harvesting on KXLOWT daily lows
