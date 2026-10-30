"""
run_four_checks.py
==================
(a) Interaction regression: sapm_r_opp, post2020, sapm_r_opp x post2020
(b) Rolling 3-year window coefficients for sapm_r_opp
(c) Romano-Wolf univariate over 41 candidates, 5000 draws
(d) OOS 2020+ flagship vs non-flagship interaction
"""
import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
import patsy
from pathlib import Path

SEED   = 42
N_PERM = 5_000
rng    = np.random.default_rng(SEED)

BASE    = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis')
PANEL_P = BASE / 'preliminary results' / 'style_panel.csv'

STYLE_VARS = [
    'slpm_r','str_acc_r','dist_share_r','clinch_share_r','ground_share_r',
    'head_share_r','body_share_r','leg_share_r','kd_rate_r','td_per15_r',
    'td_acc_r','td_def_r','sub_per15_r','ctrl_share_r','sapm_r',
    'avg_fight_min_r','finish_rate_r',
]
ALL_ATOMIC  = STYLE_VARS + [v+'_opp' for v in STYLE_VARS]
COMPOSITES  = ['td_edge','anti_td_edge','drag_down','pace_durability',
               'ctrl_scramble','ground_exploit','ko_power_chin']
CANDIDATES  = ALL_ATOMIC + COMPOSITES   # 41
CONTROLS    = 'glicko_z + age_at_fight + layoff_days_c + C(division) + C(year)'
MAIN_FORMULA= ('calibration_gap ~ ' + ' + '.join(ALL_ATOMIC) +
               ' + glicko_z + age_at_fight + layoff_days_c + C(division) + C(year)')

# ── Load & build panel ────────────────────────────────────────────────────────
panel = pd.read_csv(PANEL_P, low_memory=False, parse_dates=['date'])
panel['year']          = panel['date'].dt.year
panel['layoff_days_c'] = panel['layoff_days'].clip(0, 365*2)
panel['post2020']      = (panel['year'] >= 2020).astype(float)

opp_join = (panel[['fight_id','fighter_id']+STYLE_VARS]
            .rename(columns={'fighter_id':'opponent_id',
                             **{v:v+'_opp' for v in STYLE_VARS}}))
panel = panel.merge(opp_join, on=['fight_id','opponent_id'], how='left')

# Flagship: numbered UFC PPV events (e.g. "UFC 300") vs Fight Night
links = pd.read_csv(BASE / 'ufcstats_raw' / 'fight_links.csv')
links['fight_id'] = links['fight_url'].str.split('/').str[-1]
import re
links['flagship'] = links['event_name'].apply(
    lambda x: 1.0 if re.match(r'^UFC\s+\d+', str(x)) else 0.0)
panel = panel.merge(links[['fight_id','flagship','event_name']]
                    .drop_duplicates('fight_id'), on='fight_id', how='left')

req = (ALL_ATOMIC + COMPOSITES +
       ['calibration_gap','glicko_z','age_at_fight','layoff_days_c',
        'division','year','fighter_id','post2020','flagship','won'])
est = panel[[c for c in req if c in panel.columns]].dropna(
      subset=ALL_ATOMIC+['calibration_gap','glicko_z','age_at_fight','layoff_days_c']).copy()

print(f'Estimation sample: N={len(est):,}  '
      f'({panel["date"].min().date()} – {panel["date"].max().date()})\n')

# ── Helper: clustered OLS ─────────────────────────────────────────────────────
def cluster_ols(df, formula, var, group='fighter_id'):
    try:
        dummy = df.iloc[[0]].assign(division='other', calibration_gap=0.0)
        aug   = pd.concat([df, dummy], ignore_index=True)
        dp    = len(aug)-1
        lhs_a, rhs_a = patsy.dmatrices(formula, data=aug, return_type='dataframe')
        real  = lhs_a.index != dp
        lhs   = lhs_a[real]; rhs = rhs_a[real]
        mod   = sm.OLS(lhs.iloc[:,0], rhs).fit(
                    cov_type='cluster', cov_kwds={'groups': aug.loc[lhs.index, group]})
        if var in mod.params.index:
            return mod.params[var], mod.bse[var], mod.pvalues[var]
        return None, None, None
    except Exception as e:
        return None, None, None

