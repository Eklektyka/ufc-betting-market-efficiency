"""
robustness_checks.py
====================
CHECK 1 — Two-way cluster SE (fighter_id AND fight_id) via Cameron-Gelbach-
          Miller (2011). Each fight appears as two rows; calibration_gap sums
          to exactly zero within each fight, so single-cluster SE by fighter
          may underestimate variance. CGM addresses the within-fight dependency.

CHECK 3 — Rolling window sapm_opp [NOT IMPLEMENTED]
          Requires per-fight strike absorption values (not career averages).
          fight_totals.csv has concatenated stats for both fighters without a
          reliable separator — not parseable. Needs a clean re-scrape of
          per-fight UFCStats data to implement.

CHECK 5 — Drop Overturned fights.
          31 rows have method="Overturned" and won=0. These may be No Contests
          coded as losses rather than genuine fight results. Drop and re-run.

Reports coefficient, SE, and p-value for sapm_r_opp and age_at_fight under
each check, compared to the baseline single-cluster result.
"""

import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import scipy.stats as stats
import statsmodels.api as sm
import patsy
from pathlib import Path

SEED = 42
np.random.seed(SEED)

BASE    = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis')
OUT_DIR = BASE / 'preliminary results'

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

FOCUS_VARS = ['sapm_r_opp', 'age_at_fight']

# ── 0. Load panel ──────────────────────────────────────────────────────────
print('Loading panel...')
panel = pd.read_csv(OUT_DIR / 'style_panel.csv', parse_dates=['date'])
panel['year']          = panel['date'].dt.year
panel['layoff_days_c'] = panel['layoff_days'].clip(0, 365 * 2)

opp_join = (panel[['fight_id','fighter_id'] + STYLE_VARS]
            .rename(columns={'fighter_id':'opponent_id',
                             **{v: v+'_opp' for v in STYLE_VARS}}))
panel = panel.merge(opp_join, on=['fight_id','opponent_id'], how='left')

req = (ALL_ATOMIC
       + ['calibration_gap','glicko_z','glicko','age_at_fight','layoff_days_c',
          'won','division','year','fighter_id','fight_id','method'])
panel_est = panel[panel[req].notna().all(axis=1)].copy().reset_index(drop=True)

# glicko_z fix: training moments
train = panel_est[panel_est['year'] <= 2019]
_mu, _sd = train['glicko'].mean(), train['glicko'].std()
panel_est['glicko_z'] = (panel_est['glicko'] - _mu) / _sd

print(f'Base panel: N={len(panel_est):,}')

# ── Helpers ────────────────────────────────────────────────────────────────
def stars(p):
    if p < 0.001: return '***'
    if p < 0.010: return '**'
    if p < 0.050: return '*'
    if p < 0.100: return '.'
    return ''

def build_and_fit(data, formula, cluster_col):
    """Fit OLS with single-cluster SE, return model + design matrices."""
    dummy = data.iloc[[0]].assign(division='other', calibration_gap=0.0)
    aug   = pd.concat([data, dummy], ignore_index=True)
    dpos  = len(aug) - 1
    lhs, rhs = patsy.dmatrices(formula, data=aug, return_type='dataframe')
    mask = lhs.index != dpos
    lhs, rhs = lhs[mask], rhs[mask]
    groups = aug.loc[lhs.index, cluster_col].values
    mod = sm.OLS(lhs.iloc[:,0], rhs).fit(
        cov_type='cluster', cov_kwds={'groups': groups})
    return mod, lhs, rhs, groups, aug, mask

def cgm_se(X, e, g1, g2, n, k):
    """
    Cameron-Gelbach-Miller two-way cluster SE.
    V_CGM = (X'X)^{-1} [B_g1 + B_g2 - B_HC0] (X'X)^{-1}
    with finite-sample corrections.
    """
    bread = np.linalg.pinv(X.T @ X)

    def sandwich(groups, correction=True):
        uniq = np.unique(groups)
        G    = len(uniq)
        meat = np.zeros((k, k))
        for g in uniq:
            idx   = groups == g
            score = X[idx].T @ e[idx]
            meat += np.outer(score, score)
        if correction:
            meat *= G / (G - 1) * (n - 1) / (n - k)
        return meat

    B1   = sandwich(g1)
    B2   = sandwich(g2)
    # Intersection: each obs is its own cluster → HC0
    B12  = (X * e[:, None]).T @ (X * e[:, None])
    B12 *= (n - 1) / (n - k)

    vcov = bread @ (B1 + B2 - B12) @ bread
    return vcov

def print_results(label, params, se, pvals, col_names, focus=FOCUS_VARS):
    print(f'\n  {label}')
    print(f'  {"Variable":<20} {"Coef":>10} {"SE":>10} {"p":>8} {"Sig":>5}')
    print('  ' + '-'*57)
    for v in focus:
        if v in col_names:
            i = col_names.index(v)
            print(f'  {v:<20} {params[i]:>+10.5f} {se[i]:>10.5f} '
                  f'{pvals[i]:>8.4f} {stars(pvals[i]):>5}')

