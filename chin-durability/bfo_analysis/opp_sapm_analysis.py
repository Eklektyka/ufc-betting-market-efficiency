"""
opp_sapm_analysis.py  (v3 — interactions removed)
===================================================
STEP 1 — Saturated OLS, full sample 2007–2026-06-06, cluster-SE by fighter.
STEP 2 — Specification curve (~288 specs) for sapm_r_opp.
STEP 3 — Frozen temporal holdout: fit on 2007-2019, freeze, apply to 2020–2026-06-06.
STEP 4 — Economic significance on frozen predictions: bootstrap 95% CI
          (10,000 resamples) using ACTUAL closing decimal odds (1/q_close).
STEP 5 — Honest summary.

Data: trimmed to 2026-04-18.
"""
import sys, warnings, itertools
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import statsmodels.api as sm
import patsy
from pathlib import Path

SEED   = 42
N_BOOT = 10_000
VIG    = 0.020
rng    = np.random.default_rng(SEED)
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

UFC_WEIGHT_CLASSES = {
    'heavyweight', 'light heavyweight', 'middleweight', 'welterweight',
    'lightweight', 'featherweight', 'bantamweight', 'flyweight', 'strawweight',
    "women's bantamweight", "women's flyweight", "women's featherweight",
    "women's strawweight", 'catch weight',
}

# ── 0. Load & build panel ──────────────────────────────────────────────────────
print('Loading panel...')
panel = pd.read_csv(OUT_DIR / 'style_panel.csv', parse_dates=['date'])
panel['year']          = panel['date'].dt.year
panel['layoff_days_c'] = panel['layoff_days'].clip(0, 365 * 2)

opp_join = (panel[['fight_id', 'fighter_id'] + STYLE_VARS]
            .rename(columns={'fighter_id': 'opponent_id',
                             **{v: v + '_opp' for v in STYLE_VARS}}))
panel = panel.merge(opp_join, on=['fight_id', 'opponent_id'], how='left')

req = (ALL_ATOMIC
       + ['calibration_gap', 'market_prob_shin', 'q_close', 'glicko_z',
          'age_at_fight', 'layoff_days_c', 'won', 'division', 'year',
          'fighter_id', 'sapm_r_opp'])
panel_est = panel[panel[req].notna().all(axis=1)].copy().reset_index(drop=True)

train = panel_est[panel_est['year'] <= 2019].copy()
test  = panel_est[panel_est['year'] >= 2020].copy()

# Fix (item 2): re-standardise glicko_z on training moments only
_glicko_mean = train['glicko'].mean()
_glicko_std  = train['glicko'].std()
for _df in [panel_est, train, test]:
    _df['glicko_z'] = (_df['glicko'] - _glicko_mean) / _glicko_std
print(f'[Fix] glicko_z re-standardised on training moments '
      f'(mean={_glicko_mean:.1f}, SD={_glicko_std:.1f})')

print(f'Panel (complete cases): N={len(panel_est):,}  '
      f'({panel_est["date"].min().date()} – {panel_est["date"].max().date()})')
print(f'Train (2007-2019):      N={len(train):,}  '
      f'({train["date"].min().date()} – {train["date"].max().date()})')
print(f'Test  (2020-2026):      N={len(test):,}   '
      f'({test["date"].min().date()} – {test["date"].max().date()})')

train_divisions = set(train['division'].dropna().unique())

def align_design(formula, data, ref_cols):
    _, rhs = patsy.dmatrices(formula, data=data, return_type='dataframe')
    out = pd.DataFrame(index=rhs.index)
    for col in ref_cols:
        out[col] = rhs[col].values if col in rhs.columns else 0.0
    return out

def remap_division(d, train_divs):
    if d in train_divs:
        return d
    if isinstance(d, str) and d.strip().lower() in UFC_WEIGHT_CLASSES:
        return d
    return 'other'

# ── STEP 1 — Saturated OLS, full sample ───────────────────────────────────────
print('\n' + '='*70)
print('STEP 1 — Saturated OLS, full sample, cluster SE by fighter')
print('='*70)

dummy_row = panel_est.iloc[[0]].assign(division='other', calibration_gap=0.0)
full_aug  = pd.concat([panel_est, dummy_row], ignore_index=True)
dummy_pos = len(full_aug) - 1

lhs_aug, rhs_aug = patsy.dmatrices(FORMULA, data=full_aug, return_type='dataframe')
real_mask = lhs_aug.index != dummy_pos
lhs_full  = lhs_aug[real_mask]
rhs_full  = rhs_aug[real_mask]

