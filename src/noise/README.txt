Multiple-testing / luck check on the live leads (2026-11-24). Research only; no paper strategy changed.
  leads.py  -> lead_rows.csv : per-bet rows (date, cost, pnl, price) for each lead, same rules as the original tests
  stats.py  -> noise_results.txt, noise_table.csv : trial tally, hurdles (Bonferroni/Holm/BH over ~624 trials,
               HLZ t>3, p<0.005), day-clustered t-stats, deflated Sharpe, price-matched random-bucket placebo
Run: python3 noise/leads.py && python3 noise/stats.py   (needs scipy)
