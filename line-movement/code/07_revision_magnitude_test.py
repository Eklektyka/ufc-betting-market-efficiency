"""
Phase 07 — Revision magnitude test: H0: coef(move) = 1
========================================================
Implements: Phase 7 of the line-efficiency analysis.
Reads:      data/processed/paths_panel_v1.csv
Writes:     nothing (printed output only; numbers transcribed to results/phase07_magnitude_test.txt)
Result:     Cannot reject H0=1 in any window (full, pre-2020, 2020+).
            Revision magnitude is efficient: market moves the right amount.
"""

import pandas as pd
import numpy as np
import statsmodels.formula.api as smf
from scipy import stats

panel = pd.read_csv("../data/processed/paths_panel_v1.csv")
pre   = panel[panel['year'] < 2020]
post  = panel[panel['year'] >= 2020]

def run(df, label):
    m    = smf.ols("g_open ~ move", data=df).fit(
               cov_type='cluster', cov_kwds={'groups': df['fighter_id']})
    coef = m.params['move']; se = m.bse['move']; ci = m.conf_int().loc['move']
    t1   = (coef - 1) / se
    p1   = 2 * stats.t.sf(abs(t1), df=m.df_resid)
    print(f"\ng_open ~ move, H0: coef=1  |  {label}  (N={len(df)}, clustered by fighter_id)")
    print(f"  coef={coef:+.5f}  SE={se:.5f}  t_vs_H0_1={t1:+.3f}  p_vs_H0_1={p1:.4f}  CI=[{ci[0]:+.5f}, {ci[1]:+.5f}]")

run(panel, "Full sample (2007-2026)")
run(pre,   "pre-2020")
run(post,  "2020+")