mod_full = sm.OLS(lhs_full.iloc[:, 0], rhs_full).fit(
    cov_type='cluster',
    cov_kwds={'groups': full_aug.loc[lhs_full.index, 'fighter_id']})

print(f'\nN={len(lhs_full):,}  adj-R²={mod_full.rsquared_adj:.4f}')
print('\nFull coefficient table:')
print(f'{"Variable":<50} {"Coef":>10} {"SE":>10} {"t":>8} {"p":>8}')
print('-'*92)
for var in mod_full.params.index:
    c   = mod_full.params[var]
    se  = mod_full.bse[var]
    t   = mod_full.tvalues[var]
    p   = mod_full.pvalues[var]
    sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else '.' if p < 0.1 else ''
    print(f'{var:<50} {c:>+10.5f} {se:>10.5f} {t:>8.3f} {p:>8.4f} {sig}')

coef_sapm_full = mod_full.params.get('sapm_r_opp', np.nan)
p_sapm_full    = mod_full.pvalues.get('sapm_r_opp', np.nan)
print(f'\nKEY: sapm_r_opp  coef={coef_sapm_full:+.5f}  p={p_sapm_full:.4f}')

# ── STEP 1b — Romano-Wolf FWER correction ─────────────────────────────────────
print('\n' + '='*70)
print('STEP 1b — Romano-Wolf stepdown FWER (10,000 permutations)')
print('='*70)

RW_VARS = ['sapm_r_opp', 'sapm_r', 'age_at_fight', 'slpm_r', 'slpm_r_opp']

# Observed |t|-stats for each variable
obs_t = np.array([abs(mod_full.tvalues[v]) for v in RW_VARS])

# Permutation: shuffle calibration_gap, refit OLS, collect |t|-stats
# Use HC0 SE in permutation distribution (standard for RW; much faster than cluster)
N_RW    = 10_000
y_orig  = lhs_full.iloc[:, 0].values
X       = rhs_full.values
var_idx = [list(rhs_full.columns).index(v) for v in RW_VARS]

XtX_inv = np.linalg.pinv(X.T @ X)          # precompute once
XtX_inv_X = XtX_inv @ X.T                  # shape (k, n)

perm_t = np.empty((N_RW, len(RW_VARS)))
for b in range(N_RW):
    y_perm  = rng.permutation(y_orig)
    beta_p  = XtX_inv_X @ y_perm
    resid_p = y_perm - X @ beta_p
    # HC0 SE (fast: no grouping needed)
    scores  = (resid_p[:, None] * X)        # (n, k)
    meat    = scores.T @ scores             # (k, k)
    vcov    = XtX_inv @ meat @ XtX_inv
    se_p    = np.sqrt(np.diag(vcov))
    perm_t[b] = np.abs(beta_p[var_idx] / se_p[var_idx])

# Stepdown: sort by observed |t| descending, enforce monotonicity
order    = np.argsort(-obs_t)          # indices sorted by |t| high→low
rw_p     = np.empty(len(RW_VARS))
for step, idx in enumerate(order):
    # p = proportion of perms where max |t| over remaining vars >= observed |t|
    remaining = order[step:]
    max_perm  = perm_t[:, remaining].max(axis=1)
    rw_p[idx] = (max_perm >= obs_t[idx]).mean()

# Monotonicity enforcement (stepdown: adjusted p can only increase)
for step in range(1, len(order)):
    idx_curr = order[step]
    idx_prev = order[step - 1]
    rw_p[idx_curr] = max(rw_p[idx_curr], rw_p[idx_prev])

print(f'\n{"Variable":<20} {"Obs |t|":>9} {"Naive p":>9} {"RW p":>9} {"Sig":>5}')
print('-' * 57)
for i, v in enumerate(RW_VARS):
    naive_p = mod_full.pvalues[v]
    sig     = '***' if rw_p[i] < 0.001 else '**' if rw_p[i] < 0.01 else '*' if rw_p[i] < 0.05 else '.' if rw_p[i] < 0.1 else ''
    print(f'{v:<20} {obs_t[i]:>9.3f} {naive_p:>9.4f} {rw_p[i]:>9.4f} {sig:>5}')

# ── STEP 1c — Mincer-Zarnowitz logit ─────────────────────────────────────────
print('\n' + '='*70)
print('STEP 1c — Mincer-Zarnowitz logit')
print('='*70)
print('Correct functional form for binary outcome.')
print('Variant A: β on logit(market_prob) free.')
print('Variant B: β≡1 (offset) — residual predictability after perfect calibration.')

