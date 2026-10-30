"""
age_at_fight_analysis.py  (v1)
==============================
Four-part investigation of age_at_fight as a market inefficiency signal.

STEP 1 — Romano-Wolf FWER over the fighter-state family (3 vars):
          age_at_fight, layoff_days_c, glicko_z.
STEP 2 — Linearity: (a) quadratic age term; (b) age-bin dummies.
STEP 3 — Frozen temporal holdout: fit ≤2019, apply 2020–2026-04-18.
          Reports IS vs OOS coefficients, attenuation, and calibration
          gap by age decile in the OOS window.
STEP 4 — Economic significance: bootstrap P&L (10,000 resamples) for
          fading top-decile oldest fighters in OOS, actual closing odds.
BONUS  — Interaction: age_at_fight × sapm_r_opp (both centred).

Controls throughout: ALL_ATOMIC style vars + glicko_z + layoff_days_c
  + C(division) + C(year).  Cluster SE by fighter_id.
Data: style_panel.csv  (2008-06-21 – 2026-04-18)
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

# ── 0. Load & build panel ──────────────────────────────────────────────────
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

print(f'Panel: N={len(panel_est):,}  '
      f'({panel_est["date"].min().date()} – {panel_est["date"].max().date()})')
print(f'Train: N={len(train):,}   Test: N={len(test):,}')

# ── Helpers ────────────────────────────────────────────────────────────────
def stars(p):
    if p < 0.001: return '***'
    if p < 0.010: return '**'
    if p < 0.050: return '*'
    if p < 0.100: return '.'
    return ''

def build_design(formula, data):
    dummy_row = data.iloc[[0]].assign(division='other', calibration_gap=0.0)
    aug       = pd.concat([data, dummy_row], ignore_index=True)
    dpos      = len(aug) - 1
    lhs_a, rhs_a = patsy.dmatrices(formula, data=aug, return_type='dataframe')
    mask = lhs_a.index != dpos
    return lhs_a[mask], rhs_a[mask], aug

def fit_cluster(lhs, rhs, groups):
    return sm.OLS(lhs.iloc[:, 0], rhs).fit(
        cov_type='cluster', cov_kwds={'groups': groups})

def align_design(formula, data, ref_cols):
    _, rhs = patsy.dmatrices(formula, data=data, return_type='dataframe')
    out = pd.DataFrame(index=rhs.index)
    for col in ref_cols:
        out[col] = rhs[col].values if col in rhs.columns else 0.0
    return out

def remap_division(d, train_divs):
    if d in train_divs: return d
    if isinstance(d, str) and d.strip().lower() in UFC_WEIGHT_CLASSES: return d
    return 'other'

def net_return(df, won_col='won', odds_col='dec_odds'):
    return np.where(df[won_col].values == 1, df[odds_col].values - 1.0, -1.0)

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

def rw_stepdown(y, X, n, k, cand_idx, cand_names, obs_t):
    XtX_inv = np.linalg.pinv(X.T @ X)
    perm_t  = np.empty((N_PERM, len(cand_idx)))
    for b in range(N_PERM):
        y_p      = rng.permutation(y)
        beta_p   = XtX_inv @ (X.T @ y_p)
        resid_p  = y_p - X @ beta_p
        sigma2_p = (resid_p @ resid_p) / (n - k)
        var_p    = sigma2_p * np.diag(XtX_inv)
        t_p      = np.abs(beta_p / np.sqrt(np.maximum(var_p, 1e-12)))
        perm_t[b] = t_p[cand_idx]
    order      = np.argsort(-obs_t)
    ord_t      = obs_t[order]
    ord_names  = [cand_names[i] for i in order]
    perm_ord   = perm_t[:, order]
    rw_p       = np.empty(len(cand_idx))
    for step in range(len(cand_idx)):
        rw_p[step] = (perm_ord[:, step:].max(axis=1) >= ord_t[step]).mean()
    for step in range(1, len(cand_idx)):
        rw_p[step] = max(rw_p[step], rw_p[step - 1])
    return ord_names, ord_t, rw_p

# ── STEP 1 — Romano-Wolf: fighter-state family ────────────────────────────
print('\n' + '='*70)
print('STEP 1 — Romano-Wolf: fighter-state family (age, layoff, glicko) [3 vars]')
print('='*70)

STATE_VARS = ['age_at_fight', 'layoff_days_c', 'glicko_z']

lhs_s, rhs_s, aug_s = build_design(FORMULA, panel_est)
y_s   = lhs_s.iloc[:, 0].values
X_s   = rhs_s.values
n_s, k_s = X_s.shape
grp_s = aug_s.loc[lhs_s.index, 'fighter_id'].values
mod_s = fit_cluster(lhs_s, rhs_s, grp_s)

s_idx   = [rhs_s.columns.get_loc(v) for v in STATE_VARS if v in rhs_s.columns]
s_names = [rhs_s.columns[i] for i in s_idx]
obs_t_s = np.abs(np.array(mod_s.tvalues)[s_idx])

print(f'Running RW ({N_PERM:,} permutations)...')
ord_names_s, ord_t_s, rw_p_s = rw_stepdown(y_s, X_s, n_s, k_s, s_idx, s_names, obs_t_s)

print(f'\n{"Variable":<20} {"Obs |t|":>8} {"Naive p":>10} {"RW p":>10} {"Sig":>5}')
print('-'*58)
for step in range(len(s_idx)):
    name    = ord_names_s[step]
    naive_p = np.array(mod_s.pvalues)[rhs_s.columns.get_loc(name)]
    print(f'{name:<20} {ord_t_s[step]:>8.3f} {naive_p:>10.4f} {rw_p_s[step]:>10.4f} '
          f'{stars(rw_p_s[step]):>5}')

# ── STEP 2 — Linearity ────────────────────────────────────────────────────
print('\n' + '='*70)
print('STEP 2 — Linearity check')
print('='*70)

# 2a. Quadratic
print('\n--- 2a. Quadratic age term ---')
panel_est['age2'] = panel_est['age_at_fight'] ** 2
FORMULA_Q = FORMULA.replace('+ age_at_fight', '+ age_at_fight + age2')

lhs_q, rhs_q, aug_q = build_design(FORMULA_Q, panel_est)
grp_q = aug_q.loc[lhs_q.index, 'fighter_id'].values
mod_q = fit_cluster(lhs_q, rhs_q, grp_q)

for var in ['age_at_fight', 'age2']:
    if var in mod_q.params.index:
        c, p = mod_q.params[var], mod_q.pvalues[var]
        print(f'  {var:<20}  coef={c:+.6f}  p={p:.4f}  {stars(p)}')

if 'age_at_fight' in mod_q.params.index and 'age2' in mod_q.params.index:
    b1, b2 = mod_q.params['age_at_fight'], mod_q.params['age2']
    print(f'\n  Marginal effect (d calibration_gap / d age) at selected ages:')
    for age in [25, 28, 31, 34, 37, 40]:
        me = b1 + 2 * b2 * age
        print(f'    Age {age}: {me:+.5f}')

# 2b. Age-bin dummies
print('\n--- 2b. Age-bin dummies (reference: 28–30, approximate prime) ---')
bins   = [0, 27, 30, 33, 36, 100]
labels = ['le27', 'a28to30', 'a31to33', 'a34to36', 'ge37']
panel_est['age_bin'] = pd.cut(
    panel_est['age_at_fight'], bins=bins, labels=labels, right=True)

FORMULA_BIN = ('calibration_gap ~ '
               + ' + '.join(ALL_ATOMIC)
               + ' + C(age_bin, Treatment("a28to30"))'
               + ' + glicko_z + layoff_days_c'
               + ' + C(division) + C(year)')

lhs_b, rhs_b, aug_b = build_design(FORMULA_BIN, panel_est)
grp_b = aug_b.loc[lhs_b.index, 'fighter_id'].values
mod_b = fit_cluster(lhs_b, rhs_b, grp_b)

bin_label_map = {
    'le27':    '≤27',
    'a31to33': '31–33',
    'a34to36': '34–36',
    'ge37':    '≥37',
}
bin_vars = [c for c in mod_b.params.index if 'age_bin' in c]
print(f'  {"Bin vs 28–30":<40} {"Coef":>10} {"p":>8} {"Sig":>5}')
print('  ' + '-'*67)
for v in bin_vars:
    c, p = mod_b.params[v], mod_b.pvalues[v]
    short = v.split('[T.')[-1].rstrip(']') if '[T.' in v else v
    label = bin_label_map.get(short, short)
    print(f'  {label:<40} {c:>+10.5f} {p:>8.4f} {stars(p):>5}')

# ── STEP 3 — Frozen holdout ───────────────────────────────────────────────
print('\n' + '='*70)
print('STEP 3 — Frozen temporal holdout (train ≤2019 → test 2020–2026-04-18)')
print('='*70)

train_divs = set(train['division'].dropna().unique())

dummy_tr  = train.iloc[[0]].assign(division='other', calibration_gap=0.0)
train_aug = pd.concat([train, dummy_tr], ignore_index=True)
dpos_tr   = len(train_aug) - 1

lhs_tr_a, rhs_tr_a = patsy.dmatrices(FORMULA, data=train_aug, return_type='dataframe')
mask_tr = lhs_tr_a.index != dpos_tr
lhs_tr  = lhs_tr_a[mask_tr]
rhs_tr  = rhs_tr_a[mask_tr]
mod_is  = fit_cluster(lhs_tr, rhs_tr, train_aug.loc[lhs_tr.index, 'fighter_id'].values)

age_is = mod_is.params.get('age_at_fight', np.nan)
p_is   = mod_is.pvalues.get('age_at_fight', np.nan)
print(f'\nIS  age_at_fight: coef={age_is:+.6f}  p={p_is:.4f}  (N={len(lhs_tr):,})')

test_rem = test.copy()
test_rem['division'] = test_rem['division'].apply(
    lambda d: remap_division(d, train_divs))
rhs_te       = align_design(FORMULA, test_rem, ref_cols=rhs_tr.columns)
test_scored  = test_rem.loc[rhs_te.index].copy()
test_scored['frozen_pred'] = mod_is.predict(rhs_te).values

lhs_oos, rhs_oos = patsy.dmatrices(FORMULA, data=test_rem, return_type='dataframe')
mod_oos = fit_cluster(lhs_oos, rhs_oos, test_rem.loc[lhs_oos.index, 'fighter_id'].values)

age_oos = mod_oos.params.get('age_at_fight', np.nan)
se_oos  = mod_oos.bse.get('age_at_fight', np.nan)
p_oos   = mod_oos.pvalues.get('age_at_fight', np.nan)
ci_oos  = mod_oos.conf_int().loc['age_at_fight']
atten   = age_oos / age_is if age_is != 0 else np.nan

print(f'OOS age_at_fight: coef={age_oos:+.6f}  SE={se_oos:.6f}  p={p_oos:.4f}  '
      f'CI=[{ci_oos[0]:+.6f}, {ci_oos[1]:+.6f}]')
print(f'Attenuation (OOS/IS): {atten:.3f}  ({(1-atten)*100:.0f}% decay)')

# Calibration gap by age decile (OOS)
test_scored['age_decile'] = pd.qcut(
    test_scored['age_at_fight'], 10, labels=False, duplicates='drop') + 1
decile_tbl = (test_scored.groupby('age_decile', observed=True)
              .agg(n=('won','count'),
                   avg_age=('age_at_fight','mean'),
                   cal_gap=('calibration_gap','mean'))
              .reset_index())

print(f'\nCalibration gap by age decile (OOS) — decile 1 = youngest:')
print(f'  {"Decile":>6} {"Avg Age":>8} {"N":>5} {"Cal Gap":>10}')
print('  ' + '-'*35)
for _, row in decile_tbl.iterrows():
    print(f'  {int(row["age_decile"]):>6} {row["avg_age"]:>8.1f} '
          f'{int(row["n"]):>5} {row["cal_gap"]:>+10.4f}')

# ── STEP 4 — Economic significance ────────────────────────────────────────
print('\n' + '='*70)
print('STEP 4 — P&L bootstrap: fading top-decile oldest fighters (OOS)')
print('='*70)

# Use full panel_est for OOS to get fight_id / opponent_id
oos_all = panel_est[panel_est['year'] >= 2020].copy()
oos_all['dec_odds'] = 1.0 / oos_all['q_close']

age_thresh  = oos_all['age_at_fight'].quantile(0.90)
old_ids     = set(oos_all.loc[oos_all['age_at_fight'] >= age_thresh, 'fighter_id'])
old_fights  = set(oos_all.loc[oos_all['age_at_fight'] >= age_thresh, 'fight_id'])

# Opponent rows: same fight_id, fighter not in old_ids
fade_bets = oos_all[
    oos_all['fight_id'].isin(old_fights) &
    ~oos_all['fighter_id'].isin(old_ids)
].copy()

print(f'\nAge threshold (90th pct OOS): {age_thresh:.1f} years')
print(f'Unique old fighters          : {len(old_ids):,}')
print(f'Fade bets available          : {len(fade_bets):,}')
print(f'Win rate (fade bets)         : {fade_bets["won"].mean()*100:.1f}%')
print(f'Avg market prob (fade side)  : {fade_bets["market_prob_shin"].mean()*100:.1f}%')
print(f'Cal gap (fade side)          : {fade_bets["calibration_gap"].mean()*100:+.2f} pp')

r = net_return(fade_bets)
edge, lo, hi, pval = boot_ci(r)
print(f'\nFade strategy — bet on opponent of top-decile-oldest fighter:')
print(f'  Net edge    : {edge:+.2f} pp')
print(f'  95% boot CI : [{lo:+.2f}, {hi:+.2f}] pp')
print(f'  Bootstrap p : {pval:.3f}')
print(f'  Clears zero : {"YES" if lo > 0 else "NO (CI crosses 0)"}')
print(f'  Beats 2pp vig: {"YES" if lo > VIG*100 else "NO"}')

# ── BONUS — Interaction: age × sapm_r_opp ────────────────────────────────
print('\n' + '='*70)
print('BONUS — Interaction: age_at_fight × sapm_r_opp (both centred on training mean)')
print('='*70)

age_mean      = train['age_at_fight'].mean()
sapm_opp_mean = train['sapm_r_opp'].mean()

panel_est['age_c']       = panel_est['age_at_fight'] - age_mean
panel_est['sapm_opp_c']  = panel_est['sapm_r_opp']  - sapm_opp_mean
panel_est['age_x_sapm']  = panel_est['age_c'] * panel_est['sapm_opp_c']

FORMULA_INT = FORMULA + ' + age_x_sapm'

lhs_i, rhs_i, aug_i = build_design(FORMULA_INT, panel_est)
grp_i = aug_i.loc[lhs_i.index, 'fighter_id'].values
mod_i = fit_cluster(lhs_i, rhs_i, grp_i)

print(f'\nCentred at training means:  age={age_mean:.2f}  sapm_r_opp={sapm_opp_mean:.4f}')
print(f'\n{"Variable":<20} {"Coef":>12} {"SE":>10} {"t":>7} {"p":>8} {"Sig":>5}')
print('-'*67)
for var in ['age_at_fight', 'sapm_r_opp', 'age_x_sapm']:
    if var in mod_i.params.index:
        c  = mod_i.params[var]
        se = mod_i.bse[var]
        t  = mod_i.tvalues[var]
        p  = mod_i.pvalues[var]
        print(f'{var:<20} {c:>+12.6f} {se:>10.6f} {t:>7.3f} {p:>8.4f} {stars(p):>5}')

if 'age_x_sapm' in mod_i.params.index:
    b_int = mod_i.params['age_x_sapm']
    p_int = mod_i.pvalues['age_x_sapm']
    print(f'\nInteraction significant at p<0.05: {"YES" if p_int < 0.05 else "NO"}')
    if p_int < 0.05:
        print(f'A 1-unit increase in sapm_r_opp is worth {b_int:+.5f} extra '
              f'per year of age above the training mean ({age_mean:.1f}).')

print('\nDone.')
