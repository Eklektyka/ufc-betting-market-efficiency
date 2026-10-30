"""
run_clean_signal_battery.py
===========================
Constructs sapm_pre_r_opp (clean pre-fight signal) and runs locked battery.
"""
import sys, warnings, itertools, re
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
import patsy
from pathlib import Path

BASE    = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis')
SEED    = 42
N_RW    = 10_000
rng     = np.random.default_rng(SEED)

# ── 1. Build sapm_prefight from fight_totals_clean ────────────────────────────
ft = pd.read_csv(BASE / 'ufcstats_raw' / 'fight_totals_clean.csv', low_memory=False)
ft['date']       = pd.to_datetime(ft['date'], errors='coerce')
ft['fighter_id'] = ft['fighter_url'].str.split('/').str[-1]
ft['fight_id']   = ft['fight_url'].str.split('/').str[-1]

for col in ['sig_str_landed','sig_str_att','opp_sig_str_landed' if 'opp_sig_str_landed' in ft.columns else 'sig_str_landed']:
    ft[col] = pd.to_numeric(ft[col], errors='coerce')

# compute opp sig_str_landed via fight-level self-merge
opp_str = ft[['fight_url','fighter_url','sig_str_landed']].rename(
    columns={'fighter_url':'fighter_url_opp','sig_str_landed':'opp_sig_str_land'})
ft = ft.merge(opp_str, on=['fight_url','fighter_url_opp'], how='left')

def parse_time(t):
    try:
        p = str(t).split(':')
        return int(p[0]) + int(p[1])/60.0
    except: return np.nan

ft['round_num'] = pd.to_numeric(ft['round'], errors='coerce')
ft['time_min']  = ft['time'].apply(parse_time)
ft['fight_min'] = ((ft['round_num'] - 1) * 5.0 + ft['time_min']).clip(lower=0.1)

ft['sapm_fight'] = ft['opp_sig_str_land'] / ft['fight_min']
ft.loc[ft['sapm_fight'] > 50, 'sapm_fight'] = np.nan

# expanding pre-fight mean (shift 1 = excludes current fight)
ft = ft.sort_values(['fighter_id','date','fight_url']).reset_index(drop=True)
ft['sapm_cumean'] = (ft.groupby('fighter_id')['sapm_fight']
                       .expanding().mean()
                       .reset_index(level=0, drop=True))
ft['sapm_prefight'] = ft.groupby('fighter_id')['sapm_cumean'].shift(1)

ft_merge = ft[['fighter_id','date','sapm_prefight']].drop_duplicates(
    subset=['fighter_id','date'], keep='first')

# ── 2. Load panel, merge prefight sapm ───────────────────────────────────────
panel = pd.read_csv(BASE / 'preliminary results' / 'style_panel.csv',
                    low_memory=False, parse_dates=['date'])
panel['year']          = panel['date'].dt.year
panel['layoff_days_c'] = panel['layoff_days'].clip(0, 365*2)
panel['post2020']      = (panel['year'] >= 2020).astype(float)

panel = panel.merge(ft_merge, on=['fighter_id','date'], how='left')

# Verify: fraction of fighters with >1 distinct sapm_prefight
varying = panel.dropna(subset=['sapm_prefight']).groupby('fighter_id')['sapm_prefight'].nunique()
frac_varying = (varying > 1).mean()
print(f'Fraction of fighters with >1 distinct sapm_prefight: {frac_varying:.4f} '
      f'({(varying>1).sum()}/{len(varying)})')

# ── 3. Residualise: sapm_prefight ~ glicko_z + C(division) ──────────────────
panel['sapm_pre_r'] = np.nan
mask = panel['sapm_prefight'].notna() & panel['glicko_z'].notna() & panel['division'].notna()
if mask.sum() > 0:
    mod_g = smf.ols('sapm_prefight ~ glicko_z + C(division)', panel[mask]).fit()
    panel.loc[panel[mask].index, 'sapm_pre_r'] = mod_g.resid.values
# fallback: division only
mask2 = panel['sapm_pre_r'].isna() & panel['sapm_prefight'].notna() & panel['division'].notna()
if mask2.sum() > 0:
    mod_d = smf.ols('sapm_prefight ~ C(division)', panel[mask2]).fit()
    panel.loc[panel[mask2].index, 'sapm_pre_r'] = mod_d.resid.values

