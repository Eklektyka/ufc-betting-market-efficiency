"""
Phase 05 — Out-of-sample robustness: pre-2020 vs 2020+ split
=============================================================
Implements: Phase 5 of the line-efficiency analysis.
Reads:      data/processed/paths_panel_v1.csv
Writes:     nothing (printed output only; numbers transcribed to results/phase05_oos_split.txt)
Result:     Mech A (g_open~move) and Mech B (win~p_open+move): REAL in both windows.
            Mech C (g_close~move): REJECT (sign flip, insignificant in both windows).
"""

import pandas as pd
import statsmodels.formula.api as smf

panel = pd.read_csv("../data/processed/paths_panel_v1.csv")
pre   = panel[panel['year'] < 2020]
post  = panel[panel['year'] >= 2020]

def run(df, formula, label):
    m    = smf.ols(formula, data=df).fit(
               cov_type='cluster', cov_kwds={'groups': df['fighter_id']})
    var  = 'move'
    coef = m.params[var]; se = m.bse[var]; p = m.pvalues[var]; ci = m.conf_int().loc[var]
    print(f"  {label:<12} N={len(df):>5}  coef={coef:+.5f}  SE={se:.5f}  p={p:.4f}  CI=[{ci[0]:+.5f}, {ci[1]:+.5f}]")

for name, formula in [("Mech A: g_open ~ move",       "g_open ~ move"),
                       ("Mech B: win ~ p_open + move", "win ~ p_open + move"),
                       ("Mech C: g_close ~ move",      "g_close ~ move")]:
    print(f"\n{name} (clustered by fighter_id)")
    run(pre,  formula, "pre-2020")
    run(post, formula, "2020+")
