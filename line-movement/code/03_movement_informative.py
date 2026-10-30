"""
Phase 03 — Does line movement predict the opening-price error?
==============================================================
Implements: Phase 3 of the line-efficiency analysis.
Reads:      data/processed/paths_panel_v1.csv
Writes:     nothing (printed output only; numbers transcribed to results/phase03_movement_informative.txt)
Result:     g_open ~ move: coef=+1.039, p<0.0001 (clustered by fighter_id).
            win ~ p_open + move: move coef=+1.039, p<0.0001.
            Market revision is informative; adds predictive power over the opening line.
"""

import pandas as pd
import statsmodels.formula.api as smf

panel = pd.read_csv("../data/processed/paths_panel_v1.csv")
N     = len(panel)

# Regression 1: g_open ~ move
m1   = smf.ols("g_open ~ move", data=panel).fit(
           cov_type='cluster', cov_kwds={'groups': panel['fighter_id']})
coef = m1.params['move']; se = m1.bse['move']; p = m1.pvalues['move']; ci = m1.conf_int().loc['move']
print(f"g_open ~ move (N={N}, clustered by fighter_id)")
print(f"  coef={coef:+.5f}  SE={se:.5f}  p={p:.4f}  CI=[{ci[0]:+.5f}, {ci[1]:+.5f}]")

# Regression 2: win ~ p_open + move
m2   = smf.ols("win ~ p_open + move", data=panel).fit(
           cov_type='cluster', cov_kwds={'groups': panel['fighter_id']})
coef2 = m2.params['move']; se2 = m2.bse['move']; p2 = m2.pvalues['move']; ci2 = m2.conf_int().loc['move']
print(f"\nwin ~ p_open + move (N={N}, clustered by fighter_id)  [move coef only]")
print(f"  coef={coef2:+.5f}  SE={se2:.5f}  p={p2:.4f}  CI=[{ci2[0]:+.5f}, {ci2[1]:+.5f}]")