# ── 4. Build opponent-side sapm_pre_r_opp ───────────────────────────────────
opp_pre = panel[['fight_id','fighter_id','sapm_pre_r']].rename(
    columns={'fighter_id':'opponent_id','sapm_pre_r':'sapm_pre_r_opp'})
panel = panel.merge(opp_pre, on=['fight_id','opponent_id'], how='left')

# Also rebuild full opponent block for ALL_ATOMIC (needed for spec curve + RW-5)
STYLE_VARS = ['slpm_r','str_acc_r','dist_share_r','clinch_share_r','ground_share_r',
    'head_share_r','body_share_r','leg_share_r','kd_rate_r','td_per15_r',
    'td_acc_r','td_def_r','sub_per15_r','ctrl_share_r','sapm_r',
    'avg_fight_min_r','finish_rate_r']
opp_style = panel[['fight_id','fighter_id']+STYLE_VARS].rename(
    columns={'fighter_id':'opponent_id',**{v:v+'_opp' for v in STYLE_VARS}})
panel = panel.merge(opp_style, on=['fight_id','opponent_id'], how='left')

# ALL_ATOMIC with sapm_pre_r_opp replacing sapm_r_opp
ALL_ATOMIC_NEW = [v for v in STYLE_VARS if v != 'sapm_r'] + ['sapm_pre_r'] + \
                 [v+'_opp' for v in STYLE_VARS if v != 'sapm_r'] + ['sapm_pre_r_opp']

CONTROLS = 'glicko_z + age_at_fight + layoff_days_c + C(division) + C(year)'
FORMULA   = ('calibration_gap ~ ' + ' + '.join(ALL_ATOMIC_NEW) + ' + ' + CONTROLS)
DROP_CORE = ['sapm_pre_r_opp','calibration_gap','glicko_z','age_at_fight','layoff_days_c']

est = panel.dropna(subset=DROP_CORE).copy()

# ── Helper ────────────────────────────────────────────────────────────────────
def cluster_ols(df, formula, var, group='fighter_id'):
    try:
        dummy = df.iloc[[0]].assign(division='other', calibration_gap=0.0)
        aug   = pd.concat([df, dummy], ignore_index=True)
        dp    = len(aug) - 1
        lhs_a, rhs_a = patsy.dmatrices(formula, data=aug, return_type='dataframe')
        real  = lhs_a.index != dp
        lhs   = lhs_a[real]; rhs = rhs_a[real]
        mod   = sm.OLS(lhs.iloc[:,0], rhs).fit(
                    cov_type='cluster', cov_kwds={'groups': aug.loc[lhs.index, group]})
        if var not in mod.params.index:
            return None, None, None, None
        return mod.params[var], mod.bse[var], mod.pvalues[var], len(lhs)
    except:
        return None, None, None, None

def fmt(c, se, p, n=None):
    if c is None: return 'NOT AVAILABLE'
    s = f'coef={c:+.5f}  SE={se:.5f}  p={p:.4f}'
    if n: s += f'  N={n:,}'
    return s

print()
print('='*70)
print('(1) FULL SAMPLE')
print('='*70)
c,se,p,n = cluster_ols(est, FORMULA, 'sapm_pre_r_opp')
print(fmt(c,se,p,n))

print()
print('='*70)
print('(2) IS <=2019 and OOS 2020+')
print('='*70)
is_ = est[est['year'] <= 2019]
c_is,se_is,p_is,n_is = cluster_ols(is_, FORMULA, 'sapm_pre_r_opp')
print(f'IS:  {fmt(c_is,se_is,p_is,n_is)}')

oos = est[est['year'] >= 2020]
c_oo,se_oo,p_oo,n_oo = cluster_ols(oos, FORMULA, 'sapm_pre_r_opp')
print(f'OOS: {fmt(c_oo,se_oo,p_oo,n_oo)}')
if c_oo is not None:
    ci_lo = c_oo - 1.96*se_oo; ci_hi = c_oo + 1.96*se_oo
    print(f'OOS 95% CI: [{ci_lo:+.5f}, {ci_hi:+.5f}]')

