"""
build_analysis_panel.py
=======================
Sources:
  - C:/Users/micha/merged/sapm_residual.csv       (signal, 13,501 rows)
  - C:/Users/micha/merged/ufc_fights_clean.csv    (odds, probs, outcomes, metadata)
  - C:/Users/micha/ufcstats_raw/fights.csv        (full fight history for layoff calc)

Constructs one-row-per-fighter-per-fight analysis panel with:
  Signal:           sapm_pre_r, sapm_pre_r_opp
  Devigged prob:    p_close_hi  (best-book closing line, NaN where no odds)
  Win indicator:    win  (1=W, 0=L, NaN for D/NC)
  Calibration gap:  g = win - p_close_hi  (NaN where either is missing)
  Covariates:       layoff_days, division, year, fighter_id, fight_id
  NOTE:             age is absent — no DOB in canonical source files; needs fighter-page scrape

Output: C:/Users/micha/merged/analysis_panel.csv
"""

import sys, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

# ── 0. Paths ──────────────────────────────────────────────────────────────────
RESID      = 'C:/Users/micha/merged/sapm_residual.csv'
CLEAN      = 'C:/Users/micha/merged/ufc_fights_clean.csv'
FIGHTS_RAW = 'C:/Users/micha/ufcstats_raw/fights.csv'
OUT        = 'C:/Users/micha/merged/analysis_panel.csv'

# ── 1. Load ───────────────────────────────────────────────────────────────────
print('Loading files ...')
resid = pd.read_csv(RESID, parse_dates=['date'])
clean = pd.read_csv(CLEAN)
clean['date'] = pd.to_datetime(clean['date'], format='%B %d, %Y')
raw   = pd.read_csv(FIGHTS_RAW)
raw['date'] = pd.to_datetime(raw['date'], format='%B %d, %Y')
print(f'  sapm_residual    : {len(resid):,} rows')
print(f'  ufc_fights_clean : {len(clean):,} rows')
print(f'  fights_raw       : {len(raw):,} rows')

# ── 2. Per-fighter devigged prob, win indicator, fighter_id, fight_id ─────────
# From clean: fighter perspective depends on whether this fighter is A or B.
# Build long form of clean: one row per fighter per fight.
print('\nBuilding per-fighter perspective from clean file ...')

keep_common = [
    'fight_url', 'date', 'division',
    'p_close_hi_a', 'p_close_hi_b',
    'result_a', 'result_b',
    'fighter_a', 'fighter_a_url',
    'fighter_b', 'fighter_b_url',
]

ca = clean[keep_common].copy()
ca['fighter']      = ca['fighter_a']
ca['fighter_url']  = ca['fighter_a_url']
ca['p_close_hi']   = ca['p_close_hi_a']
ca['result']       = ca['result_a']

cb = clean[keep_common].copy()
cb['fighter']      = cb['fighter_b']
cb['fighter_url']  = cb['fighter_b_url']
cb['p_close_hi']   = cb['p_close_hi_b']
cb['result']       = cb['result_b']

long_clean = pd.concat([
    ca[['fight_url', 'date', 'division', 'fighter', 'fighter_url', 'p_close_hi', 'result']],
    cb[['fight_url', 'date', 'division', 'fighter', 'fighter_url', 'p_close_hi', 'result']],
], ignore_index=True)

# fighter_id and fight_id: last segment of their respective URLs
long_clean['fighter_id'] = long_clean['fighter_url'].str.split('/').str[-1]
long_clean['fight_id']   = long_clean['fight_url'].str.split('/').str[-1]

# win indicator: 1=W, 0=L, NaN=D/NC
long_clean['win'] = np.where(
    long_clean['result'] == 'W', 1.0,
    np.where(long_clean['result'] == 'L', 0.0, np.nan)
)

print(f'  long_clean rows  : {len(long_clean):,}')
print(f'  win dist : {long_clean["win"].value_counts(dropna=False).to_dict()}')

# ── 3. Compute layoff_days from full fight history ────────────────────────────
print('\nComputing layoff_days from raw fight history ...')

