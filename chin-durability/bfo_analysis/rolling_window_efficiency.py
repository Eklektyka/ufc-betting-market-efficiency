"""
rolling_window_efficiency.py
============================
Tests whether the sapm_r_opp mispricing attenuates over time — i.e., whether
the market learns. Runs the main OLS regression on successive 4-year rolling
windows (e.g., 2008-2011, 2009-2012, ..., 2022-2025) and plots the
sapm_r_opp coefficient with 95% CI for each window center year.

If the market adjusts, the coefficient should decay toward zero in later windows.
If it persists, that strengthens the anomaly claim.
"""

import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import statsmodels.api as sm
import patsy
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

BASE    = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis')
OUT_DIR = BASE / 'preliminary results'
FIG_DIR = BASE / 'ufc_paper_visualizations'
FIG_DIR.mkdir(exist_ok=True)

STYLE_VARS = [
    'slpm_r','str_acc_r','dist_share_r','clinch_share_r','ground_share_r',
    'head_share_r','body_share_r','leg_share_r','kd_rate_r','td_per15_r',
    'td_acc_r','td_def_r','sub_per15_r','ctrl_share_r','sapm_r',
    'avg_fight_min_r','finish_rate_r',
]
ALL_ATOMIC = STYLE_VARS + [v + '_opp' for v in STYLE_VARS]

FORMULA = ('calibration_gap ~ '
           + ' + '.join(ALL_ATOMIC)
           + ' + glicko_z + age_at_fight + layoff_days_c'
           + ' + C(division) + C(year)')

WINDOW   = 4   # years per window
FOCUS    = ['sapm_r_opp', 'age_at_fight']

# ── Load panel ─────────────────────────────────────────────────────────────
print('Loading panel...')
panel = pd.read_csv(OUT_DIR / 'style_panel.csv', parse_dates=['date'])
panel['year']          = panel['date'].dt.year
panel['layoff_days_c'] = panel['layoff_days'].clip(0, 365 * 2)

opp_join = (panel[['fight_id','fighter_id'] + STYLE_VARS]
            .rename(columns={'fighter_id':'opponent_id',
                             **{v: v+'_opp' for v in STYLE_VARS}}))
panel = panel.merge(opp_join, on=['fight_id','opponent_id'], how='left')

req = (ALL_ATOMIC
       + ['calibration_gap','glicko_z','glicko','age_at_fight',
          'layoff_days_c','division','year','fighter_id','fight_id'])
panel_full = panel[panel[req].notna().all(axis=1)].copy().reset_index(drop=True)

# Fix glicko_z: standardise on pre-2020 training moments
train_global = panel_full[panel_full['year'] <= 2019]
_mu, _sd = train_global['glicko'].mean(), train_global['glicko'].std()
panel_full['glicko_z'] = (panel_full['glicko'] - _mu) / _sd

print(f'Full panel N={len(panel_full):,}')

# ── Rolling window loop ────────────────────────────────────────────────────
years      = sorted(panel_full['year'].unique())
min_yr     = min(years)
max_yr     = max(years)

results = []

for start in range(min_yr, max_yr - WINDOW + 2):
    end    = start + WINDOW - 1
    center = (start + end) / 2
    subset = panel_full[(panel_full['year'] >= start) &
                        (panel_full['year'] <= end)].copy().reset_index(drop=True)

    if len(subset) < 200:
        print(f'  {start}-{end}: N={len(subset)} — skipped (too small)')
        continue

    # Dummy row for unseen division level
    dummy = subset.iloc[[0]].assign(division='other', calibration_gap=0.0)
    aug   = pd.concat([subset, dummy], ignore_index=True)
    dpos  = len(aug) - 1

    try:
        lhs, rhs = patsy.dmatrices(FORMULA, data=aug, return_type='dataframe')
        mask     = lhs.index != dpos
        lhs, rhs = lhs[mask], rhs[mask]
        groups   = aug.loc[lhs.index, 'fighter_id'].values

        mod = sm.OLS(lhs.iloc[:,0], rhs).fit(
            cov_type='cluster', cov_kwds={'groups': groups})

        row = {'start': start, 'end': end, 'center': center, 'n': len(subset)}
        for v in FOCUS:
            if v in mod.params.index:
                ci = mod.conf_int().loc[v]
                row[f'{v}_coef'] = mod.params[v]
                row[f'{v}_se']   = mod.bse[v]
                row[f'{v}_p']    = mod.pvalues[v]
                row[f'{v}_lo']   = ci[0]
                row[f'{v}_hi']   = ci[1]
        results.append(row)
        print(f'  {start}-{end}: N={len(subset):,}  '
              f'sapm_r_opp={mod.params.get("sapm_r_opp", np.nan):+.5f}  '
              f'p={mod.pvalues.get("sapm_r_opp", np.nan):.3f}')
    except Exception as ex:
        print(f'  {start}-{end}: FAILED — {ex}')