print()
print('='*70)
print('(3) INTERACTION: sapm_pre_r_opp x post2020')
print('='*70)
est['sapm_pre_x_post'] = est['sapm_pre_r_opp'] * est['post2020']
f_int = FORMULA + ' + post2020 + sapm_pre_x_post'
c1,se1,p1,_ = cluster_ols(est, f_int, 'sapm_pre_r_opp')
c2,se2,p2,_ = cluster_ols(est, f_int, 'post2020')
c3,se3,p3,_ = cluster_ols(est, f_int, 'sapm_pre_x_post')
print(f'sapm_pre_r_opp (baseline):        {fmt(c1,se1,p1)}')
print(f'post2020 (level shift):            {fmt(c2,se2,p2)}')
print(f'sapm_pre_r_opp x post2020 (extra):{fmt(c3,se3,p3)}')

print()
print('='*70)
print('(4) ROLLING 3-YEAR WINDOWS')
print('='*70)
print(f'{"Start":<7} {"End":<5} {"N":>5}  {"Coef":>9}  {"p":>7}')
for start in range(2008, 2024):
    end = start + 2
    sub = est[est['year'].between(start, end)].copy()
    if len(sub) < 80:
        print(f'{start:<7} {end:<5} {len(sub):>5}  NOT AVAILABLE')
        continue
    c,se,p,n = cluster_ols(sub, FORMULA, 'sapm_pre_r_opp')
    if c is None:
        print(f'{start:<7} {end:<5} {len(sub):>5}  NOT AVAILABLE')
    else:
        sig = '***' if p<0.001 else ('**' if p<0.01 else ('*' if p<0.05 else ''))
        print(f'{start:<7} {end:<5} {len(sub):>5}  {c:>+9.5f}  {p:>7.4f} {sig}')

print()
print('='*70)
print(f'(5) RW-5 JOINT ({N_RW:,} permutations)')
print('='*70)
RW_VARS = ['sapm_pre_r_opp', 'sapm_pre_r', 'age_at_fight', 'slpm_r', 'slpm_r_opp']
rw_candidates = [v for v in RW_VARS if v in est.columns]

try:
    dummy_rw = est.iloc[[0]].assign(division='other', calibration_gap=0.0)
    aug_rw   = pd.concat([est, dummy_rw], ignore_index=True)
    dp_rw    = len(aug_rw) - 1
    lhs_rw, rhs_rw = patsy.dmatrices(FORMULA, data=aug_rw, return_type='dataframe')
    real_rw  = lhs_rw.index != dp_rw
    lhs_rw   = lhs_rw[real_rw]; rhs_rw = rhs_rw[real_rw]
    mod_full = sm.OLS(lhs_rw.iloc[:,0], rhs_rw).fit(
                   cov_type='cluster', cov_kwds={'groups': aug_rw.loc[lhs_rw.index, 'fighter_id']})

    obs_t    = np.array([abs(mod_full.tvalues[v]) for v in rw_candidates if v in mod_full.tvalues])
    rw_cands = [v for v in rw_candidates if v in mod_full.tvalues]
    order    = np.argsort(-obs_t)
    t_sorted = obs_t[order]
    cands_sorted = [rw_cands[i] for i in order]

    var_idx  = [list(rhs_rw.columns).index(v) for v in rw_cands]
    X_rw     = rhs_rw.values
    y_rw     = lhs_rw.iloc[:,0].values
    XtXi     = np.linalg.pinv(X_rw.T @ X_rw)
    K        = len(rw_cands)

    perm_t = np.empty((N_RW, K))
    for b in range(N_RW):
        yp   = rng.permutation(y_rw)
        beta = XtXi @ X_rw.T @ yp
        resid= yp - X_rw @ beta
        s2   = np.dot(resid,resid) / max(len(yp)-X_rw.shape[1], 1)
        se_v = np.sqrt(np.maximum(s2 * np.diag(XtXi), 0))
        tp   = np.array([abs(beta[vi]/se_v[vi]) if se_v[vi]>0 else 0 for vi in var_idx])
        tp_sorted = tp[order]
        for ki in range(K-2,-1,-1):
            tp_sorted[ki] = max(tp_sorted[ki], tp_sorted[ki+1])
        perm_t[b] = tp_sorted
        if (b+1) % 2000 == 0:
            print(f'  RW perm {b+1}/{N_RW}')

    rw_p = np.array([(perm_t[:,ki] >= t_sorted[ki]).mean() for ki in range(K)])
    for ki in range(1,K):
        rw_p[ki] = max(rw_p[ki], rw_p[ki-1])

    print(f'{"Rank":<5} {"Variable":<25} {"Obs|t|":>8} {"RW p":>8}')
    for ki, v in enumerate(cands_sorted):
        print(f'{ki+1:<5} {v:<25} {t_sorted[ki]:>8.3f} {rw_p[ki]:>8.4f}')

    sapm_rank = cands_sorted.index('sapm_pre_r_opp') + 1 if 'sapm_pre_r_opp' in cands_sorted else None
    sapm_ki   = cands_sorted.index('sapm_pre_r_opp') if 'sapm_pre_r_opp' in cands_sorted else None
    if sapm_rank:
        print(f'\nsapm_pre_r_opp: rank {sapm_rank}/{K}  RW p={rw_p[sapm_ki]:.4f}')
    else:
        print('sapm_pre_r_opp: NOT AVAILABLE')