def fmt(c, se, p):
    if c is None: return 'NOT AVAILABLE'
    return f'coef={c:+.5f}  SE={se:.5f}  p={p:.4f}'

# ═══════════════════════════════════════════════════════════════════════════════
print('='*70)
print('(a) INTERACTION REGRESSION: sapm_r_opp × post2020')
print('='*70)
f_int = (MAIN_FORMULA
         .replace('calibration_gap ~ ',
                  'calibration_gap ~ post2020 + sapm_r_opp:post2020 + '))
# Build explicit interaction term
est['sapm_x_post'] = est['sapm_r_opp'] * est['post2020']
f_int2 = (MAIN_FORMULA + ' + post2020 + sapm_x_post')

c1,se1,p1 = cluster_ols(est, f_int2, 'sapm_r_opp')
c2,se2,p2 = cluster_ols(est, f_int2, 'post2020')
c3,se3,p3 = cluster_ols(est, f_int2, 'sapm_x_post')

print(f'sapm_r_opp (baseline IS effect):   {fmt(c1,se1,p1)}')
print(f'post2020 (level shift):             {fmt(c2,se2,p2)}')
print(f'sapm_r_opp x post2020 (extra OOS): {fmt(c3,se3,p3)}')

# ═══════════════════════════════════════════════════════════════════════════════
print()
print('='*70)
print('(b) ROLLING 3-YEAR WINDOWS: sapm_r_opp coef and p')
print('='*70)
print(f'{"Start yr":<10} {"End yr":<8} {"N":>6}  {"Coef":>9}  {"p":>7}')
print('-'*45)
for start in range(2008, 2024):
    end  = start + 2
    sub  = est[est['year'].between(start, end)].copy()
    if len(sub) < 100:
        print(f'{start:<10} {end:<8} {len(sub):>6}  {"NOT AVAILABLE":>9}')
        continue
    c,se,p = cluster_ols(sub, MAIN_FORMULA, 'sapm_r_opp')
    if c is None:
        print(f'{start:<10} {end:<8} {len(sub):>6}  NOT AVAILABLE')
    else:
        sig = '***' if p<0.001 else ('**' if p<0.01 else ('*' if p<0.05 else ''))
        print(f'{start:<10} {end:<8} {len(sub):>6}  {c:>+9.5f}  {p:>7.4f} {sig}')

# ═══════════════════════════════════════════════════════════════════════════════
print()
print('='*70)
print('(c) ROMANO-WOLF UNIVARIATE OVER 41 CANDIDATES (5,000 permutations)')
print('='*70)

# Build dummies once
est_rw = est.copy()
est_rw = pd.get_dummies(est_rw, columns=['division','year'], drop_first=True, dtype=float)
ctrl_cols = (['glicko_z','age_at_fight','layoff_days_c'] +
             [c for c in est_rw.columns if c.startswith('division_') or c.startswith('year_')])

y = est_rw['calibration_gap'].values
ctrl_arr = est_rw[[c for c in ctrl_cols if c in est_rw.columns]].values

# Univariate t-stats (clustered for observed; plain OLS for permutations)
cands_present = [c for c in CANDIDATES if c in est_rw.columns]
t_obs  = {}
coefs  = {}
pvals  = {}
groups = est_rw['fighter_id'].values

for cand in cands_present:
    xc  = est_rw[cand].values.reshape(-1,1)
    Xc  = sm.add_constant(np.hstack([xc, ctrl_arr]))
    try:
        res = sm.OLS(y, Xc).fit(cov_type='cluster', cov_kwds={'groups': groups})
        t_obs[cand]  = abs(res.tvalues[1])
        coefs[cand]  = res.params[1]
        pvals[cand]  = res.pvalues[1]
    except Exception:
        pass

# Permutation null (plain OLS for speed)
K      = len(t_obs)
order  = sorted(t_obs, key=lambda c: -t_obs[c])
t_sort = np.array([t_obs[c] for c in order])

