"""
run_exploratory_rw41.py
=======================
Romano-Wolf FWER correction over 41 candidate predictors of calibration_gap.

Family (41 variables):
  - 34 ALL_ATOMIC style variables (17 fighter-side _r + 17 opponent-side _r)
  - 7 composite matchup features: td_edge, anti_td_edge, drag_down,
    pace_durability, ctrl_scramble, ground_exploit, ko_power_chin

Note: stance_mismatch excluded — binary variable, not comparable to the
continuous style variables in the same OLS sweep.

Controls (not in RW family): glicko_z, age_at_fight, layoff_days_c,
  C(division), C(year)

Method: Romano-Wolf (2005) stepdown, B=5,000 permutations.
  - Observed t-stats: cluster-robust SE by fighter_id
  - Permutation t-stats: OLS SE (standard practice for speed;
    (X'X)^{-1} precomputed once, reused across all permutations)
  - Permutation scheme: shuffle outcome y (calibration_gap)

Outcome: calibration_gap  (win_prob_actual - market_prob_shin, per fighter)
Sample:  complete cases, full panel 2007-2026-04-18
"""

import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import statsmodels.api as sm
import patsy
from pathlib import Path

SEED   = 42
N_PERM = 5_000
rng    = np.random.default_rng(SEED)

BASE    = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis')
OUT_DIR = BASE / 'preliminary results'

STYLE_VARS = [
    'slpm_r', 'str_acc_r', 'dist_share_r', 'clinch_share_r', 'ground_share_r',
    'head_share_r', 'body_share_r', 'leg_share_r', 'kd_rate_r', 'td_per15_r',
    'td_acc_r', 'td_def_r', 'sub_per15_r', 'ctrl_share_r', 'sapm_r',
    'avg_fight_min_r', 'finish_rate_r',
]
ALL_ATOMIC = STYLE_VARS + [v + '_opp' for v in STYLE_VARS]   # 34

COMPOSITE = [
    'td_edge', 'anti_td_edge', 'drag_down', 'pace_durability',
    'ctrl_scramble', 'ground_exploit', 'ko_power_chin',
]   # 7  (stance_mismatch excluded — binary)

CANDIDATES = ALL_ATOMIC + COMPOSITE   # 41
assert len(CANDIDATES) == 41, f'Expected 41 candidates, got {len(CANDIDATES)}'

CONTROLS = 'glicko_z + age_at_fight + layoff_days_c + C(division) + C(year)'

# ── 0. Load & build panel ──────────────────────────────────────────────────
print('Loading panel...')
panel = pd.read_csv(OUT_DIR / 'style_panel.csv', parse_dates=['date'])
panel['year']          = panel['date'].dt.year
panel['layoff_days_c'] = panel['layoff_days'].clip(0, 365 * 2)

opp_join = (panel[['fight_id', 'fighter_id'] + STYLE_VARS]
            .rename(columns={'fighter_id': 'opponent_id',
                             **{v: v + '_opp' for v in STYLE_VARS}}))
panel = panel.merge(opp_join, on=['fight_id', 'opponent_id'], how='left')

req = (CANDIDATES
       + ['calibration_gap', 'glicko_z', 'age_at_fight',
          'layoff_days_c', 'division', 'year', 'fighter_id'])
panel_est = panel[panel[req].notna().all(axis=1)].copy().reset_index(drop=True)

print(f'N={len(panel_est):,}  '
      f'({panel_est["date"].min().date()} – {panel_est["date"].max().date()})')
print(f'Family: {len(CANDIDATES)} variables  '
      f'({len(ALL_ATOMIC)} ALL_ATOMIC + {len(COMPOSITE)} composite)\n')

# ── 1. Build design matrix ─────────────────────────────────────────────────
dummy_row = panel_est.iloc[[0]].assign(division='other', calibration_gap=0.0)
full_aug  = pd.concat([panel_est, dummy_row], ignore_index=True)
dummy_pos = len(full_aug) - 1

formula = 'calibration_gap ~ ' + ' + '.join(CANDIDATES) + ' + ' + CONTROLS
lhs_aug, rhs_aug = patsy.dmatrices(formula, data=full_aug, return_type='dataframe')
real_mask = lhs_aug.index != dummy_pos
lhs    = lhs_aug[real_mask]
rhs    = rhs_aug[real_mask]
y      = lhs.iloc[:, 0].values
X      = rhs.values
n, k   = X.shape
groups = full_aug.loc[lhs.index, 'fighter_id'].values

