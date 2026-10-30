"""
rebuild_panel_prefight_glicko_clean.py
=======================================
Adapts rebuild_panel_prefight_glicko.py to:
  - Read style_panel_clean.csv (with pre-fight rolling stats)
  - Residualise the NEW pre-fight rolling vars (_prefight suffix → _r suffix)
    plus keep the existing positional _r vars (dist_share_r etc.) from style_panel
  - Build Glicko from ufc_extended.csv (unchanged logic)
  - Write output back to style_panel_clean.csv (update in place)
  - Report estimation sample N and primary OLS result

STEP 2 of the pipeline.
"""

import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import statsmodels.api as sm
import patsy
from pathlib import Path
from scipy.stats import pearsonr

BASE      = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis')
RAW       = BASE / 'ufcstats_raw' / 'ufc_extended.csv'
CLEAN_P   = BASE / 'preliminary results' / 'style_panel_clean.csv'
CUTOFF    = pd.Timestamp('2026-04-18')

# Mapping: prefight_col → residualised col name (matching style_panel convention)
# New pre-fight rolling vars from fight_totals_clean
PREFIGHT_TO_R = {
    'sapm_prefight':         'sapm_r',
    'slpm_prefight':         'slpm_r',
    'str_acc_prefight':      'str_acc_r',
    'str_def_prefight':      'str_def_r',     # new — not in old panel
    'td_per15_prefight':     'td_per15_r',
    'td_acc_prefight':       'td_acc_r',
    'td_def_prefight':       'td_def_r',
    'sub_per15_prefight':    'sub_per15_r',
    'kd_rate_prefight':      'kd_rate_r',
    'ctrl_share_prefight':   'ctrl_share_r',
    'avg_fight_min_prefight':'avg_fight_min_r',
    'finish_rate_prefight':  'finish_rate_r',
}

# Style vars that will appear in FORMULA (must include _r suffix in panel cols)
# Positional vars (not rebuilt from fight_totals) — keep as-is from old panel
POSITIONAL_R = [
    'dist_share_r', 'clinch_share_r', 'ground_share_r',
    'head_share_r', 'body_share_r', 'leg_share_r',
]

STYLE_VARS = (list(PREFIGHT_TO_R.values())      # from clean rebuild
              + POSITIONAL_R                       # from original panel
              + ['str_def_r'])                     # new var (str_def not in old)

# Deduplicate
STYLE_VARS = list(dict.fromkeys(STYLE_VARS))

# ── 1. Build Glicko-1 from ufc_extended ──────────────────────────────────────
print('=' * 65)
print('STEP 2a — Building Glicko-1 from ufc_extended.csv')
print('=' * 65)

ext = pd.read_csv(RAW, parse_dates=['date'])
ext = ext[ext['date'] <= CUTOFF].copy().reset_index(drop=True)
ext['fighter_id'] = ext['fighter_url'].str.split('/').str[-1]
print(f'  ufc_extended rows after cutoff: {len(ext):,}')
print(f'  Result values: {ext["result"].value_counts().to_dict()}')

ext = ext.sort_values(['date', 'fight_url', 'fighter']).reset_index(drop=True)

# Map fight → opponent per fighter
fight_grp = ext.groupby('fight_url')
opp_map = {}
for furl, grp in fight_grp:
    ids = grp['fighter_id'].tolist()
    if len(ids) == 2:
        opp_map[furl] = {ids[0]: ids[1], ids[1]: ids[0]}

ext['opponent_id'] = ext.apply(
    lambda r: opp_map.get(r['fight_url'], {}).get(r['fighter_id'], None), axis=1
)

R0, RD0 = 1500.0, 350.0
q_c = np.log(10) / 400.0

def g_f(RD):
    return 1.0 / np.sqrt(1 + 3 * q_c**2 * RD**2 / np.pi**2)

def glicko_update(r, RD, ro, RDo, s):
    g  = g_f(RDo)
    E  = 1.0 / (1.0 + 10.0 ** (-g * (r - ro) / 400.0))
    d2 = 1.0 / (q_c**2 * g**2 * E * (1 - E))
    r_new  = r  + q_c / (1.0/RD**2 + 1.0/d2) * g * (s - E)
    RD_new = np.sqrt(1.0 / (1.0/RD**2 + 1.0/d2))
    return r_new, RD_new

ratings = {}

def get_rating(fid):
    return ratings.get(fid, (R0, RD0))

pre_opp_records = []

fights_sorted = (ext[['fight_url','date']].drop_duplicates()
                 .sort_values('date').reset_index(drop=True))