X_mats = {}
for cand in order:
    xc = est_rw[cand].values.reshape(-1,1)
    Xc = sm.add_constant(np.hstack([xc, ctrl_arr]))
    try:
        XtXi = np.linalg.pinv(Xc.T @ Xc)
        X_mats[cand] = (Xc, XtXi)
    except Exception:
        pass

null_max = np.zeros((N_PERM, K))
for b in range(N_PERM):
    yp    = rng.permutation(y)
    tp    = np.zeros(K)
    for ki, cand in enumerate(order):
        if cand not in X_mats: continue
        Xc, XtXi = X_mats[cand]
        beta  = XtXi @ Xc.T @ yp
        resid = yp - Xc @ beta
        s2    = np.dot(resid,resid) / max(len(yp)-Xc.shape[1],1)
        se_   = np.sqrt(max(s2 * XtXi[1,1], 0))
        tp[ki]= abs(beta[1]/se_) if se_>0 else 0
    for ki in range(K-2,-1,-1):
        tp[ki] = max(tp[ki], tp[ki+1])
    null_max[b] = tp
    if (b+1) % 1000 == 0:
        print(f'  permutation {b+1}/{N_PERM}')

rw_p = np.zeros(K)
for ki in range(K):
    rw_p[ki] = (null_max[:,ki] >= t_sort[ki]).mean()
for ki in range(1,K):
    rw_p[ki] = max(rw_p[ki], rw_p[ki-1])

print(f'\n{"Rank":<5} {"Variable":<30} {"Coef":>9} {"Naive p":>9} {"RW p":>9}')
print('-'*65)
for ki, cand in enumerate(order[:15]):
    print(f'{ki+1:<5} {cand:<30} {coefs[cand]:>+9.5f} {pvals[cand]:>9.4f} {rw_p[ki]:>9.4f}')

sapm_rank = order.index('sapm_r_opp')+1 if 'sapm_r_opp' in order else None
sapm_ki   = order.index('sapm_r_opp')   if 'sapm_r_opp' in order else None
age_rank  = order.index('age_at_fight') if 'age_at_fight' in order else None

print(f'\nsapm_r_opp  : rank {sapm_rank}/{K}  '
      f'naive p={pvals.get("sapm_r_opp","NOT AVAILABLE"):.4f}  '
      f'RW p={rw_p[sapm_ki]:.4f}' if sapm_rank else 'sapm_r_opp: NOT AVAILABLE')

# age_at_fight full-sample (clustered)
ca,sea,pa = cluster_ols(est, MAIN_FORMULA+' + age_at_fight'
            if 'age_at_fight' not in MAIN_FORMULA else MAIN_FORMULA, 'age_at_fight')
print(f'age_at_fight: {fmt(ca,sea,pa)}')

# ═══════════════════════════════════════════════════════════════════════════════
print()
print('='*70)
print('(d) OOS 2020+ FLAGSHIP INTERACTION')
print('='*70)

oos = est[est['year'] >= 2020].copy()
if 'flagship' not in oos.columns or oos['flagship'].isna().all():
    print('flagship: NOT AVAILABLE')
else:
    oos['flagship'] = oos['flagship'].fillna(0)
    oos['sapm_x_flagship'] = oos['sapm_r_opp'] * oos['flagship']
    n_flag    = int(oos['flagship'].sum())
    n_nonflag = int((oos['flagship']==0).sum())
    print(f'N flagship={n_flag}  N non-flagship={n_nonflag}  N total OOS={len(oos)}')

    f_flag = MAIN_FORMULA + ' + flagship + sapm_x_flagship'
    cf,sef,pf   = cluster_ols(oos, f_flag, 'sapm_r_opp')
    cf2,sef2,pf2= cluster_ols(oos, f_flag, 'flagship')
    cf3,sef3,pf3= cluster_ols(oos, f_flag, 'sapm_x_flagship')
    print(f'sapm_r_opp (non-flagship baseline): {fmt(cf,sef,pf)}')
    print(f'flagship (level shift):             {fmt(cf2,sef2,pf2)}')
    print(f'sapm_r_opp x flagship (extra):      {fmt(cf3,sef3,pf3)}')