except Exception as e:
    print(f'NOT AVAILABLE ({e})')

print()
print('='*70)
print('(6) SPEC CURVE (288 designs)')
print('='*70)
ctrl_options = list(itertools.product(
    [True,False],[True,False],[True,False],[True,False],[True,False]))
year_starts = [2007,2010,2012]
div_drops   = [None,'Heavyweight','Lightweight']

results_spec = []
for (use_age,use_layoff,use_glicko,use_div,use_year), yr_start, div_drop in itertools.product(
        ctrl_options, year_starts, div_drops):
    ctrl_parts = []
    if use_glicko:  ctrl_parts.append('glicko_z')
    if use_age:     ctrl_parts.append('age_at_fight')
    if use_layoff:  ctrl_parts.append('layoff_days_c')
    if use_div:     ctrl_parts.append('C(division)')
    if use_year:    ctrl_parts.append('C(year)')
    f_s = ('calibration_gap ~ ' + ' + '.join(ALL_ATOMIC_NEW) +
           ((' + ' + ' + '.join(ctrl_parts)) if ctrl_parts else ''))
    samp = est[est['year'] >= yr_start].copy()
    if div_drop: samp = samp[samp['division'] != div_drop]
    if len(samp) < 100: continue
    try:
        dummy_s = samp.iloc[[0]].assign(division='other', calibration_gap=0.0)
        aug_s   = pd.concat([samp, dummy_s], ignore_index=True)
        dp_s    = len(aug_s)-1
        lh_s, rh_s = patsy.dmatrices(f_s, data=aug_s, return_type='dataframe')
        real_s  = lh_s.index != dp_s
        mod_s   = sm.OLS(lh_s[real_s].iloc[:,0], rh_s[real_s]).fit(
                      cov_type='cluster',
                      cov_kwds={'groups': aug_s.loc[lh_s[real_s].index,'fighter_id']})
        if 'sapm_pre_r_opp' in mod_s.params:
            results_spec.append({'coef': mod_s.params['sapm_pre_r_opp'],
                                  'p':   mod_s.pvalues['sapm_pre_r_opp']})
    except: continue

specs_df = pd.DataFrame(results_spec)
if len(specs_df):
    print(f'Specs run: {len(specs_df)}')
    print(f'% positive:     {(specs_df["coef"]>0).mean()*100:.1f}%')
    print(f'% significant:  {(specs_df["p"]<0.05).mean()*100:.1f}%')
    print(f'Coef range:     [{specs_df["coef"].min():+.5f}, {specs_df["coef"].max():+.5f}]')
    print(f'Median coef:    {specs_df["coef"].median():+.5f}')
else:
    print('NOT AVAILABLE')

