"""
build_sapm_residual.py
======================
Sources (only these two files):
  - C:/Users/micha/merged/ufc_fights_clean.csv   (7,932 fights, one row per fight)
  - C:/Users/micha/merged/sapm_expanding.csv      (13,501 fighter-fight rows, built this session)

Steps:
  1. Build Glicko-1 time-series from ufc_fights_clean.csv
       - R0=1500, RD0=350; update only on decisive W/L outcomes
       - Same-date fights: all use pre-date ratings, then batch-update
       - Record (fight_url, fighter, pre_opp_glicko) for both fighters in every fight
  2. Join pre_opp_glicko + division to sapm_expanding rows
  3. OLS: sapm_r ~ pre_opp_glicko + C(division); residuals -> sapm_pre_r
  4. Self-join opponent side: sapm_pre_r_opp
  5. Verification gate: sapm_pre_r must vary per fighter
  6. Save -> C:/Users/micha/merged/sapm_residual.csv

Output columns: fight_url, date, fighter, sapm_r, pre_opp_glicko, division,
                sapm_pre_r, sapm_pre_r_opp
"""

import sys, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import statsmodels.api as sm

# ── 0. Paths ──────────────────────────────────────────────────────────────────
CLEAN = 'C:/Users/micha/merged/ufc_fights_clean.csv'
SAPM  = 'C:/Users/micha/merged/sapm_expanding.csv'
OUT   = 'C:/Users/micha/merged/sapm_residual.csv'

# ── 1. Load source files ──────────────────────────────────────────────────────
print('Loading source files ...')
clean = pd.read_csv(CLEAN)
clean['date'] = pd.to_datetime(clean['date'], format='%B %d, %Y')
print(f'  ufc_fights_clean : {len(clean):,} fights')

sapm = pd.read_csv(SAPM, parse_dates=['date'])
print(f'  sapm_expanding   : {len(sapm):,} fighter-fight rows')

# ── 2. Build Glicko-1 from ufc_fights_clean ──────────────────────────────────
print('\nBuilding Glicko-1 ...')

R0, RD0  = 1500.0, 350.0
q_const  = np.log(10) / 400.0

def g_rd(RD):
    return 1.0 / np.sqrt(1.0 + 3.0 * q_const**2 * RD**2 / np.pi**2)

def glicko_update(r, RD, ro, RDo, s):
    """Update fighter rating (r, RD) after one game vs opponent (ro, RDo), score s."""
    g   = g_rd(RDo)
    E   = 1.0 / (1.0 + 10.0 ** (-g * (r - ro) / 400.0))
    d2  = 1.0 / (q_const**2 * g**2 * E * (1.0 - E))
    r_n  = r  + q_const / (1.0/RD**2 + 1.0/d2) * g * (s - E)
    RD_n = np.sqrt(1.0 / (1.0/RD**2 + 1.0/d2))
    return r_n, RD_n

ratings = {}   # fighter_name -> (r, RD)

def get_r(name):
    return ratings.get(name, (R0, RD0))

# Collect pre-fight opponent Glicko records
pre_opp_records = []   # list of dicts: fight_url, fighter, pre_opp_glicko

# Process fights chronologically, batching same-date fights
# (all fights on the same date use ratings from before that date, then update together)
clean_sorted = clean.sort_values('date').reset_index(drop=True)

# Group by date
for date_val, day_fights in clean_sorted.groupby('date', sort=False):
    # --- Phase 1: record pre-fight ratings for all fights on this date ---
    updates = []   # (fighter_a, fighter_b, result_a) to apply after recording
    for _, row in day_fights.iterrows():
        fa, fb = row['fighter_a'], row['fighter_b']
        ra, RDa = get_r(fa)
        rb, RDb = get_r(fb)

        # Opponent's pre-fight Glicko for fighter_a = rb; for fighter_b = ra
        pre_opp_records.append({'fight_url': row['fight_url'], 'fighter': fa, 'pre_opp_glicko': rb})
        pre_opp_records.append({'fight_url': row['fight_url'], 'fighter': fb, 'pre_opp_glicko': ra})

        # Queue update
        updates.append((fa, fb, row['result_a'], ra, RDa, rb, RDb))

    # --- Phase 2: apply Glicko updates for this date's W/L fights ---
    # Use one-game-at-a-time updating (standard Glicko-1)
    for fa, fb, result_a, ra, RDa, rb, RDb in updates:
        if result_a == 'W':           # fighter_a won
            ra_n, RDa_n = glicko_update(ra, RDa, rb, RDb, 1.0)
            rb_n, RDb_n = glicko_update(rb, RDb, ra, RDa, 0.0)
            ratings[fa] = (ra_n, RDa_n)
            ratings[fb] = (rb_n, RDb_n)
        # D / NC: no update

pre_opp_df = pd.DataFrame(pre_opp_records)
print(f'  Pre-opp records  : {len(pre_opp_df):,}')
print(f'  Fighters rated   : {len(ratings):,}')
print(f'  Glicko range     : {pre_opp_df["pre_opp_glicko"].min():.0f} - {pre_opp_df["pre_opp_glicko"].max():.0f}')

