Speed edge research (2026-11-23). Research only: no live paper strategy was changed.
  fetch_onemin_hist.py  IEM 1-minute temps, 7 stations, Dec 2024 - Aug 2026 -> onemin_hist/
  build_days.py         -> days.npz (one 1440-minute array per station-day, local standard time)
  gap_check.py          settlement rule search: official high = round(max 5-minute running mean) (97%, 98.4% on complete days)
  margin_check.py       rule reliability by rounding margin / missing data
  lock_events.py        price behaviour around the minute a bucket is decided (Sep 22 - Nov 19 2026)
  capture.py            first capture simulation (test period)
  fetch_event_tapes.py  trades around 7,601 decided buckets, Dec 2024 - Sep 21 2026 -> event_tapes.csv
  capture2.py           parameterised capture test (base and qc rules)
Results: capture_test_period.txt, capture_heldout*.txt, capture_latency.txt, capture_capped.txt