for _, frow in fights_sorted.iterrows():
    furl = frow['fight_url']
    grp_all = ext[ext['fight_url'] == furl]
    if len(grp_all) != 2:
        continue

    rows = grp_all.to_dict('records')
    fid_a, fid_b = rows[0]['fighter_id'], rows[1]['fighter_id']
    res_a_str = rows[0]['result']
    res_b_str = rows[1]['result']

    ra, RDa = get_rating(fid_a)
    rb, RDb = get_rating(fid_b)

    pre_opp_records.append({'fight_url': furl, 'fighter_id': fid_a, 'pre_opp_glicko': rb,
                            'date': frow['date']})
    pre_opp_records.append({'fight_url': furl, 'fighter_id': fid_b, 'pre_opp_glicko': ra,
                            'date': frow['date']})

    if res_a_str == 'W' and res_b_str == 'L':
        ra_new, RDa_new = glicko_update(ra, RDa, rb, RDb, 1.0)
        rb_new, RDb_new = glicko_update(rb, RDb, ra, RDa, 0.0)
        ratings[fid_a] = (ra_new, RDa_new)
        ratings[fid_b] = (rb_new, RDb_new)
    elif res_a_str == 'L' and res_b_str == 'W':
        ra_new, RDa_new = glicko_update(ra, RDa, rb, RDb, 0.0)
        rb_new, RDb_new = glicko_update(rb, RDb, ra, RDa, 1.0)
        ratings[fid_a] = (ra_new, RDa_new)
        ratings[fid_b] = (rb_new, RDb_new)

pre_opp_df = pd.DataFrame(pre_opp_records)
print(f'  Pre-opp Glicko records: {len(pre_opp_df):,}')

final_glicko = pd.DataFrame(
    [(fid, r, RD) for fid, (r, RD) in ratings.items()],
    columns=['fighter_id','glicko_built','glicko_rd_built']
)
print(f'  Fighters rated: {len(final_glicko):,}')

# ── 2. Load clean panel ───────────────────────────────────────────────────────
print()
print('=' * 65)
print('STEP 2b — Loading style_panel_clean.csv')
print('=' * 65)

panel = pd.read_csv(CLEAN_P, parse_dates=['date'])
print(f'  Panel shape: {panel.shape}')
print(f'  Panel columns: {list(panel.columns)}')

# Check which prefight cols are present
pf_present = [c for c in PREFIGHT_TO_R.keys() if c in panel.columns]
pf_missing  = [c for c in PREFIGHT_TO_R.keys() if c not in panel.columns]
print(f'  Pre-fight cols present: {pf_present}')
if pf_missing:
    print(f'  Pre-fight cols MISSING: {pf_missing}')

# ── 3. Compute avg_pre_opp_glicko ────────────────────────────────────────────
print()
print('STEP 2c — Computing avg_pre_opp_glicko per fighter-fight')

pre_opp_merged = pre_opp_df.sort_values(['fighter_id','date']).reset_index(drop=True)
pre_opp_merged['avg_pre_opp_glicko'] = (
    pre_opp_merged.groupby('fighter_id')['pre_opp_glicko']
    .expanding().mean().values
)

pre_opp_for_merge = pre_opp_merged[['fighter_id','date','avg_pre_opp_glicko']].drop_duplicates(
    subset=['fighter_id','date'], keep='last'
)

panel_aug = panel.merge(pre_opp_for_merge, on=['fighter_id','date'], how='left')
matched = panel_aug['avg_pre_opp_glicko'].notna().sum()
print(f'  Panel rows with avg_pre_opp_glicko: {matched:,} / {len(panel_aug):,} '
      f'({100*matched/len(panel_aug):.1f}%)')

# ── 4. Residualise pre-fight vars ─────────────────────────────────────────────
print()
print('=' * 65)
print('STEP 2d — Residualising pre-fight vars on avg_pre_opp_glicko + C(division)')
print('=' * 65)

mask_ok = panel_aug['avg_pre_opp_glicko'].notna() & panel_aug['division'].notna()
print(f'  Rows usable for residualisation: {mask_ok.sum():,}')