panel_est['logit_mkt'] = np.log(
    panel_est['market_prob_shin'].clip(1e-6, 1-1e-6) /
    (1 - panel_est['market_prob_shin'].clip(1e-6, 1-1e-6)))

FORMULA_MZA = ('won ~ logit_mkt + sapm_r_opp + age_at_fight + glicko_z '
               '+ layoff_days_c + C(year)')

lhs_mza, rhs_mza = patsy.dmatrices(FORMULA_MZA, data=panel_est, return_type='dataframe')
grp_mza = panel_est.loc[lhs_mza.index, 'fighter_id'].values

mod_mza = sm.Logit(lhs_mza.iloc[:, 0], rhs_mza).fit(
    cov_type='cluster', cov_kwds={'groups': grp_mza}, disp=False)

c_mkt  = mod_mza.params.get('logit_mkt', np.nan)
se_mkt = mod_mza.bse.get('logit_mkt', np.nan)
t_cal  = (c_mkt - 1) / se_mkt if se_mkt > 0 else np.nan
c_sa   = mod_mza.params.get('sapm_r_opp', np.nan)
p_sa   = mod_mza.pvalues.get('sapm_r_opp', np.nan)
sig_sa = '***' if p_sa < 0.001 else '**' if p_sa < 0.01 else '*' if p_sa < 0.05 else '.'

print(f'\nA — Unconstrained (N={len(lhs_mza):,}  pseudo-R²={mod_mza.prsquared:.4f}):')
print(f'  logit_mkt   coef={c_mkt:+.5f}  '
      f'MZ calibration test H0 β=1: t={t_cal:+.3f}  '
      f'{"REJECTED" if abs(t_cal) > 1.96 else "NOT REJECTED"}')
print(f'  sapm_r_opp  coef={c_sa:+.5f}  p={p_sa:.4f}  {sig_sa}')

# B: Offset logit (β≡1 on logit_mkt)
FORMULA_MZB = ('won ~ sapm_r_opp + age_at_fight + glicko_z '
               '+ layoff_days_c + C(year)')

lhs_mzb, rhs_mzb = patsy.dmatrices(FORMULA_MZB, data=panel_est, return_type='dataframe')
offset_b  = panel_est.loc[lhs_mzb.index, 'logit_mkt'].values
grp_mzb   = panel_est.loc[lhs_mzb.index, 'fighter_id'].values

mod_mzb = sm.GLM(
    lhs_mzb.iloc[:, 0], rhs_mzb,
    family=sm.families.Binomial(),
    offset=offset_b).fit(
    cov_type='cluster', cov_kwds={'groups': grp_mzb})

c_sa_b = mod_mzb.params.get('sapm_r_opp', np.nan)
p_sa_b = mod_mzb.pvalues.get('sapm_r_opp', np.nan)
sig_b  = '***' if p_sa_b < 0.001 else '**' if p_sa_b < 0.01 else '*' if p_sa_b < 0.05 else '.'

print(f'\nB — Offset β≡1 (N={len(lhs_mzb):,}):')
print(f'  sapm_r_opp  coef={c_sa_b:+.5f}  p={p_sa_b:.4f}  {sig_b}')
print(f'\nKEY MZ: sapm_r_opp survives logit reformulation: '
      f'{"YES" if p_sa_b < 0.05 else "NO"}  (offset p={p_sa_b:.4f})')

# ── STEP 2 — Specification curve ──────────────────────────────────────────────
print('\n' + '='*70)
print('STEP 2 — Specification curve for sapm_r_opp (288 specs)')
print('='*70)
print('Varying: controls (age, layoff, glicko, division FE, year FE) x '
      'year start (2007/2010/2012) x division drops (none/HW/LW).')

ctrl_options = list(itertools.product(
    [True, False],  # age_at_fight
    [True, False],  # layoff_days_c
    [True, False],  # glicko_z
    [True, False],  # C(division)
    [True, False],  # C(year)
))

year_starts = [2007, 2010, 2012]
div_drops   = [None, 'Heavyweight', 'Lightweight']

specs_results = []
spec_count    = 0