cand_cols  = [c for c in CANDIDATES if c in rhs.columns]
cand_idx   = [rhs.columns.get_loc(c) for c in cand_cols]
K          = len(cand_cols)
print(f'Candidate columns found in design matrix: {K}')

# ── 2. Observed model — cluster SE ────────────────────────────────────────
print('Fitting observed model (cluster SE by fighter_id)...')
mod_obs = sm.OLS(y, X).fit(
    cov_type='cluster',
    cov_kwds={'groups': groups})

obs_t = np.abs(np.array(mod_obs.tvalues)[cand_idx])
print(f'Adj-R² = {mod_obs.rsquared_adj:.4f}\n')

# ── 3. Romano-Wolf stepdown ────────────────────────────────────────────────
# Precompute (X'X)^{-1} once for fast permutation OLS
XtX_inv = np.linalg.pinv(X.T @ X)   # k × k

print(f'Running Romano-Wolf stepdown ({N_PERM:,} permutations)...')
perm_t = np.empty((N_PERM, K))

for b in range(N_PERM):
    y_p      = rng.permutation(y)
    beta_p   = XtX_inv @ (X.T @ y_p)
    resid_p  = y_p - X @ beta_p
    sigma2_p = (resid_p @ resid_p) / (n - k)
    var_p    = sigma2_p * np.diag(XtX_inv)
    t_p      = np.abs(beta_p / np.sqrt(np.maximum(var_p, 1e-12)))
    perm_t[b] = t_p[cand_idx]
    if (b + 1) % 1000 == 0:
        print(f'  {b + 1}/{N_PERM}')

# Stepdown: sort by observed |t| descending
order         = np.argsort(-obs_t)
ordered_t     = obs_t[order]
ordered_names = [cand_cols[i] for i in order]
perm_ordered  = perm_t[:, order]   # shape (N_PERM, K)

rw_p = np.empty(K)
for step in range(K):
    max_t_step = perm_ordered[:, step:].max(axis=1)
    rw_p[step] = (max_t_step >= ordered_t[step]).mean()

# Enforce monotonicity
for step in range(1, K):
    rw_p[step] = max(rw_p[step], rw_p[step - 1])

# ── 4. Results ─────────────────────────────────────────────────────────────
def stars(p):
    if p < 0.001: return '***'
    if p < 0.010: return '**'
    if p < 0.050: return '*'
    if p < 0.100: return '.'
    return ''

results = []
for step in range(K):
    name    = ordered_names[step]
    naive_p = np.array(mod_obs.pvalues)[rhs.columns.get_loc(name)]
    results.append({
        'Variable': name,
        'Obs |t|':  ordered_t[step],
        'Naive p':  naive_p,
        'RW p':     rw_p[step],
        'Sig':      stars(rw_p[step]),
    })

df_res = pd.DataFrame(results)

print('\n' + '=' * 72)
print(f'Romano-Wolf stepdown — family of {K} variables (B={N_PERM:,})')
print('=' * 72)
print(f'{"Variable":<25} {"Obs |t|":>8} {"Naive p":>10} {"RW p":>10} {"Sig":>5}')
print('-' * 65)
for _, row in df_res.iterrows():
    print(f'{row["Variable"]:<25} {row["Obs |t|"]:>8.3f} '
          f'{row["Naive p"]:>10.4f} {row["RW p"]:>10.4f} {row["Sig"]:>5}')

survivors = df_res[df_res['RW p'] < 0.05]
print(f'\nSurvivors at RW p < 0.05: {len(survivors)} of {K}')
for _, row in survivors.iterrows():
    print(f'  {row["Variable"]:<25}  RW p={row["RW p"]:.4f}  {row["Sig"]}')

focal = df_res[df_res['Variable'] == 'sapm_r_opp']
if not focal.empty:
    r    = focal.iloc[0]
    rank = int(df_res[df_res['Variable'] == 'sapm_r_opp'].index[0]) + 1
    print(f'\nFocal variable: sapm_r_opp')
    print(f'  Rank in family : {rank} of {K}')
    print(f'  Obs |t|        : {r["Obs |t|"]:.3f}')
    print(f'  Naive p        : {r["Naive p"]:.4f}')
    print(f'  RW p           : {r["RW p"]:.4f}  {r["Sig"]}')

print('\nDone.')
