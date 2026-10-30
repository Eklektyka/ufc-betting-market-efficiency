# Simulation Summary

Fights: 549 (rank=349, test=200) | Users: 1547 | Draws: 500 | Seed: 67
Skill: delta_u ~ N(0,sigma_s), pick winner w.p. delta_u/(1-null_acc)
Power: share of draws above 95th percentile of null (sigma_s=0) distribution

| Statistic | Null SD | Threshold | null mean | null power | 0.01 mean | 0.01 power | 0.02 mean | 0.02 power | 0.03 mean | 0.03 power |
|---|---|---|---|---|---|---|---|---|---|---|
| frac_roi_pos | 0.1860 | 0.6949 | 0.3433 | 4.8% | 0.4360 | 10.8% | 0.5360 | 19.2% | 0.5552 | 18.2% |
| mean_clv_edge | 0.0140 | 0.0211 | -0.0001 | 5.0% | 0.0042 | 10.0% | 0.0105 | 19.4% | 0.0134 | 30.6% |
| rho_rank_test_clv | 0.0636 | 0.1036 | 0.0014 | 5.0% | 0.0939 | 42.8% | 0.2731 | 99.6% | 0.4502 | 100.0% |
| top_decile_test_clv | 0.0211 | 0.0328 | -0.0014 | 5.0% | 0.0100 | 11.6% | 0.0302 | 45.2% | 0.0503 | 80.8% |
| top_minus_bot_clv | 0.0054 | 0.0079 | 0.0001 | 5.0% | 0.0081 | 51.0% | 0.0265 | 100.0% | 0.0481 | 100.0% |
| divergence_consensus_roi | 0.0853 | 0.1158 | -0.0180 | 5.0% | 0.0276 | 12.4% | 0.1081 | 41.0% | 0.2122 | 83.4% |
| always_fav_test_roi | 0.0506 | 0.0657 | -0.0188 | 5.0% | -0.0147 | 3.8% | -0.0101 | 5.6% | -0.0142 | 5.0% |