# ── 3. Join pre_opp_glicko + division to sapm_expanding ──────────────────────
print('\nJoining Glicko and division to sapm_expanding ...')

div_map = clean[['fight_url', 'division']].drop_duplicates('fight_url')

df = (
    sapm
    .merge(pre_opp_df,   on=['fight_url', 'fighter'], how='left')
    .merge(div_map,      on='fight_url',              how='left')
)

n_total = len(df)
n_glicko_ok  = df['pre_opp_glicko'].notna().sum()
n_division_ok = df['division'].notna().sum()
print(f'  Rows total       : {n_total:,}')
print(f'  pre_opp_glicko   : {n_glicko_ok:,} non-null ({100*n_glicko_ok/n_total:.1f}%)')
print(f'  division         : {n_division_ok:,} non-null ({100*n_division_ok/n_total:.1f}%)')

# Drop rows missing either covariate or the signal
df_reg = df.dropna(subset=['sapm_r', 'pre_opp_glicko', 'division']).copy()
print(f'  Rows for regression : {len(df_reg):,}')

# ── 4. OLS: sapm_r ~ pre_opp_glicko + C(division) -> residuals ───────────────
print('\nResidualising sapm_r on pre_opp_glicko + C(division) ...')

# Build design matrix manually to avoid patsy unicode issues on Windows
div_dummies = pd.get_dummies(df_reg['division'], drop_first=True, dtype=float)
X = pd.concat([
    pd.Series(1.0, index=df_reg.index, name='const'),
    df_reg['pre_opp_glicko'].rename('pre_opp_glicko'),
    div_dummies,
], axis=1)
y = df_reg['sapm_r']

mod  = sm.OLS(y, X).fit()
print(f'  N={len(y):,}  R2={mod.rsquared:.4f}')
print(f'  pre_opp_glicko: coef={mod.params["pre_opp_glicko"]:+.6f}  '
      f't={mod.tvalues["pre_opp_glicko"]:+.3f}  '
      f'p={mod.pvalues["pre_opp_glicko"]:.4f}')

df_reg = df_reg.copy()
df_reg['sapm_pre_r'] = mod.resid.values

# ── 5. Verification gate ──────────────────────────────────────────────────────
print('\n-- Verification gate (sapm_pre_r must vary per fighter) --')

per_fighter = df_reg.groupby('fighter')['sapm_pre_r'].nunique()
total   = len(per_fighter)
varying = (per_fighter > 1).sum()
frac    = varying / total
print(f'  Fighters with >1 distinct sapm_pre_r : {varying:,} / {total:,} ({frac:.2%})')

if frac < 0.50:
    print('GATE FAILED: residual is static. Do not proceed.')
    sys.exit(1)
print('  GATE PASSED')

# ── 6. Merge opponent side: sapm_pre_r_opp ───────────────────────────────────
print('\nMerging opponent sapm_pre_r ...')

# Need to know who the opponent is for each row.
# Join clean to get fighter_a, fighter_b, then derive opponent.
opp_map = clean[['fight_url', 'fighter_a', 'fighter_b']].copy()

df_reg = df_reg.merge(opp_map, on='fight_url', how='left')
df_reg['opponent'] = np.where(
    df_reg['fighter'] == df_reg['fighter_a'],
    df_reg['fighter_b'],
    df_reg['fighter_a']
)
df_reg = df_reg.drop(columns=['fighter_a', 'fighter_b'])

# Self-join on (fight_url, opponent == fighter)
opp_side = df_reg[['fight_url', 'fighter', 'sapm_pre_r']].rename(
    columns={'fighter': 'opponent', 'sapm_pre_r': 'sapm_pre_r_opp'}
)
df_reg = df_reg.merge(opp_side, on=['fight_url', 'opponent'], how='left')

n_opp = df_reg['sapm_pre_r_opp'].notna().sum()
print(f'  sapm_pre_r_opp non-null : {n_opp:,} / {len(df_reg):,} ({100*n_opp/len(df_reg):.1f}%)')

# ── 7. Save ───────────────────────────────────────────────────────────────────
out_cols = [
    'fight_url', 'date', 'fighter', 'opponent',
    'sapm_r', 'pre_opp_glicko', 'division',
    'sapm_pre_r', 'sapm_pre_r_opp'
]
df_reg[out_cols].to_csv(OUT, index=False)
print(f'\nSaved: {OUT}')
print(f'  Shape: {df_reg[out_cols].shape}')

# ── 8. Summary stats ──────────────────────────────────────────────────────────
print('\n-- Summary stats --')
for col in ['sapm_r', 'sapm_pre_r', 'sapm_pre_r_opp', 'pre_opp_glicko']:
    d = df_reg[col].describe()
    print(f'  {col:20s}  mean={d["mean"]:+7.3f}  std={d["std"]:.3f}  '
          f'min={d["min"]:+7.3f}  max={d["max"]:+7.3f}')

print('\nDone.')
