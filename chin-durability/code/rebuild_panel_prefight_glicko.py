"""
rebuild_panel_prefight_glicko.py
================================
Forensic reconstruction of the original _r residualisation pipeline.

Evidence points to pre-fight opponent Glicko-1 as the original quality measure
(34-var regression t=3.943, closest to original t≈4.030 vs. static Glicko t=3.706).

Steps:
  1. Build Glicko-1 time-series from ufc_extended.csv (≤ April 18 2026)
  2. For each fighter-fight, avg_pre_opp_glicko = career-mean pre-fight opp rating
  3. Residualise 17 style vars on avg_pre_opp_glicko + C(division)
  4. Overwrite _r columns in style_panel.csv
  5. Report sapm_r_opp coefficient under main OLS as sanity check

Run order AFTER this: opp_sapm_analysis.py → run_exploratory_rw41.py (5-var only)
→ age_at_fight_analysis.py → robustness_checks.py → rolling_window_efficiency.py
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

BASE    = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis')
RAW     = BASE / 'ufcstats_raw' / 'ufc_extended.csv'
PANEL_P = BASE / 'preliminary results' / 'style_panel.csv'

CUTOFF  = pd.Timestamp('2026-04-18')

STYLE_VARS = [
    'slpm_r','str_acc_r','dist_share_r','clinch_share_r','ground_share_r',
    'head_share_r','body_share_r','leg_share_r','kd_rate_r','td_per15_r',
    'td_acc_r','td_def_r','sub_per15_r','ctrl_share_r','sapm_r',
    'avg_fight_min_r','finish_rate_r',
]

# Raw names that back each _r var (same names without _r suffix)
RAW_STYLE = [v[:-2] for v in STYLE_VARS]  # strip _r

# ── 1. Load raw fight results ───────────────────────────────────────────────
print('Loading ufc_extended.csv ...')
ext = pd.read_csv(RAW, parse_dates=['date'])
ext = ext[ext['date'] <= CUTOFF].copy()
print(f'  Rows after cutoff filter: {len(ext):,}')

# fighter_id = URL slug (last segment of fighter_url) — matches panel
ext['fighter_id'] = ext['fighter_url'].str.split('/').str[-1]

# Identify opponents: within each fight_url, pair fighters
# ufc_extended has one row per fighter per fight; 2 rows per fight
ext = ext.sort_values(['date','fight_url','fighter']).reset_index(drop=True)

# Map fight → list of (fighter_id, result)
# Build fight pairs to get opponent per row
fight_grp = ext.groupby('fight_url')

opp_map = {}  # fight_url → {fighter_id: opponent_fighter_id}
for furl, grp in fight_grp:
    ids = grp['fighter_id'].tolist()
    if len(ids) == 2:
        opp_map[furl] = {ids[0]: ids[1], ids[1]: ids[0]}

ext['opponent_id'] = ext.apply(
    lambda r: opp_map.get(r['fight_url'], {}).get(r['fighter_id'], None), axis=1
)

# Keep only W/L results (exclude D, NC) for Glicko scoring
# result column: 'W', 'L', 'D', 'NC' or similar
print(f"  Result values: {ext['result'].value_counts().to_dict()}")

wl = ext[ext['result'].isin(['W','L'])].copy()
wl = wl.sort_values('date').reset_index(drop=True)
print(f'  W/L rows for Glicko: {len(wl):,}')

# ── 2. Build Glicko-1 ratings ───────────────────────────────────────────────
print('\nBuilding Glicko-1 time-series ...')

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

# ratings dict: fighter_id → (r, RD)
ratings = {}

def get_rating(fid):
    return ratings.get(fid, (R0, RD0))

# Pre-fight opponent Glicko store: list of (fight_url, fighter_id, pre_opp_glicko)
pre_opp_records = []

# Process fights chronologically using ALL fights (for pairing/recording pre-opp Glicko)
# but only UPDATE ratings on decisive W/L outcomes.
# This ensures panel rows where opponent had NC/D still get a pre_opp_glicko record.
wl_results = set(wl['fight_url'].unique())  # fights with ≥1 W/L result

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

    # Always record pre-fight opponent Glicko for both fighters
    pre_opp_records.append({'fight_url': furl, 'fighter_id': fid_a, 'pre_opp_glicko': rb,
                            'date': frow['date']})
    pre_opp_records.append({'fight_url': furl, 'fighter_id': fid_b, 'pre_opp_glicko': ra,
                            'date': frow['date']})

    # Only update ratings for decisive W/L contests
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
    # D / NC / mixed: don't update ratings

pre_opp_df = pd.DataFrame(pre_opp_records)
print(f'  Pre-opp records: {len(pre_opp_df):,}')

# Final Glicko ratings
final_glicko = pd.DataFrame(
    [(fid, r, RD) for fid, (r, RD) in ratings.items()],
    columns=['fighter_id','glicko_built','glicko_rd_built']
)
print(f'  Fighters rated: {len(final_glicko):,}')

# ── 3. Compute avg_pre_opp_glicko per fighter ───────────────────────────────
print('\nComputing avg_pre_opp_glicko per fighter ...')

panel = pd.read_csv(PANEL_P, parse_dates=['date'])
print(f'  Panel shape: {panel.shape}')

panel_fids = set(panel['fighter_id'].dropna().unique())
ext_fids   = set(ext['fighter_id'].dropna().unique())
overlap    = panel_fids & ext_fids
print(f'  Panel fighter_ids: {len(panel_fids):,}')
print(f'  Extended fighter_ids: {len(ext_fids):,}')
print(f'  Overlap: {len(overlap):,} ({100*len(overlap)/len(panel_fids):.1f}%)')

# pre_opp_df already has date from the records (added above)
pre_opp_merged = pre_opp_df.sort_values(['fighter_id','date']).reset_index(drop=True)

# Career-expanding mean of pre_opp_glicko per fighter (up to each fight)
pre_opp_merged['avg_pre_opp_glicko'] = (
    pre_opp_merged.groupby('fighter_id')['pre_opp_glicko']
    .expanding().mean().values
)

print(f'  pre_opp_merged shape: {pre_opp_merged.shape}')
print(f'  Sample avg_pre_opp_glicko: {pre_opp_merged["avg_pre_opp_glicko"].describe()}')

# ── 4. Merge into panel ──────────────────────────────────────────────────────
print('\nMerging into panel ...')

# Panel join: fighter_id + date. Some fighters have multiple fights on same date
# (rare) — keep the one closest in fight order; use fight_url as tiebreak via merge.
# Strategy: merge on fighter_id + date, then check uniqueness.

pre_opp_for_merge = pre_opp_merged[['fighter_id','date','fight_url','avg_pre_opp_glicko']].copy()

panel_aug = panel.merge(
    pre_opp_for_merge[['fighter_id','date','avg_pre_opp_glicko']].drop_duplicates(
        subset=['fighter_id','date'], keep='last'
    ),
    on=['fighter_id','date'], how='left'
)

matched = panel_aug['avg_pre_opp_glicko'].notna().sum()
print(f'  Panel rows with avg_pre_opp_glicko: {matched:,} / {len(panel_aug):,} '
      f'({100*matched/len(panel_aug):.1f}%)')

# Also merge final glicko for corr check
panel_aug = panel_aug.merge(final_glicko[['fighter_id','glicko_built']], on='fighter_id', how='left')
corr_glicko = panel_aug[['glicko','glicko_built']].dropna()
if len(corr_glicko) > 0:
    c, _ = pearsonr(corr_glicko['glicko'], corr_glicko['glicko_built'])
    print(f'  Corr(panel glicko, built glicko_built): {c:.4f}')

# ── 5. Re-residualise style vars ────────────────────────────────────────────
print('\nRe-residualising style vars on avg_pre_opp_glicko + C(division) ...')

# Work on rows where avg_pre_opp_glicko is available
mask_ok = panel_aug['avg_pre_opp_glicko'].notna() & panel_aug['division'].notna()
print(f'  Rows usable for residualisation: {mask_ok.sum():,}')

raw_names = {
    'slpm_r':       'slpm',
    'str_acc_r':    'str_acc',
    'dist_share_r': 'dist_share',
    'clinch_share_r':'clinch_share',
    'ground_share_r':'ground_share',
    'head_share_r': 'head_share',
    'body_share_r': 'body_share',
    'leg_share_r':  'leg_share',
    'kd_rate_r':    'kd_rate',
    'td_per15_r':   'td_per15',
    'td_acc_r':     'td_acc',
    'td_def_r':     'td_def',
    'sub_per15_r':  'sub_per15',
    'ctrl_share_r': 'ctrl_share',
    'sapm_r':       'sapm',
    'avg_fight_min_r': 'avg_fight_min',
    'finish_rate_r':'finish_rate',
}

corrs = {}
for r_col, raw_col in raw_names.items():
    if raw_col not in panel_aug.columns:
        print(f'  WARNING: {raw_col} not in panel — skipping')
        continue

    sub = panel_aug[mask_ok & panel_aug[raw_col].notna()].copy()
    if len(sub) < 100:
        print(f'  {r_col}: too few rows ({len(sub)}) — skipped')
        continue

    try:
        formula_res = f'{raw_col} ~ avg_pre_opp_glicko + C(division)'
        lhs_r, rhs_r = patsy.dmatrices(formula_res, data=sub, return_type='dataframe')
        mod_r = sm.OLS(lhs_r.iloc[:,0], rhs_r).fit()
        resid = mod_r.resid

        # Before overwrite: corr with old _r
        old_r = panel_aug.loc[sub.index, r_col]
        c_old, _ = pearsonr(old_r.dropna(), resid[old_r.notna()])
        corrs[r_col] = c_old

        # Write new residuals back to panel_aug
        panel_aug.loc[sub.index, r_col] = resid.values
        print(f'  {r_col}: N={len(sub):,}  corr(old,new)={c_old:.4f}')
    except Exception as ex:
        print(f'  {r_col}: FAILED — {ex}')

# ── 6. Save updated panel ────────────────────────────────────────────────────
print('\nSaving updated style_panel.csv ...')

# Drop helper columns before saving
save_cols = [c for c in panel_aug.columns
             if c not in ['glicko_built', 'avg_pre_opp_glicko']]
panel_save = panel_aug[save_cols].copy()
panel_save.to_csv(PANEL_P, index=False)
print(f'  Saved {len(panel_save):,} rows × {len(save_cols)} cols')

# ── 7. Quick sanity check — main OLS ────────────────────────────────────────
print('\n' + '='*65)
print('SANITY CHECK — Main OLS on updated panel')
print('='*65)

panel_check = pd.read_csv(PANEL_P, parse_dates=['date'])
panel_check['year']          = panel_check['date'].dt.year
panel_check['layoff_days_c'] = panel_check['layoff_days'].clip(0, 365*2)

ALL_ATOMIC = STYLE_VARS + [v + '_opp' for v in STYLE_VARS]

opp_join = (panel_check[['fight_id','fighter_id'] + STYLE_VARS]
            .rename(columns={'fighter_id':'opponent_id',
                             **{v: v+'_opp' for v in STYLE_VARS}}))
panel_check = panel_check.merge(opp_join, on=['fight_id','opponent_id'], how='left')

req = (ALL_ATOMIC
       + ['calibration_gap','glicko_z','glicko','age_at_fight',
          'layoff_days_c','division','year','fighter_id','fight_id'])
panel_est = panel_check[panel_check[req].notna().all(axis=1)].copy().reset_index(drop=True)

# Fix glicko_z
train = panel_est[panel_est['year'] <= 2019]
_mu, _sd = train['glicko'].mean(), train['glicko'].std()
panel_est['glicko_z'] = (panel_est['glicko'] - _mu) / _sd

print(f'Estimation panel N={len(panel_est):,}')

FORMULA = ('calibration_gap ~ '
           + ' + '.join(ALL_ATOMIC)
           + ' + glicko_z + age_at_fight + layoff_days_c'
           + ' + C(division) + C(year)')

dummy = panel_est.iloc[[0]].assign(division='other', calibration_gap=0.0)
aug   = pd.concat([panel_est, dummy], ignore_index=True)
dpos  = len(aug) - 1
lhs, rhs = patsy.dmatrices(FORMULA, data=aug, return_type='dataframe')
mask = lhs.index != dpos
lhs, rhs = lhs[mask], rhs[mask]
groups = aug.loc[lhs.index, 'fighter_id'].values

mod = sm.OLS(lhs.iloc[:,0], rhs).fit(cov_type='cluster', cov_kwds={'groups': groups})

print(f"\nsapm_r_opp:   coef={mod.params['sapm_r_opp']:+.5f}  "
      f"t={mod.tvalues['sapm_r_opp']:+.4f}  "
      f"p={mod.pvalues['sapm_r_opp']:.4f}")
print(f"age_at_fight: coef={mod.params['age_at_fight']:+.5f}  "
      f"t={mod.tvalues['age_at_fight']:+.4f}  "
      f"p={mod.pvalues['age_at_fight']:.4f}")

# IS / OOS split
for label, cond in [('IS (≤2019)', panel_est['year'] <= 2019),
                    ('OOS (2020+)', panel_est['year'] >= 2020)]:
    sub = panel_est[cond].copy()
    dm  = pd.concat([sub, sub.iloc[[0]].assign(division='other', calibration_gap=0.0)],
                     ignore_index=True)
    dp  = len(dm) - 1
    l, r = patsy.dmatrices(FORMULA, data=dm, return_type='dataframe')
    mk   = l.index != dp
    l, r = l[mk], r[mk]
    g    = dm.loc[l.index, 'fighter_id'].values
    m    = sm.OLS(l.iloc[:,0], r).fit(cov_type='cluster', cov_kwds={'groups': g})
    print(f"\n{label} N={len(sub):,}")
    if 'sapm_r_opp' in m.params.index:
        ci = m.conf_int().loc['sapm_r_opp']
        print(f"  sapm_r_opp: coef={m.params['sapm_r_opp']:+.5f}  "
              f"t={m.tvalues['sapm_r_opp']:+.4f}  "
              f"p={m.pvalues['sapm_r_opp']:.4f}  "
              f"CI=[{ci[0]:+.5f}, {ci[1]:+.5f}]")

print('\nDone. Panel updated with pre-fight opponent Glicko residualisation.')
