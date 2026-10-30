"""
emergent_efficiency.py
======================
Tests whether the UFC closing-line betting market became more efficient over
time (adaptive-markets / learning). Seven sections:

  1. Single-signal × time interaction (sapm_r_opp), plain + piecewise
  2. Family-level trend: 41 candidate × time interactions, sign test + pooled
  3. Power benchmark: observed vs. expected significant counts per window
  4. Placebo: permutation null for family-decay statistic
  5. Composition controls: fighter fixed effects on the #1 trend
  6. Opening-to-closing convergence series and trend
  7. Honest summary

Rolling windows appear ONLY in #3 (labelled). All inference is coefficient-
based with explicit SE and CI.
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

SEED   = 42
N_PERM = 500
rng    = np.random.default_rng(SEED)
np.random.seed(SEED)

BASE    = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis')
OUT_DIR = BASE / 'preliminary results'
WINDOW  = 4   # years per rolling window (for section 3 power benchmark only)

STYLE_VARS = [
    'slpm_r','str_acc_r','dist_share_r','clinch_share_r','ground_share_r',
    'head_share_r','body_share_r','leg_share_r','kd_rate_r','td_per15_r',
    'td_acc_r','td_def_r','sub_per15_r','ctrl_share_r','sapm_r',
    'avg_fight_min_r','finish_rate_r',
]
ALL_ATOMIC = STYLE_VARS + [v + '_opp' for v in STYLE_VARS]
COMPOSITE  = ['td_edge','anti_td_edge','drag_down','pace_durability',
              'ctrl_scramble','ground_exploit','ko_power_chin']
CANDIDATES = ALL_ATOMIC + COMPOSITE   # 41

def stars(p):
    if p < 0.001: return '***'
    if p < 0.010: return '**'
    if p < 0.050: return '*'
    if p < 0.100: return '.'
    return ''

# ── 0. Load & build panel ──────────────────────────────────────────────────
print('Loading panel...')
panel = pd.read_csv(OUT_DIR / 'style_panel.csv', parse_dates=['date'])
panel['year']          = panel['date'].dt.year
panel['layoff_days_c'] = panel['layoff_days'].clip(0, 365 * 2)

opp_join = (panel[['fight_id','fighter_id'] + STYLE_VARS]
            .rename(columns={'fighter_id':'opponent_id',
                             **{v: v+'_opp' for v in STYLE_VARS}}))
panel = panel.merge(opp_join, on=['fight_id','opponent_id'], how='left')

req = (CANDIDATES
       + ['calibration_gap','market_prob_shin_open','q_open','glicko_z','glicko',
          'age_at_fight','layoff_days_c','won','division','year',
          'fighter_id','fight_id'])
panel_est = panel[panel[req].notna().all(axis=1)].copy().reset_index(drop=True)

# Fix glicko_z on training moments
train = panel_est[panel_est['year'] <= 2019]
_mu, _sd = train['glicko'].mean(), train['glicko'].std()
panel_est['glicko_z'] = (panel_est['glicko'] - _mu) / _sd

# Time variable: year centred
year_mean = panel_est['year'].mean()
panel_est['year_c'] = panel_est['year'] - year_mean

print(f'N={len(panel_est):,}  year_mean={year_mean:.2f}  '
      f'({panel_est["date"].min().date()} – {panel_est["date"].max().date()})')

# ── CGM two-way cluster SE (fighter × fight) ───────────────────────────────
def cgm_se(X, e, g1, g2, n, k):
    bread = np.linalg.pinv(X.T @ X)
    def sandwich(groups):
        uniq = np.unique(groups)
        G = len(uniq)
        meat = np.zeros((k, k))
        for g in uniq:
            idx   = groups == g
            score = X[idx].T @ e[idx]
            meat += np.outer(score, score)
        return meat * G / (G - 1) * (n - 1) / (n - k)
    B1  = sandwich(g1)
    B2  = sandwich(g2)
    B12 = (X * e[:, None]).T @ (X * e[:, None]) * (n - 1) / (n - k)
    return bread @ (B1 + B2 - B12) @ bread

# ── Build base design (controls + year_c, no year dummies) ────────────────
# For sections 1 & 5: C(division) absorbed; year_c is the continuous trend.
# All 41 CANDIDATES included as controls in sections 1 & 5.
OTHER_CANDS = [c for c in CANDIDATES if c != 'sapm_r_opp']

BASE_FORMULA = ('calibration_gap ~ sapm_r_opp + '
                + ' + '.join(OTHER_CANDS)
                + ' + glicko_z + age_at_fight + layoff_days_c + C(division)')

print('\n' + '='*70)
print('SECTION 1 — Single-signal × time interaction: sapm_r_opp')
print('='*70)

# ── 1a. Linear interaction ─────────────────────────────────────────────────
panel_est['sapm_x_yc'] = panel_est['sapm_r_opp'] * panel_est['year_c']

FORMULA_1A = (BASE_FORMULA.replace(
    'sapm_r_opp + ', 'sapm_r_opp + year_c + sapm_x_yc + '))

dummy = panel_est.iloc[[0]].assign(division='other', calibration_gap=0.0)
aug   = pd.concat([panel_est, dummy], ignore_index=True)
dpos  = len(aug) - 1
lhs, rhs = patsy.dmatrices(FORMULA_1A, data=aug, return_type='dataframe')
mask = lhs.index != dpos
lhs, rhs = lhs[mask], rhs[mask]
X1   = rhs.values
e_ols = np.array(sm.OLS(lhs.iloc[:,0], rhs).fit().resid)
g1   = aug.loc[lhs.index, 'fighter_id'].values
g2   = aug.loc[lhs.index, 'fight_id'].values
n1, k1 = X1.shape

mod_1a = sm.OLS(lhs.iloc[:,0], rhs).fit(
    cov_type='cluster', cov_kwds={'groups': g1})

# CGM two-way SE
vcov_cgm = cgm_se(X1, e_ols, g1, g2, n1, k1)
se_cgm   = np.sqrt(np.abs(np.diag(vcov_cgm)))
col_names = list(rhs.columns)

for vname in ['sapm_r_opp', 'year_c', 'sapm_x_yc']:
    if vname in col_names:
        i = col_names.index(vname)
        c  = mod_1a.params[vname]
        se = se_cgm[i]
        t  = c / se
        G  = min(len(np.unique(g1)), len(np.unique(g2))) - 1
        p  = 2 * stats.t.sf(abs(t), df=G)
        ci = (c - 1.96*se, c + 1.96*se)
        print(f'  {vname:<20}  coef={c:+.6f}  SE={se:.6f}  '
              f'CI=[{ci[0]:+.6f},{ci[1]:+.6f}]  p={p:.4f}  {stars(p)}')

print(f'  N={n1:,}   (two-way CGM: fighter × fight)')

# ── 1b. Piecewise — knots 2016, 2018 ──────────────────────────────────────
print('\n1b. Piecewise spline (knots 2016, 2018):')
K1, K2 = 2016, 2018
panel_est['yc_k1']      = np.maximum(panel_est['year'] - K1, 0)
panel_est['yc_k2']      = np.maximum(panel_est['year'] - K2, 0)
panel_est['sapm_x_yc_k1'] = panel_est['sapm_r_opp'] * panel_est['yc_k1']
panel_est['sapm_x_yc_k2'] = panel_est['sapm_r_opp'] * panel_est['yc_k2']

FORMULA_1B = (BASE_FORMULA.replace(
    'sapm_r_opp + ',
    'sapm_r_opp + year_c + yc_k1 + yc_k2 '
    '+ sapm_x_yc + sapm_x_yc_k1 + sapm_x_yc_k2 + '))

aug2 = pd.concat([panel_est, dummy], ignore_index=True)
lhs2, rhs2 = patsy.dmatrices(FORMULA_1B, data=aug2, return_type='dataframe')
mask2 = lhs2.index != dpos
lhs2, rhs2 = lhs2[mask2], rhs2[mask2]
mod_1b = sm.OLS(lhs2.iloc[:,0], rhs2).fit(
    cov_type='cluster', cov_kwds={'groups': aug2.loc[lhs2.index,'fighter_id'].values})

col2 = list(rhs2.columns)
print(f'  {"Segment":<30}  {"Cumulative sapm slope":>22}')
print(f'  {"Pre-2016 (baseline)  ":<30}  {mod_1b.params.get("sapm_r_opp",np.nan):>+.6f}')
s16 = mod_1b.params.get('sapm_x_yc_k1', 0)
s18 = mod_1b.params.get('sapm_x_yc_k2', 0)
base = mod_1b.params.get('sapm_r_opp', 0)
print(f'  {"2016-2018 add-on     ":<30}  {s16:>+.6f}  p={mod_1b.pvalues.get("sapm_x_yc_k1",np.nan):.4f}')
print(f'  {"Post-2018 add-on     ":<30}  {s18:>+.6f}  p={mod_1b.pvalues.get("sapm_x_yc_k2",np.nan):.4f}')
print(f'  Implied slopes:  pre-2016={base:+.6f}  '
      f'2016-18={base+s16:+.6f}  post-2018={base+s16+s18:+.6f}')

print('\n' + '='*70)
print('SECTION 2 — Family-level trend: 41 signals × time')
print('='*70)
print('For each of 41 candidates: coef on signal_j × year_c in full model.')
print('Cluster SE by fighter_id (CGM showed <1% difference).\n')

# Build design matrix for family trend: all 41 + controls + year_c
# For each candidate j: add signal_j × year_c, fit, extract interaction coef.
# Use numpy OLS for speed; cluster SE via grouped sandwich.

CTRLS = ['glicko_z','age_at_fight','layoff_days_c']

# Build division dummies via patsy on full panel
_, div_mat = patsy.dmatrices(
    'calibration_gap ~ C(division)',
    data=pd.concat([panel_est,
                    panel_est.iloc[[0]].assign(division='other',calibration_gap=0.)],
                   ignore_index=True),
    return_type='dataframe')
div_mat = div_mat.iloc[:len(panel_est)]   # drop dummy row

y_full  = panel_est['calibration_gap'].values
yc_full = panel_est['year_c'].values
fid     = panel_est['fighter_id'].values

# Base columns (controls, no candidate vars)
Z_base = np.column_stack([
    np.ones(len(panel_est)),
    panel_est[CTRLS].values,
    yc_full,
    div_mat.values[:, 1:],   # drop Intercept (already in ones)
])

family_results = []

for cand in CANDIDATES:
    xj = panel_est[cand].values
    xj_yc = xj * yc_full

    # Design: [1, controls, year_c, div_dummies, xj, xj×year_c]
    X_j = np.column_stack([Z_base, xj, xj_yc])
    n_j, k_j = X_j.shape

    try:
        betas = np.linalg.lstsq(X_j, y_full, rcond=None)[0]
        resid = y_full - X_j @ betas
        # Cluster SE by fighter_id (sandwich)
        bread = np.linalg.pinv(X_j.T @ X_j)
        uniq_f = np.unique(fid)
        G = len(uniq_f)
        meat = np.zeros((k_j, k_j))
        for f in uniq_f:
            idx   = fid == f
            score = X_j[idx].T @ resid[idx]
            meat += np.outer(score, score)
        meat *= G / (G - 1) * (n_j - 1) / (n_j - k_j)
        vcov  = bread @ meat @ bread
        se_j  = np.sqrt(abs(vcov[-1, -1]))   # last col = xj_yc
        coef_j = betas[-1]
        t_j    = coef_j / se_j if se_j > 0 else np.nan
        p_j    = 2 * stats.t.sf(abs(t_j), df=G - 1)
        family_results.append({
            'variable': cand, 'coef': coef_j, 'se': se_j,
            't': t_j, 'p': p_j, 'negative': coef_j < 0
        })
    except Exception as ex:
        family_results.append({
            'variable': cand, 'coef': np.nan, 'se': np.nan,
            't': np.nan, 'p': np.nan, 'negative': False
        })

df_fam = pd.DataFrame(family_results)

n_neg  = df_fam['negative'].sum()
n_tot  = len(df_fam)
n_sig  = (df_fam['p'] < 0.05).sum()
n_sig_neg = ((df_fam['p'] < 0.05) & df_fam['negative']).sum()

print(f'  {"Variable":<25} {"Int×Yr coef":>12} {"SE":>10} {"p":>8} {"Sig":>5} {"Dir":>5}')
print('  ' + '-'*65)
for _, row in df_fam.sort_values('coef').iterrows():
    direction = '(-)' if row['negative'] else '(+)'
    print(f'  {row["variable"]:<25} {row["coef"]:>+12.6f} {row["se"]:>10.6f} '
          f'{row["p"]:>8.4f} {stars(row["p"]):>5} {direction:>5}')

print(f'\n  Negative interactions: {n_neg} of {n_tot}')
print(f'  Significant (p<0.05):  {n_sig} of {n_tot}  ({n_sig_neg} are negative)')

# Sign test
binom_p = stats.binomtest(n_neg, n_tot, 0.5, alternative='greater').pvalue
print(f'  Sign test (H0: <=50% negative): p={binom_p:.4f}  {stars(binom_p)}')

# Pooled standardised test (mean z)
z_vals = df_fam['t'].dropna().values
z_mean = z_vals.mean()
z_se   = z_vals.std() / np.sqrt(len(z_vals))
z_p    = stats.norm.sf(-z_mean / z_se) if z_se > 0 else np.nan  # one-sided: H0 mean>=0
print(f'  Pooled mean standardised interaction: z_mean={z_mean:.4f}  '
      f'SE={z_se:.4f}  p(one-sided, H0:mean>=0)={z_p:.4f}  {stars(z_p)}')

print('\n' + '='*70)
print('SECTION 3 — Power benchmark (observed vs. expected per window)')
print('='*70)
print('Rolling 4-year windows (for illustration only — not used for inference).')
print('Expected = sum of analytic power given full-sample t-stats, scaled by sqrt(N_w/N).')
print('NOTE: overlapping windows; CI estimates not independent.\n')

years_all = sorted(panel_est['year'].unique())
N_full    = len(panel_est)

# Full-sample t-stats for all 41 candidates (single var model with controls)
full_t = {}
for cand in CANDIDATES:
    xj    = panel_est[cand].values
    X_j   = np.column_stack([Z_base, xj])
    betas = np.linalg.lstsq(X_j, y_full, rcond=None)[0]
    resid = y_full - X_j @ betas
    bread = np.linalg.pinv(X_j.T @ X_j)
    uniq_f = np.unique(fid)
    G = len(uniq_f)
    meat = np.zeros((X_j.shape[1], X_j.shape[1]))
    for f in uniq_f:
        idx = fid == f
        score = X_j[idx].T @ resid[idx]
        meat += np.outer(score, score)
    meat *= G / (G - 1) * (len(y_full) - 1) / (len(y_full) - X_j.shape[1])
    vcov = bread @ meat @ bread
    se_j = np.sqrt(abs(vcov[-1, -1]))
    full_t[cand] = betas[-1] / se_j if se_j > 0 else 0.0

z_crit = 1.96

windows = []
for start in range(min(years_all), max(years_all) - WINDOW + 2):
    end = start + WINDOW - 1
    idx_w = (panel_est['year'] >= start) & (panel_est['year'] <= end)
    N_w = idx_w.sum()
    if N_w < 200:
        continue

    sub     = panel_est[idx_w].reset_index(drop=True)
    y_w     = sub['calibration_gap'].values
    yc_w    = sub['year_c'].values
    fid_w   = sub['fighter_id'].values
    _, dmat_w = patsy.dmatrices(
        'calibration_gap ~ C(division)',
        data=pd.concat([sub, sub.iloc[[0]].assign(division='other', calibration_gap=0.)],
                       ignore_index=True),
        return_type='dataframe')
    dmat_w = dmat_w.iloc[:len(sub)]
    Z_w = np.column_stack([
        np.ones(len(sub)),
        sub[CTRLS].values,
        yc_w,
        dmat_w.values[:, 1:],
    ])

    obs_sig = 0
    exp_sig = 0.0
    for cand in CANDIDATES:
        xj_w  = sub[cand].values
        X_jw  = np.column_stack([Z_w, xj_w])
        try:
            b_w   = np.linalg.lstsq(X_jw, y_w, rcond=None)[0]
            res_w = y_w - X_jw @ b_w
            bread_w = np.linalg.pinv(X_jw.T @ X_jw)
            uniq_fw = np.unique(fid_w)
            Gw = len(uniq_fw)
            meat_w = np.zeros((X_jw.shape[1], X_jw.shape[1]))
            for f in uniq_fw:
                idx_f = fid_w == f
                sc = X_jw[idx_f].T @ res_w[idx_f]
                meat_w += np.outer(sc, sc)
            meat_w *= Gw / (Gw - 1) * (len(y_w) - 1) / (len(y_w) - X_jw.shape[1])
            vcov_w = bread_w @ meat_w @ bread_w
            se_jw  = np.sqrt(abs(vcov_w[-1, -1]))
            t_jw   = b_w[-1] / se_jw if se_jw > 0 else 0
            p_jw   = 2 * stats.t.sf(abs(t_jw), df=Gw - 1)
            if p_jw < 0.05:
                obs_sig += 1
        except:
            pass

        # Expected power: scale full-sample t by sqrt(N_w / N_full)
        t_expected = abs(full_t[cand]) * np.sqrt(N_w / N_full)
        power = stats.norm.sf(z_crit - t_expected) + stats.norm.cdf(-z_crit - t_expected)
        exp_sig += power

    windows.append({'window': f'{start}-{end}', 'N': N_w,
                    'obs_sig': obs_sig, 'exp_sig': exp_sig,
                    'ratio': obs_sig / exp_sig if exp_sig > 0 else np.nan})
    print(f'  {start}-{end}: N={N_w:,}  obs={obs_sig}  exp={exp_sig:.1f}  '
          f'ratio={obs_sig/exp_sig:.2f}' if exp_sig > 0 else
          f'  {start}-{end}: N={N_w:,}  obs={obs_sig}  exp={exp_sig:.1f}')

df_win = pd.DataFrame(windows)
print(f'\n  {"Window":<12} {"N":>6}  {"Obs sig":>8}  {"Exp sig":>9}  {"Obs/Exp":>9}')
print('  ' + '-'*50)
for _, r in df_win.iterrows():
    marker = ' <-- below expected' if r['ratio'] < 1.0 else ''
    print(f'  {r["window"]:<12} {int(r["N"]):>6}  {int(r["obs_sig"]):>8}  '
          f'{r["exp_sig"]:>9.1f}  {r["ratio"]:>9.2f}{marker}')

# Trend in ratio (is obs/exp falling over time?)
if len(df_win) > 3:
    x_trend = np.arange(len(df_win))
    slope, intercept, r, p_trend, se_trend = stats.linregress(x_trend, df_win['ratio'])
    print(f'\n  Trend in obs/exp ratio: slope={slope:+.4f}  p={p_trend:.4f}  {stars(p_trend)}')
    print(f'  (negative slope = fewer signals surviving than power predicts → consistent with learning)')

print('\n' + '='*70)
print('SECTION 4 — Placebo: permutation null for family-decay statistic')
print('='*70)
print(f'N_PERM={N_PERM}  Statistic: proportion of 41 interactions negative.')
print('Permute calibration_gap (global), re-run all 41 signal×year_c interactions.')
print('Empirical p = proportion of permutations with >= observed n_neg.\n')

# Precompute the "beta_row" for each candidate's interaction term
# beta_row_j = ((X_j'X_j)^{-1} X_j')[-1]  → shape (n,)
# Interaction coef for permuted y_perm = beta_row_j @ y_perm
beta_rows = []
for cand in CANDIDATES:
    xj    = panel_est[cand].values
    xj_yc = xj * yc_full
    X_j   = np.column_stack([Z_base, xj, xj_yc])
    try:
        XtX_inv = np.linalg.pinv(X_j.T @ X_j)
        proj    = XtX_inv @ X_j.T   # shape (k, n)
        beta_rows.append(proj[-1])   # last row = interaction term projection
    except:
        beta_rows.append(np.zeros(len(y_full)))

beta_rows = np.array(beta_rows)   # shape (41, n)

# Real family decay stat
real_neg = n_neg

# Permutation loop
perm_neg_counts = np.empty(N_PERM, dtype=int)
for b in range(N_PERM):
    y_perm = rng.permutation(y_full)
    int_coefs = beta_rows @ y_perm   # shape (41,)
    perm_neg_counts[b] = (int_coefs < 0).sum()
    if (b + 1) % 100 == 0:
        print(f'  Permutation {b+1}/{N_PERM}...')

perm_p = (perm_neg_counts >= real_neg).mean()
perm_mean = perm_neg_counts.mean()
perm_sd   = perm_neg_counts.std()

print(f'\n  Observed n_neg (real data): {real_neg} of {n_tot}')
print(f'  Permutation null — mean: {perm_mean:.2f}  SD: {perm_sd:.2f}  '
      f'(expected ~20.5 under H0)')
print(f'  Empirical p (>= observed): {perm_p:.4f}  {stars(perm_p)}')
if perm_p >= 0.05:
    print('  INTERPRETATION: Family-decay pattern is NOT distinguishable from '
          'selection artifact. Do not claim "learning" from family evidence alone.')
else:
    print('  INTERPRETATION: Family-decay exceeds permutation null. '
          'Consistent with genuine decay beyond selection artifact.')

print('\n' + '='*70)
print('SECTION 5 — Composition controls: fighter fixed effects on #1 trend')
print('='*70)
print('Within-fighter demeaning (equivalent to fighter FEs).')
print('Tests whether the same fighter becomes less mispriced over time.\n')

# Within-fighter demean: subtract fighter means from all variables
dem_cols = (['calibration_gap','sapm_r_opp','year_c','sapm_x_yc',
             'glicko_z','age_at_fight','layoff_days_c']
            + OTHER_CANDS)

panel_dm = panel_est.copy()
for col in dem_cols:
    if col in panel_dm.columns:
        panel_dm[col] = (panel_dm[col]
                         - panel_dm.groupby('fighter_id')[col].transform('mean'))

# Rebuild interaction after demeaning
panel_dm['sapm_x_yc'] = panel_dm['sapm_r_opp'] * panel_dm['year_c']

# Formula: no division FE needed after within-transform (fighter absorbs division)
FORMULA_FE = ('calibration_gap ~ sapm_r_opp + year_c + sapm_x_yc + '
              + ' + '.join(OTHER_CANDS)
              + ' + glicko_z + age_at_fight + layoff_days_c - 1')

lhs_fe, rhs_fe = patsy.dmatrices(FORMULA_FE, data=panel_dm, return_type='dataframe')
mod_fe = sm.OLS(lhs_fe.iloc[:,0], rhs_fe).fit(
    cov_type='cluster', cov_kwds={'groups': panel_dm.loc[lhs_fe.index,'fighter_id'].values})

for vname in ['sapm_r_opp','year_c','sapm_x_yc']:
    if vname in mod_fe.params.index:
        c  = mod_fe.params[vname]
        se = mod_fe.bse[vname]
        p  = mod_fe.pvalues[vname]
        ci = mod_fe.conf_int().loc[vname]
        print(f'  {vname:<20}  coef={c:+.6f}  SE={se:.6f}  '
              f'CI=[{ci[0]:+.6f},{ci[1]:+.6f}]  p={p:.4f}  {stars(p)}')

print(f'  N={len(lhs_fe):,}  (within-fighter; fighter FEs absorbed)')

print('\n' + '='*70)
print('SECTION 6 — Opening-to-closing convergence series and trend')
print('='*70)
print('Does closing calibration gap shrink more than opening over time?')
print('Evidence of market learning that does not route through mined signals.\n')

panel_est['cal_gap_open'] = panel_est['won'] - panel_est['market_prob_shin_open']

by_year = (panel_est.groupby('year')
           .agg(
               n           = ('calibration_gap', 'count'),
               var_close   = ('calibration_gap', 'var'),
               var_open    = ('cal_gap_open', 'var'),
               mae_close   = ('calibration_gap', lambda x: x.abs().mean()),
               mae_open    = ('cal_gap_open', lambda x: x.abs().mean()),
           ).reset_index())

by_year['ratio_var'] = by_year['var_close'] / by_year['var_open']
by_year['ratio_mae'] = by_year['mae_close'] / by_year['mae_open']

print(f'  {"Year":>6} {"N":>5} {"Var(close)":>11} {"Var(open)":>11} '
      f'{"MAE(close)":>11} {"MAE(open)":>11} {"Var ratio":>10}')
print('  ' + '-'*75)
for _, r in by_year.iterrows():
    print(f'  {int(r["year"]):>6} {int(r["n"]):>5} {r["var_close"]:>11.5f} '
          f'{r["var_open"]:>11.5f} {r["mae_close"]:>11.5f} '
          f'{r["mae_open"]:>11.5f} {r["ratio_var"]:>10.4f}')

# Trend tests (exclude 2007 = 1 obs, 2026 = partial year)
by_yr_trim = by_year[(by_year['year'] >= 2008) & (by_year['year'] <= 2025)].copy()

for metric, label in [('var_close', 'Var(close)'),
                       ('var_open',  'Var(open)'),
                       ('ratio_var', 'Var(close)/Var(open)')]:
    sl, ic, r_val, p_val, se_val = stats.linregress(
        by_yr_trim['year'], by_yr_trim[metric])
    print(f'\n  Trend in {label}: slope={sl:+.6f}  SE={se_val:.6f}  '
          f'p={p_val:.4f}  {stars(p_val)}')

# Corr(open, close) by year
print('\n  Year-by-year corr(cal_gap_open, cal_gap_close):')
corrs = (panel_est[panel_est['year'].between(2008,2025)]
         .groupby('year')[['calibration_gap','cal_gap_open']]
         .corr().unstack()['calibration_gap']['cal_gap_open'])
for yr, c_val in corrs.items():
    print(f'    {yr}: {c_val:.4f}')
sl_c, _, _, p_c, se_c = stats.linregress(corrs.index, corrs.values)
print(f'  Trend in corr: slope={sl_c:+.5f}  SE={se_c:.5f}  p={p_c:.4f}  {stars(p_c)}')

print('\n' + '='*70)
print('SECTION 7 — Honest summary')
print('='*70)

# Re-read key values
s1_int_p = None
for vname in ['sapm_x_yc']:
    if vname in col_names:
        i = col_names.index(vname)
        t_v = mod_1a.params[vname] / se_cgm[i]
        G = min(len(np.unique(g1)), len(np.unique(g2))) - 1
        s1_int_p = 2 * stats.t.sf(abs(t_v), df=G)

print(f"""
  1. Single-signal × time interaction (sapm_r_opp × year_c):
     coef reported above with two-way CGM SE.
     p = {f"{s1_int_p:.4f}" if s1_int_p is not None else "see above"}
     {'Significant — consistent with gradual decay.' if s1_int_p is not None and s1_int_p < 0.05 else 'Not significant — no confirmed decay in headline test.'}

  2. Family-level trend (41 signals):
     {n_neg} of {n_tot} interaction coefficients are negative.
     Sign test p = {binom_p:.4f}  {stars(binom_p)}
     Pooled standardised mean z = {z_mean:.4f}  p = {z_p:.4f}  {stars(z_p)}

  3. Power benchmark:
     See table above. Key question: does obs/exp ratio decline over time?
     Trend slope = {slope:+.4f}  p = {p_trend:.4f}  {stars(p_trend)}
     {'Declining ratio — consistent with genuine decay beyond power gradient.' if slope < 0 else 'No declining ratio — cannot rule out power gradient.'}

  4. Placebo:
     Empirical p = {perm_p:.4f}  {stars(perm_p)}
     {'Decay NOT distinguishable from selection artifact. "Learning" claim unsupported by family evidence.' if perm_p >= 0.05 else 'Decay exceeds permutation null. Selection artifact alone insufficient.'}

  5. Composition controls (fighter FEs):
     See interaction coefficient above.

  Confounds addressed / open:
  - Selection artifact: addressed by placebo (#4).
  - Power gradient: addressed by obs/exp benchmark (#3).
  - Composition: partially addressed by fighter FEs (#5).

  Appropriate claim (if #1 significant): "The sapm_r_opp mispricing signal
  is consistent with the adaptive-markets hypothesis (Lo 2004) — a declining
  interaction with time is observed, though the family-level evidence
  [{'' if perm_p < 0.05 else 'does NOT '}clear the placebo threshold]."
""")

print('Done.')