for pf_col, r_col in PREFIGHT_TO_R.items():
    if pf_col not in panel_aug.columns:
        print(f'  {r_col}: SKIP — {pf_col} not in panel')
        continue

    sub = panel_aug[mask_ok & panel_aug[pf_col].notna()].copy()
    if len(sub) < 100:
        print(f'  {r_col}: too few rows ({len(sub)}) — skipped')
        continue

    try:
        formula_res = f'{pf_col} ~ avg_pre_opp_glicko + C(division)'
        lhs_r, rhs_r = patsy.dmatrices(formula_res, data=sub, return_type='dataframe')
        mod_r = sm.OLS(lhs_r.iloc[:,0], rhs_r).fit()
        resid = mod_r.resid

        # Write residuals to _r column
        if r_col not in panel_aug.columns:
            panel_aug[r_col] = np.nan
        panel_aug.loc[sub.index, r_col] = resid.values

        print(f'  {r_col} ← resid({pf_col}): N={len(sub):,}  '
              f'R²={mod_r.rsquared:.4f}  '
              f'mean_resid={resid.mean():.4f}')
    except Exception as ex:
        print(f'  {r_col}: FAILED — {ex}')

# Save updated panel
panel_aug_save = panel_aug.drop(columns=['avg_pre_opp_glicko'], errors='ignore')
panel_aug_save.to_csv(CLEAN_P, index=False)
print(f'\n  Saved {len(panel_aug_save):,} rows × {len(panel_aug_save.columns)} cols to {CLEAN_P}')

# ── STEP 3 — Estimation sample ───────────────────────────────────────────────
print()
print('=' * 65)
print('STEP 3 — Estimation sample N')
print('=' * 65)

panel_check = pd.read_csv(CLEAN_P, parse_dates=['date'])
panel_check['year']          = panel_check['date'].dt.year
panel_check['layoff_days_c'] = panel_check['layoff_days'].clip(0, 365 * 2)

# Style vars present (only those actually in panel_check)
STYLE_VARS_PRESENT = [v for v in STYLE_VARS if v in panel_check.columns]
ALL_ATOMIC_PRESENT = STYLE_VARS_PRESENT + [v + '_opp' for v in STYLE_VARS_PRESENT]

print(f'  Style vars: {STYLE_VARS_PRESENT}')

# Join opponent style vars
opp_join = (panel_check[['fight_id', 'fighter_id'] + STYLE_VARS_PRESENT]
            .rename(columns={'fighter_id': 'opponent_id',
                             **{v: v + '_opp' for v in STYLE_VARS_PRESENT}}))
panel_check = panel_check.merge(opp_join, on=['fight_id', 'opponent_id'], how='left')

req = (['sapm_r_opp', 'calibration_gap', 'market_prob_shin', 'q_close',
        'glicko_z', 'glicko', 'age_at_fight', 'layoff_days_c',
        'won', 'division', 'year', 'fighter_id', 'fight_id']
       + ALL_ATOMIC_PRESENT)
req = list(dict.fromkeys(req))  # deduplicate
req = [r for r in req if r in panel_check.columns]

panel_est = panel_check[panel_check[req].notna().all(axis=1)].copy().reset_index(drop=True)

# Re-standardise glicko_z on 2007-2019 training moments
train_mask = panel_est['year'] <= 2019
_mu, _sd = panel_est.loc[train_mask, 'glicko'].mean(), panel_est.loc[train_mask, 'glicko'].std()
panel_est['glicko_z'] = (panel_est['glicko'] - _mu) / _sd

print(f'  Estimation sample N = {len(panel_est):,}')
print(f'  (Previous N = 5,234)')
print(f'  Date range: {panel_est["date"].min().date()} → {panel_est["date"].max().date()}')
print(f'  Year range: {panel_est["year"].min()} → {panel_est["year"].max()}')

IS  = panel_est[panel_est['year'] <= 2019]
OOS = panel_est[panel_est['year'] >= 2020]
print(f'  IS  (≤2019): N={len(IS):,}')
print(f'  OOS (2020+): N={len(OOS):,}')

# ── STEP 4 — Primary OLS ─────────────────────────────────────────────────────
print()
print('=' * 65)
print('STEP 4 — Primary OLS: calibration_gap ~ sapm_r_opp + controls')
print('=' * 65)

FORMULA = ('calibration_gap ~ '
           + ' + '.join(ALL_ATOMIC_PRESENT)
           + ' + glicko_z + age_at_fight + layoff_days_c'
           + ' + C(division) + C(year)')

# Add dummy row to ensure all division/year levels present in design matrix
dummy = panel_est.iloc[[0]].assign(division='other', calibration_gap=0.0)
aug   = pd.concat([panel_est, dummy], ignore_index=True)
dpos  = len(aug) - 1

lhs, rhs = patsy.dmatrices(FORMULA, data=aug, return_type='dataframe')
mask = lhs.index != dpos
lhs, rhs = lhs[mask], rhs[mask]
groups = aug.loc[lhs.index, 'fighter_id'].values