for (use_age, use_layoff, use_glicko, use_div, use_year), yr_start, div_drop in itertools.product(
        ctrl_options, year_starts, div_drops):

    ctrl_parts = []
    if use_glicko:  ctrl_parts.append('glicko_z')
    if use_age:     ctrl_parts.append('age_at_fight')
    if use_layoff:  ctrl_parts.append('layoff_days_c')
    if use_div:     ctrl_parts.append('C(division)')
    if use_year:    ctrl_parts.append('C(year)')

    formula_s = ('calibration_gap ~ '
                 + ' + '.join(ALL_ATOMIC)
                 + ((' + ' + ' + '.join(ctrl_parts)) if ctrl_parts else ''))

    samp = panel_est[panel_est['year'] >= yr_start].copy()
    if div_drop:
        samp = samp[samp['division'] != div_drop]
    if len(samp) < 100:
        continue

    try:
        lhs_s, rhs_s = patsy.dmatrices(formula_s, data=samp, return_type='dataframe')
        mod_s = sm.OLS(lhs_s.iloc[:, 0], rhs_s).fit(
            cov_type='cluster',
            cov_kwds={'groups': samp.loc[lhs_s.index, 'fighter_id']})
        if 'sapm_r_opp' in mod_s.params:
            specs_results.append({
                'coef': mod_s.params['sapm_r_opp'],
                'p':    mod_s.pvalues['sapm_r_opp'],
                'N':    len(lhs_s),
            })
        spec_count += 1
    except Exception:
        continue

specs_df = pd.DataFrame(specs_results)
pos_share = (specs_df['coef'] > 0).mean()
sig_share = (specs_df['p'] < 0.05).mean()
pos_sig   = ((specs_df['coef'] > 0) & (specs_df['p'] < 0.05)).mean()

print(f'\nTotal specifications: {spec_count}')
print(f'sapm_r_opp:')
print(f'  Share positive-signed          : {pos_share:.1%}')
print(f'  Share significant (p<.05)      : {sig_share:.1%}')
print(f'  Share positive AND significant : {pos_sig:.1%}')
print(f'  Coef range                     : [{specs_df["coef"].min():+.5f}, {specs_df["coef"].max():+.5f}]')
print(f'  Median coef                    : {specs_df["coef"].median():+.5f}')

# ── STEP 3 — Frozen temporal holdout ──────────────────────────────────────────
print('\n' + '='*70)
print('STEP 3 — Frozen temporal holdout (train 2007-2019 → test 2020-2026-04-18)')
print('='*70)

test_divs_unseen = set(test['division'].dropna().unique()) - train_divisions
print(f'Unseen test divisions: {sorted(test_divs_unseen) if test_divs_unseen else "none"}')

test_remapped = test.copy()
test_remapped['division'] = test_remapped['division'].apply(
    lambda d: remap_division(d, train_divisions))
n_other = (test_remapped['division'] == 'other').sum()
print(f'Rows remapped to "other": {n_other}')

dummy_row_tr = train.iloc[[0]].assign(division='other', calibration_gap=0.0)
train_aug    = pd.concat([train, dummy_row_tr], ignore_index=True)
dummy_pos_tr = len(train_aug) - 1

lhs_aug_tr, rhs_aug_tr = patsy.dmatrices(FORMULA, data=train_aug, return_type='dataframe')
real_mask_tr = lhs_aug_tr.index != dummy_pos_tr
lhs_tr       = lhs_aug_tr[real_mask_tr]
rhs_tr       = rhs_aug_tr[real_mask_tr]

mod_is = sm.OLS(lhs_tr.iloc[:, 0], rhs_tr).fit(
    cov_type='cluster',
    cov_kwds={'groups': train_aug.loc[lhs_tr.index, 'fighter_id']})

coef_is = mod_is.params.get('sapm_r_opp', np.nan)
p_is    = mod_is.pvalues.get('sapm_r_opp', np.nan)
print(f'\nIS  sapm_r_opp: coef={coef_is:+.5f}  p={p_is:.4f}  '
      f'(N={len(lhs_tr):,}  adj-R²={mod_is.rsquared_adj:.4f})')

rhs_te = align_design(FORMULA, test_remapped, ref_cols=rhs_tr.columns)
test_scored = test_remapped.loc[rhs_te.index].copy()
test_scored['frozen_pred'] = mod_is.predict(rhs_te).values
test_scored['dec_odds']    = 1.0 / test_scored['q_close']

corr = np.corrcoef(test_scored['frozen_pred'], test_scored['calibration_gap'])[0, 1]
print(f'Corr(frozen_pred, actual_gap): {corr:.4f}')

lhs_oos, rhs_oos = patsy.dmatrices(FORMULA, data=test_remapped, return_type='dataframe')
mod_oos = sm.OLS(lhs_oos.iloc[:, 0], rhs_oos).fit(
    cov_type='cluster',
    cov_kwds={'groups': test_remapped.loc[lhs_oos.index, 'fighter_id']})