# ── BASELINE (single-cluster by fighter_id) ───────────────────────────────
print('\n' + '='*65)
print('BASELINE — single cluster by fighter_id')
print('='*65)

mod_base, lhs_b, rhs_b, grp_b, aug_b, mask_b = build_and_fit(
    panel_est, FORMULA, 'fighter_id')

col_names = list(rhs_b.columns)
params_b  = np.array(mod_base.params)
se_b      = np.array(mod_base.bse)
pvals_b   = np.array(mod_base.pvalues)
print_results('Baseline', params_b, se_b, pvals_b, col_names)

# ── CHECK 1 — Two-way CGM cluster SE ──────────────────────────────────────
print('\n' + '='*65)
print('CHECK 1 — Two-way cluster SE: fighter_id AND fight_id (CGM 2011)')
print('='*65)
print('Within-fight: calibration_gap sums to ~0 per fight.')
print('Single-cluster SE may understate variance by ~sqrt(2).')

X  = rhs_b.values
e  = np.array(mod_base.resid)
n, k = X.shape
g1 = aug_b.loc[lhs_b.index, 'fighter_id'].values
g2 = aug_b.loc[lhs_b.index, 'fight_id'].values

vcov_cgm = cgm_se(X, e, g1, g2, n, k)
se_cgm   = np.sqrt(np.abs(np.diag(vcov_cgm)))
t_cgm    = params_b / se_cgm

# df = min(G1, G2) - 1 (conservative)
G1 = len(np.unique(g1))
G2 = len(np.unique(g2))
df = min(G1, G2) - 1
p_cgm = 2 * stats.t.sf(np.abs(t_cgm), df=df)

print_results('Two-way CGM', params_b, se_cgm, p_cgm, col_names)

# SE inflation factors
print('\n  SE inflation (CGM / baseline):')
for v in FOCUS_VARS:
    if v in col_names:
        i = col_names.index(v)
        infl = se_cgm[i] / se_b[i]
        print(f'  {v:<20}  {infl:.3f}x')

# ── CHECK 3 — Rolling window [NOT IMPLEMENTED] ────────────────────────────
print('\n' + '='*65)
print('CHECK 3 — Rolling window sapm_opp [NOT IMPLEMENTED]')
print('='*65)
print('Requires per-fight strike absorption (not career averages).')
print('fight_totals.csv has both fighters stats concatenated without')
print('a reliable separator — cannot be parsed cleanly.')
print('Needs a clean re-scrape of per-fight UFCStats data.')

# ── CHECK 5 — Drop Overturned fights ──────────────────────────────────────
print('\n' + '='*65)
print('CHECK 5 — Drop Overturned fights (N=31, coded won=0)')
print('='*65)

panel_no_ov = panel_est[~panel_est['method'].str.contains(
    'Overturned', case=False, na=False)].copy().reset_index(drop=True)

print(f'Rows dropped: {len(panel_est) - len(panel_no_ov)}')
print(f'Remaining N: {len(panel_no_ov):,}')

mod_nov, lhs_nov, rhs_nov, grp_nov, _, _ = build_and_fit(
    panel_no_ov, FORMULA, 'fighter_id')

params_nov = np.array(mod_nov.params)
se_nov     = np.array(mod_nov.bse)
pvals_nov  = np.array(mod_nov.pvalues)
col_names_nov = list(rhs_nov.columns)

print_results('No Overturned', params_nov, se_nov, pvals_nov, col_names_nov)

# ── SUMMARY ───────────────────────────────────────────────────────────────
print('\n' + '='*65)
print('SUMMARY TABLE')
print('='*65)
print(f'\n{"":30} {"Baseline":>12} {"Two-way CGM":>12} {"No Overturned":>14}')
print('-'*72)

for v in FOCUS_VARS:
    if v in col_names and v in col_names_nov:
        i_b   = col_names.index(v)
        i_nov = col_names_nov.index(v)
        i_cgm = col_names.index(v)
        b_str   = f'{params_b[i_b]:+.5f}{stars(pvals_b[i_b])}'
        cgm_str = f'{params_b[i_cgm]:+.5f}{stars(p_cgm[i_cgm])}'
        nov_str = f'{params_nov[i_nov]:+.5f}{stars(pvals_nov[i_nov])}'
        print(f'{v:<30} {b_str:>12} {cgm_str:>12} {nov_str:>14}')
        se_b_str   = f'({se_b[i_b]:.5f})'
        se_cgm_str = f'({se_cgm[i_cgm]:.5f})'
        se_nov_str = f'({se_nov[i_nov]:.5f})'
        print(f'{"SE":<30} {se_b_str:>12} {se_cgm_str:>12} {se_nov_str:>14}')
    print()

print('Done.')