mod = sm.OLS(lhs.iloc[:,0], rhs).fit(cov_type='cluster', cov_kwds={'groups': groups})

print(f'\n  Full-sample OLS (N={len(panel_est):,}, cluster SE by fighter_id):')
print(f'  Formula: calibration_gap ~ [17 style_vars + _opp] + glicko_z + age_at_fight + layoff_days_c + C(year) + C(division)')
print()
print(f'  {"Variable":<25} {"Coef":>10} {"SE":>10} {"t":>8} {"p":>8}')
print(f'  {"-"*65}')

key_vars = ['sapm_r_opp', 'slpm_r_opp', 'age_at_fight', 'glicko_z', 'layoff_days_c']
for var in key_vars:
    if var in mod.params.index:
        print(f'  {var:<25} {mod.params[var]:>10.5f} {mod.bse[var]:>10.5f} '
              f'{mod.tvalues[var]:>8.3f} {mod.pvalues[var]:>8.4f}')

print()
print(f'  R² = {mod.rsquared:.4f}  Adj-R² = {mod.rsquared_adj:.4f}  N = {len(panel_est):,}')

# IS / OOS split
print()
print('  In-sample / Out-of-sample split:')
for label, sub_df in [('IS (≤2019)', IS), ('OOS (2020+)', OOS)]:
    dm  = pd.concat([sub_df, sub_df.iloc[[0]].assign(division='other', calibration_gap=0.0)],
                    ignore_index=True)
    dp  = len(dm) - 1
    l, r = patsy.dmatrices(FORMULA, data=dm, return_type='dataframe')
    mk   = l.index != dp
    l, r = l[mk], r[mk]
    g    = dm.loc[l.index, 'fighter_id'].values
    m    = sm.OLS(l.iloc[:,0], r).fit(cov_type='cluster', cov_kwds={'groups': g})
    ci   = m.conf_int()
    print(f'\n  {label} N={len(sub_df):,}')
    if 'sapm_r_opp' in m.params.index:
        ci_row = ci.loc['sapm_r_opp']
        print(f'    sapm_r_opp: coef={m.params["sapm_r_opp"]:+.5f}  '
              f'SE={m.bse["sapm_r_opp"]:.5f}  '
              f't={m.tvalues["sapm_r_opp"]:+.3f}  '
              f'p={m.pvalues["sapm_r_opp"]:.4f}  '
              f'CI=[{ci_row[0]:+.5f}, {ci_row[1]:+.5f}]')

# Simple 5-var OLS as additional check
print()
print('  Simple 5-var OLS (sapm_r_opp + age + glicko_z + layoff + C(year) + C(division)):')
FORMULA5 = ('calibration_gap ~ sapm_r_opp + age_at_fight + glicko_z + layoff_days_c'
            + ' + C(division) + C(year)')
aug5  = pd.concat([panel_est, dummy], ignore_index=True)
l5, r5 = patsy.dmatrices(FORMULA5, data=aug5, return_type='dataframe')
mk5   = l5.index != dpos
l5, r5 = l5[mk5], r5[mk5]
g5    = aug5.loc[l5.index, 'fighter_id'].values
m5    = sm.OLS(l5.iloc[:,0], r5).fit(cov_type='cluster', cov_kwds={'groups': g5})
if 'sapm_r_opp' in m5.params.index:
    ci5 = m5.conf_int().loc['sapm_r_opp']
    print(f'    sapm_r_opp: coef={m5.params["sapm_r_opp"]:+.5f}  '
          f'SE={m5.bse["sapm_r_opp"]:.5f}  '
          f't={m5.tvalues["sapm_r_opp"]:+.3f}  '
          f'p={m5.pvalues["sapm_r_opp"]:.4f}  '
          f'CI=[{ci5[0]:+.5f}, {ci5[1]:+.5f}]')

print()
print('=' * 65)
print('Pipeline COMPLETE. Results manifest:')
print('=' * 65)
print(f'  style_panel_clean.csv:  {len(panel_aug_save):,} rows × {len(panel_aug_save.columns)} cols')
print(f'  Estimation sample N:    {len(panel_est):,}  (prev: 5,234)')
print(f'  sapm_r_opp full OLS:    coef={mod.params.get("sapm_r_opp", float("nan")):+.5f}  '
      f't={mod.tvalues.get("sapm_r_opp", float("nan")):+.3f}  '
      f'p={mod.pvalues.get("sapm_r_opp", float("nan")):.4f}')