# Raw has two rows per fight (one per fighter). Use fighter_url as fighter key.
layoff_src = raw[['fighter_url', 'date']].drop_duplicates().copy()
layoff_src = layoff_src.sort_values(['fighter_url', 'date']).reset_index(drop=True)

# Previous fight date per fighter per fight
layoff_src['prev_date'] = layoff_src.groupby('fighter_url')['date'].shift(1)
layoff_src['layoff_days'] = (layoff_src['date'] - layoff_src['prev_date']).dt.days

# Only keep what we need for the merge
layoff_map = layoff_src[['fighter_url', 'date', 'layoff_days']].drop_duplicates(
    subset=['fighter_url', 'date']
)
print(f'  layoff_map rows  : {len(layoff_map):,}')
print(f'  layoff_days null : {layoff_map["layoff_days"].isna().sum():,}  '
      f'(debut fights — expected)')

# ── 4. Merge everything onto sapm_residual ────────────────────────────────────
print('\nMerging panel ...')

panel = resid[['fight_url', 'date', 'fighter', 'opponent',
               'sapm_r', 'sapm_pre_r', 'sapm_pre_r_opp']].copy()

# Join per-fighter perspective columns from long_clean
panel = panel.merge(
    long_clean[['fight_url', 'fighter', 'division', 'fighter_id', 'fight_id',
                'p_close_hi', 'win', 'result', 'fighter_url']],
    on=['fight_url', 'fighter'],
    how='left'
)

# Join layoff_days via fighter_url + date
panel = panel.merge(
    layoff_map.rename(columns={'fighter_url': 'fighter_url_lay'}),
    left_on=['fighter_url', 'date'],
    right_on=['fighter_url_lay', 'date'],
    how='left'
).drop(columns=['fighter_url_lay'])

# year
panel['year'] = panel['date'].dt.year

# ── 5. Calibration gap ────────────────────────────────────────────────────────
# g = win indicator - devigged prob (NaN where win is NaN or prob is NaN)
panel['g'] = panel['win'] - panel['p_close_hi']

print(f'\n  Panel rows       : {len(panel):,}')
print(f'  Columns          : {panel.columns.tolist()}')

# ── 6. Coverage report ────────────────────────────────────────────────────────
print('\n-- Coverage --')
key_cols = ['sapm_pre_r', 'sapm_pre_r_opp', 'p_close_hi', 'win', 'g',
            'layoff_days', 'division', 'year', 'fighter_id', 'fight_id']
for col in key_cols:
    nn   = panel[col].notna().sum()
    pct  = 100 * nn / len(panel)
    print(f'  {col:20s}: {nn:6,} / {len(panel):,}  ({pct:.1f}%)')

# ── 7. Summary stats ──────────────────────────────────────────────────────────
print('\n-- Summary stats --')
for col in ['sapm_pre_r', 'sapm_pre_r_opp', 'p_close_hi', 'g', 'layoff_days']:
    d = panel[col].describe()
    print(f'  {col:20s}  mean={d["mean"]:+7.3f}  std={d["std"]:.3f}  '
          f'min={d["min"]:+7.3f}  max={d["max"]:+7.3f}')

# Favourite win rate check
wl = panel[panel['win'].notna()]
fav_win = (wl.loc[wl['p_close_hi'] > 0.5, 'win'] == 1).mean()
print(f'\n  Favourite win rate   : {fav_win:.3f}  (expect ~0.667)')
print(f'  Mean calibration gap : {panel["g"].mean():.4f}  (expect ~0)')

# ── 8. Save ───────────────────────────────────────────────────────────────────
out_cols = [
    'fight_id', 'fighter_id', 'fight_url', 'date', 'year',
    'fighter', 'opponent',
    'division',
    'sapm_pre_r', 'sapm_pre_r_opp',
    'p_close_hi', 'win', 'result',
    'g',
    'layoff_days',
    'sapm_r',   # raw expanding signal, kept for reference
]
panel[out_cols].to_csv(OUT, index=False)
print(f'\nSaved: {OUT}')
print(f'  Shape: {panel[out_cols].shape}')
print('\nNOTE: age absent — no DOB in ufcstats_raw/fights.csv or ufc_fights_clean.csv.')
print('      Requires a separate fighter-page scrape to add.')
print('\nDone.')
