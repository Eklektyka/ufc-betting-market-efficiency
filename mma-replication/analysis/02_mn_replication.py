#!/usr/bin/env python3
"""
Table 2: Miller & Nichols (2026) replication — travel, age, women's favorites.
All resolve to efficient on 2007-2025 with temporal validation.
Outputs: figures/table2_mn_replication.csv
"""
import sys, warnings, functools
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)

OUT_DIR = '../figures'

# Results from prior analysis scripts (exotic_models.py, travel_replication.py, intl_home.py)
# These are the held-out test (2024-25) Brier deltas vs market
rows = [
    {'Inefficiency': 'Age/youth (BT cliff model)', 'Source': 'Miller & Nichols (2026)',
     'In-sample direction': 'Correct (cliff hurts)', 'OOS Brier vs market': '+0.046',
     'OOS significant': 'No', 'Verdict': 'Efficient'},
    {'Inefficiency': 'Career experience', 'Source': 'Miller & Nichols (2026)',
     'In-sample direction': 'Veteran penalty', 'OOS Brier vs market': '+0.043',
     'OOS significant': 'No', 'Verdict': 'Efficient'},
    {'Inefficiency': "Women's favorites", 'Source': 'Miller & Nichols (2026)',
     'In-sample direction': '2024 spike (p=0.052)', 'OOS Brier vs market': 'n/a (pooled null)',
     'OOS significant': 'No', 'Verdict': 'Efficient'},
    {'Inefficiency': 'Travel distance (log)', 'Source': 'Miller & Nichols (2026)',
     'In-sample direction': 'Correct (travel hurts)', 'OOS Brier vs market': '+0.0002',
     'OOS significant': 'No', 'Verdict': 'Efficient'},
    {'Inefficiency': 'Timezone differential', 'Source': 'Miller & Nichols (2026)',
     'In-sample direction': 'Correct (jet lag hurts)', 'OOS Brier vs market': '+0.0003',
     'OOS significant': 'No', 'Verdict': 'Efficient'},
    {'Inefficiency': 'Home country advantage', 'Source': 'This paper',
     'In-sample direction': '+3.8pp excess', 'OOS Brier vs market': '+0.0000',
     'OOS significant': 'No (CI incl. 0)', 'Verdict': 'Efficient (underpowered)'},
    {'Inefficiency': 'Favorite-longshot bias', 'Source': 'Miller & Nichols (2026)',
     'In-sample direction': 'Not found', 'OOS Brier vs market': 'n/a',
     'OOS significant': 'No', 'Verdict': 'Efficient'},
]

table = pd.DataFrame(rows)
table.to_csv(f'{OUT_DIR}/table2_mn_replication.csv', index=False)
print(table.to_string(index=False))
print(f"\nSaved to {OUT_DIR}/table2_mn_replication.csv")
