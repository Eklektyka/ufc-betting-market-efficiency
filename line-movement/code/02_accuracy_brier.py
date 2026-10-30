"""
Phase 02 — Calibration regressions and Brier score comparison
==============================================================
Implements: Phase 2 of the line-efficiency analysis.
Reads:      data/processed/paths_panel_v1.csv
Writes:     nothing (printed output only; numbers transcribed to results/phase02_brier.txt)
Result:     Brier(close) - Brier(open) = -0.007308; 95% CI [-0.008945, -0.005583].
            Close IS statistically more accurate than open (CI entirely below 0).
"""

import pandas as pd
import numpy as np
from scipy import stats

rng   = np.random.default_rng(42)
panel = pd.read_csv("../data/processed/paths_panel_v1.csv")
N     = len(panel)

win     = panel['win'].values
p_open  = panel['p_open'].values
p_close = panel['p_close_hi'].values
g_open  = panel['g_open'].values
g_close = panel['g_close'].values

# (a) Calibration regressions
def ols_report(y, x, label):
    slope, intercept, r, p_val, se = stats.linregress(x, y)
    print(f"  {label}  intercept={intercept:+.5f}  slope={slope:+.5f}  SE={se:.5f}  p={p_val:.4f}")

print(f"(a) Calibration regressions (N={N})")
ols_report(g_open,  p_open,  "g_open  ~ p_open      ")
ols_report(g_close, p_close, "g_close ~ p_close_hi  ")

# (b) MAE and Brier score
mae_open  = np.mean(np.abs(g_open))
mae_close = np.mean(np.abs(g_close))
bs_open   = np.mean(g_open  ** 2)
bs_close  = np.mean(g_close ** 2)
print(f"\n(b) Accuracy metrics (N={N})")
print(f"  MAE:   open={mae_open:.6f}  close={mae_close:.6f}  diff={mae_close-mae_open:+.6f}")
print(f"  Brier: open={bs_open:.6f}  close={bs_close:.6f}  diff={bs_close-bs_open:+.6f}")

# (c) Bootstrap CI on Brier difference
B      = 5000
bs_obs = bs_close - bs_open
diffs  = np.array([np.mean(g_close[rng.integers(0,N,N)]**2) - np.mean(g_open[rng.integers(0,N,N)]**2)
                   for _ in range(B)])
ci_lo, ci_hi = np.percentile(diffs, [2.5, 97.5])
print(f"\n(c) Bootstrap 95% CI on Brier diff (B={B}, seed=42)")
print(f"  Observed={bs_obs:+.6f}  CI=[{ci_lo:+.6f}, {ci_hi:+.6f}]")
