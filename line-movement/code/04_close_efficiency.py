"""
Phase 04 — Is the market's revision fully impounded at the close?
=================================================================
Implements: Phase 4 of the line-efficiency analysis.
Reads:      data/processed/paths_panel_v1.csv
Writes:     nothing (printed output only; numbers transcribed to results/phase04_close_efficiency.txt)
Result:     g_close ~ move: coef=+0.038, p=0.545 (clustered by fighter_id).
            Cannot reject H0=0. Movement is fully impounded into the closing line.
            Market is efficient with respect to its own revision.
"""

import pandas as pd
import statsmodels.formula.api as smf

panel = pd.read_csv("../data/processed/paths_panel_v1.csv")
N     = len(panel)

m    = smf.ols("g_close ~ move", data=panel).fit(
           cov_type='cluster', cov_kwds={'groups': panel['fighter_id']})
coef = m.params['move']; se = m.bse['move']; p = m.pvalues['move']; ci = m.conf_int().loc['move']

print(f"g_close ~ move (N={N}, clustered by fighter_id)")
print(f"  coef={coef:+.5f}  SE={se:.5f}  p={p:.4f}  CI=[{ci[0]:+.5f}, {ci[1]:+.5f}]")
