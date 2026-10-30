# Mining Hypotheses

Mining set: 7273 rows, 2007-07-07 to 2022-12-17
Subgroups tested: 2111
BH correction at q=0.10 across 2111 tests

| # | Rule | Dir | Effect | N | CI excl 0 | BH | Plausibility |
|---|---|---|---|---|---|---|---|
| 1 | sapm_pre_r <= -1 AND career_ko_losses > 2 | OVERPERFORM | +0.296 | 36 | yes | no | low |
| 2 | career_ko_losses > 2 AND sapm_pre_r <= -1 | OVERPERFORM | +0.296 | 36 | yes | no | low |
| 3 | layoff_days > 730 AND diff_career_wr <= -0.2 | OVERPERFORM | +0.254 | 31 | yes | no | low |
| 4 | sapm_pre_r <= -2 AND career_ko_losses > 0 | OVERPERFORM | +0.245 | 38 | yes | no | low |
| 5 | layoff_days > 730 AND diff_career_wr <= -0.1 | OVERPERFORM | +0.239 | 44 | yes | no | low |
| 6 | layoff_days > 730 AND line_move <= -0.02 | OVERPERFORM | +0.213 | 58 | yes | no | low-medium |
| 7 | layoff_days > 730 AND line_move <= -0.05 | OVERPERFORM | +0.187 | 48 | yes | no | low |
| 8 | layoff_days > 730 AND line_move <= 0.02 | OVERPERFORM | +0.185 | 74 | yes | no | low-medium |
| 9 | layoff_days > 730 AND diff_career_ctrl_per_fight > 60 | OVERPERFORM | +0.184 | 35 | yes | no | low |
| 10 | streak > 5 AND diff_career_ctrl_per_fight > 60 | OVERPERFORM | +0.184 | 60 | yes | no | low-medium |
| 11 | layoff_days > 730 AND diff_career_wr <= 0 | OVERPERFORM | +0.183 | 59 | yes | no | low-medium |
| 12 | layoff_days <= 60 AND diff_career_td_per_fight <= -1 | UNDERPERFORM | -0.181 | 40 | yes | no | low |
| 13 | layoff_days > 730 AND line_move <= 0 | OVERPERFORM | +0.181 | 68 | yes | no | low-medium |
| 14 | layoff_days > 730 AND streak <= -2 | OVERPERFORM | +0.179 | 35 | yes | no | low |
| 15 | streak > 5 AND diff_career_ctrl_per_fight > 30 | OVERPERFORM | +0.174 | 69 | yes | no | low-medium |
| 16 | layoff_days > 730 AND line_move <= 0.05 | OVERPERFORM | +0.174 | 79 | yes | no | low-medium |
| 17 | layoff_days > 730 AND close_spread <= 20 | OVERPERFORM | +0.173 | 63 | yes | no | low-medium |
| 18 | layoff_days > 730 AND implied_prob <= 0.3 | OVERPERFORM | +0.172 | 30 | yes | no | low |
| 19 | implied_prob <= 0.3 AND layoff_days > 730 | OVERPERFORM | +0.172 | 30 | yes | no | low |
| 20 | streak > 5 AND close_spread <= 5 | OVERPERFORM | +0.169 | 32 | yes | no | low |

Note: no test was run on the holdout set.