df = pd.DataFrame(results)
print(f'\nWindows computed: {len(df)}')

# ── Print table ────────────────────────────────────────────────────────────
print('\n' + '='*70)
print(f'{"Window":<12} {"N":>5}  {"sapm_r_opp coef":>16}  {"95% CI":>22}  {"p":>7}')
print('-'*70)
for _, r in df.iterrows():
    sig = ('***' if r['sapm_r_opp_p'] < 0.001 else
           '**'  if r['sapm_r_opp_p'] < 0.010 else
           '*'   if r['sapm_r_opp_p'] < 0.050 else
           '.'   if r['sapm_r_opp_p'] < 0.100 else '')
    ci_str = f'[{r["sapm_r_opp_lo"]:+.5f}, {r["sapm_r_opp_hi"]:+.5f}]'
    print(f'{int(r["start"])}-{int(r["end"]):<7} {int(r["n"]):>5}  '
          f'{r["sapm_r_opp_coef"]:>+16.5f}  {ci_str:>22}  '
          f'{r["sapm_r_opp_p"]:>6.3f} {sig}')

# ── Plot ───────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
fig.suptitle('Rolling 4-Year Window: Market Efficiency in UFC Betting\n'
             '(OLS coefficient ± 95% CI, cluster SE by fighter)', fontsize=13)

for ax, var, label, color in zip(
        axes,
        FOCUS,
        ['Opponent chin vulnerability (sapm_r_opp)',
         'Fighter age (age_at_fight)'],
        ['#2166ac', '#d6604d']):

    coef_col = f'{var}_coef'
    lo_col   = f'{var}_lo'
    hi_col   = f'{var}_hi'
    p_col    = f'{var}_p'

    if coef_col not in df.columns:
        continue

    xs  = df['center'].values
    ys  = df[coef_col].values
    los = df[lo_col].values
    his = df[hi_col].values
    ps  = df[p_col].values

    ax.axhline(0, color='black', linewidth=0.8, linestyle='--', alpha=0.5)
    ax.fill_between(xs, los, his, alpha=0.18, color=color)
    ax.plot(xs, ys, color=color, linewidth=2, marker='o', markersize=5)

    # Shade significant windows
    for i, (x, y, lo, hi, p) in enumerate(zip(xs, ys, los, his, ps)):
        marker = '*' if p < 0.05 else ''
        if marker:
            ax.annotate('*', (x, hi), ha='center', va='bottom',
                        fontsize=10, color=color)

    ax.set_ylabel('Coefficient', fontsize=10)
    ax.set_title(label, fontsize=11, loc='left')
    ax.grid(axis='y', alpha=0.3)

    # Add N as secondary annotation on first panel
    if var == 'sapm_r_opp':
        for _, row in df.iterrows():
            ax.annotate(f'N={int(row["n"])}',
                        (row['center'], los[df['center'] == row['center']].item()),
                        textcoords='offset points', xytext=(0, -14),
                        ha='center', fontsize=6.5, color='gray')

axes[-1].set_xlabel('Window center year', fontsize=10)
xticks = df['center'].values
axes[-1].set_xticks(xticks)
axes[-1].set_xticklabels([f'{int(r.start)}-{int(r.end)}'
                           for _, r in df.iterrows()], rotation=45, ha='right')

plt.tight_layout()
out_path = FIG_DIR / 'rolling_window_efficiency.png'
plt.savefig(out_path, dpi=150, bbox_inches='tight')
print(f'\nFigure saved: {out_path}')
plt.show()
print('Done.')
