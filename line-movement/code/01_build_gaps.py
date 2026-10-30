"""
Phase 01 — Build paths panel (p_open, g_open, g_close, move)
=============================================================
Implements: Phase 1 of the line-efficiency analysis.
Reads:      data/processed/analysis_panel_cc.csv
            (ufc_fights_clean.csv from merged/ for p_open_a, p_open_b, odds_imputed)
Writes:     data/processed/paths_panel_v1.csv  (N=8,112 rows, 20 cols)
Result:     N=8,112 after excluding 1,155 rows with imputed opening odds.
            mean(g_open)=0.00000, mean(g_close)=0.00000 (lines unbiased on average).
            Tagged paths-v1 in merged/ git repo.
"""

import pandas as pd
import numpy as np

cc    = pd.read_csv("../data/processed/analysis_panel_cc.csv")
clean = pd.read_csv("../../merged/ufc_fights_clean.csv",
                    usecols=['fight_url','fighter_a','fighter_b','p_open_a','p_open_b','odds_imputed'])

merged = cc.merge(clean, on='fight_url', how='left')
is_a   = merged['fighter'] == merged['fighter_a']
merged['p_open']       = np.where(is_a, merged['p_open_a'], merged['p_open_b'])
merged['open_imputed'] = merged['odds_imputed']
merged.drop(columns=['fighter_a','fighter_b','p_open_a','p_open_b','odds_imputed'], inplace=True)

merged.rename(columns={'g': 'g_close'}, inplace=True)
merged['g_open'] = merged['win']        - merged['p_open']
merged['move']   = merged['p_close_hi'] - merged['p_open']

panel = merged[(merged['p_open'].notna()) & (~merged['open_imputed'])].copy()
panel.to_csv("../data/processed/paths_panel_v1.csv", index=False)
print(f"Saved paths_panel_v1.csv: {len(panel)} rows")
print(panel[['p_open','p_close_hi','g_open','g_close','move']].agg(['mean','std']).T.round(5))