print()
print('='*70)
print('(7) MZ LOGIT OFFSET')
print('='*70)
try:
    mz = est[est['market_prob_shin'].notna() & est['won'].notna()].copy()
    mz['logit_mkt'] = np.log(mz['market_prob_shin'].clip(0.01,0.99) /
                             (1 - mz['market_prob_shin'].clip(0.01,0.99)))
    lhs_mz, rhs_mz = patsy.dmatrices(
        'won ~ sapm_pre_r_opp + age_at_fight + glicko_z + layoff_days_c + C(division) + C(year)',
        data=mz, return_type='dataframe')
    offset_mz = mz.loc[lhs_mz.index, 'logit_mkt'].values
    mod_mz = sm.Logit(lhs_mz.iloc[:,0], rhs_mz).fit_regularized(
        method='l1', alpha=0, disp=False)
    # Use regular Logit with offset via exog_extra
    import statsmodels.discrete.discrete_model as disc
    mod_mz2 = sm.Logit(lhs_mz.iloc[:,0], rhs_mz, offset=offset_mz).fit(disp=False)
    c_mz  = mod_mz2.params.get('sapm_pre_r_opp', None)
    se_mz = mod_mz2.bse.get('sapm_pre_r_opp', None)
    p_mz  = mod_mz2.pvalues.get('sapm_pre_r_opp', None)
    print(f'sapm_pre_r_opp: {fmt(c_mz, se_mz, p_mz)}')
except Exception as e:
    print(f'NOT AVAILABLE ({e})')

print()
print('='*70)
print('(8) 2022-2025 TOP DECILE (threshold pre-2022)')
print('='*70)
try:
    bfo = pd.read_csv(BASE / 'bfo_odds_final' / 'bfo_odds_devigged.csv', low_memory=False)
    bfo['date'] = pd.to_datetime(bfo['date'], errors='coerce')

    def am_to_dec(x):
        if pd.isna(x): return np.nan
        return x/100+1 if x>0 else 100/abs(x)+1

    merged8 = panel.merge(
        bfo[['fight_id','fighter_ufc_id','fighter_close_lo','fighter_close_hi']],
        left_on=['fight_id','fighter_id'], right_on=['fight_id','fighter_ufc_id'], how='left')
    merged8['dec_best'] = merged8['fighter_close_hi'].apply(am_to_dec)  # best-book odds
    merged8['dec_mid']  = (merged8['fighter_close_lo'].apply(am_to_dec) +
                           merged8['fighter_close_hi'].apply(am_to_dec)) / 2

    thresh = merged8[merged8['date'] < '2022-01-01']['sapm_pre_r_opp'].dropna().quantile(0.90)

    mask8 = ((merged8['date'] >= '2022-01-01') & (merged8['date'] <= '2025-12-31') &
             merged8['sapm_pre_r_opp'].notna() & merged8['dec_mid'].notna() &
             merged8['won'].notna())
    top8  = merged8[mask8 & (merged8['sapm_pre_r_opp'] >= thresh)].copy()
    top8['pnl'] = top8['won'] * (top8['dec_mid'] - 1) - (1 - top8['won'])

    rng8  = np.random.default_rng(SEED)
    boot_gap = [rng8.choice(top8['calibration_gap'].values, len(top8), replace=True).mean()*100
                for _ in range(5000)]
    boot_pnl = [rng8.choice(top8['pnl'].values, len(top8), replace=True).mean()*100
                for _ in range(5000)]
    ci_gap = np.percentile(boot_gap, [2.5, 97.5])
    ci_pnl = np.percentile(boot_pnl, [2.5, 97.5])

    print(f'Pre-2022 90th pct threshold: {thresh:.4f}')
    print(f'N bets: {len(top8)}')
    print(f'Gross gap:           {top8["calibration_gap"].mean()*100:+.2f}pp')
    print(f'Bootstrap 95% CI (gross gap): [{ci_gap[0]:+.2f}, {ci_gap[1]:+.2f}] pp')
    print(f'Win rate:            {top8["won"].mean():.4f}')
    print(f'Mean best-book dec odds: {top8["dec_best"].mean():.4f}')
    print(f'P&L per unit bet:    {top8["pnl"].mean()*100:+.2f}pp')
    print(f'Bootstrap 95% CI (P&L):   [{ci_pnl[0]:+.2f}, {ci_pnl[1]:+.2f}] pp')
except Exception as e:
    print(f'NOT AVAILABLE ({e})')

print()
print('='*70)
print('(9) age_at_fight FULL SAMPLE')
print('='*70)
c_a,se_a,p_a,n_a = cluster_ols(est, FORMULA, 'age_at_fight')
print(fmt(c_a,se_a,p_a,n_a))

print('\nDONE.')
