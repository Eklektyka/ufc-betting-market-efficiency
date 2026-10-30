"""
Phase 06 — Forecast-encompassing test: win ~ p_open + p_close_hi
=================================================================
Implements: Phase 6 of the line-efficiency analysis.
Reads:      data/processed/paths_panel_v1.csv
Writes:     nothing (printed output only; numbers transcribed to results/phase06_forecast_encompassing.txt)
Result:     p_close_hi significant (p<0.0001) in all three samples; p_open collapses to
            near-zero and loses significance in all three. Closing line encompasses opening line.
"""

import pandas as pd
import statsmodels.formula.api as smf

panel = pd.read_csv("../data/processed/paths_panel_v1.csv")
pre   = panel[panel['year'] < 2020]
post  = panel[panel['year'] >= 2020]

def run(df, label):
    m = smf.ols("win ~ p_open + p_close_hi", data=df).fit(
            cov_type='cluster', cov_kwds={'groups': df['fighter_id']})
    print(f"\n{label}  (N={len(df)}, clustered by fighter_id)")
    for v in ['p_open', 'p_close_hi']:
        print(f"  {v:<14}  coef={m.params[v]:+.5f}  SE={m.bse[v]:.5f}  p={m.pvalues[v]:.4f}")

run(panel, "Full sample (2007-2026)")
run(pre,   "pre-2020")
run(post,  "2020+")