coef_oos = mod_oos.params.get('sapm_r_opp', np.nan)
se_oos   = mod_oos.bse.get('sapm_r_opp', np.nan)
p_oos    = mod_oos.pvalues.get('sapm_r_opp', np.nan)
ci_lo    = float(mod_oos.conf_int().loc['sapm_r_opp'][0])
ci_hi    = float(mod_oos.conf_int().loc['sapm_r_opp'][1])
atten    = coef_oos / coef_is if coef_is != 0 else np.nan

print(f'OOS sapm_r_opp: coef={coef_oos:+.5f}  SE={se_oos:.5f}  p={p_oos:.4f}  '
      f'CI=[{ci_lo:+.5f}, {ci_hi:+.5f}]')
print(f'Attenuation (OOS/IS): {atten:.3f}  ({(1-atten)*100:.0f}% decay)')

thresh  = test_scored['sapm_r_opp'].quantile(0.90)
top10   = test_scored[test_scored['sapm_r_opp'] >= thresh]
gap_top = (top10['won'].mean() - top10['market_prob_shin'].mean()) * 100
net_top = gap_top - VIG * 100
print(f'\nTop-decile (sapm_r_opp >= {thresh:.3f}): '
      f'N={len(top10)}  gap={gap_top:+.2f}pp  net={net_top:+.2f}pp')

# ── STEP 4 — Economic significance / bootstrap CI ─────────────────────────────
print('\n' + '='*70)
print('STEP 4 — P&L bootstrap CI (10,000 resamples, ACTUAL closing decimal odds)')
print('='*70)

def net_return(df):
    return np.where(df['won'].values == 1, df['dec_odds'].values - 1.0, -1.0)

def boot_ci(returns, alpha=0.05):
    n     = len(returns)
    means = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx      = rng.integers(0, n, n)
        means[b] = returns[idx].mean()
    point = returns.mean() * 100
    lo, hi = np.percentile(means * 100, [100*alpha/2, 100*(1-alpha/2)])
    p_val  = 2 * min((means <= 0).mean(), (means >= 0).mean())
    return point, lo, hi, p_val

def report_strategy(name, df):
    r = net_return(df)
    edge, lo, hi, p = boot_ci(r)
    print(f'\n{name}')
    print(f'  N bets        : {len(df):,}')
    print(f'  Win rate      : {df["won"].mean()*100:.1f}%')
    print(f'  Net edge      : {edge:+.2f} pp')
    print(f'  95% boot CI   : [{lo:+.2f}, {hi:+.2f}] pp')
    print(f'  Bootstrap p   : {p:.3f}')
    print(f'  Clears zero   : {"YES" if lo > 0 else "NO (CI crosses 0)"}')
    print(f'  Beats 2pp vig : {"YES" if lo > VIG * 100 else "NO"}')

s_a = test_scored[test_scored['frozen_pred'] > 0]
report_strategy('Strategy A — frozen_pred > 0  [PRE-COMMITTED]', s_a)

s_b = test_scored[test_scored['sapm_r_opp'] >= thresh]
report_strategy('Strategy B — top-decile sapm_r_opp  [PRE-COMMITTED]', s_b)

# ── STEP 5 — Honest summary ────────────────────────────────────────────────────
print('\n' + '='*70)
print('STEP 5 — HONEST SUMMARY')
print('='*70)
print(f"""
sapm_r_opp (opponent chin vulnerability):
  Full-sample coef             : {coef_sapm_full:+.5f}  p={p_sapm_full:.4f}
  IS coef  (2007-2019)         : {coef_is:+.5f}  p={p_is:.4f}
  OOS coef (2020-2026-04-18)   : {coef_oos:+.5f}  p={p_oos:.4f}  CI=[{ci_lo:+.5f}, {ci_hi:+.5f}]
  Attenuation                  : {atten:.3f} ({(1-atten)*100:.0f}% decay)
  Top-decile gap               : {gap_top:+.2f} pp gross / {net_top:+.2f} pp net of vig
  Spec curve (% positive)      : {pos_share:.0%}
  Spec curve (% sig at p<.05)  : {sig_share:.0%}

Three-criterion verdict:
  (i)  OOS sign replicated : {'YES' if coef_is * coef_oos > 0 else 'NO'}
  (ii) OOS CI excl. zero   : {'YES' if (ci_lo > 0 or ci_hi < 0) else 'NO'}
  (iii) P&L CI excl. zero  : NO (see Step 4)
""")
print('Do not call anything tradeable if bootstrap CI includes zero.')
print('Done.')
