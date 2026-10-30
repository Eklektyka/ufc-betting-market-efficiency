"""
rebuild_panel_from_clean_totals.py
===================================
Rebuilds the style panel from scratch using fight_totals_clean.csv (17,458 rows,
2 rows per fight, each fighter's stats already correctly separated).

Steps:
  1a. Load fight_totals_clean.csv, parse date/time/round
  1b. Compute per-fight stats (slpm, sapm, str_acc, etc.)
  1c. Build EXPANDING pre-fight means (shift(1) on cumulative mean)
  1d. Merge with style_panel.csv on fighter_id + date to get market vars
  1e. Print row counts at each stage
  1f. Write to preliminary results/style_panel_clean.csv

Key insight: fighter_id in style_panel = last slug of fighter_url in fight_totals
Merge key: fighter_id (slug) + date (fighter may have multiple fights on same date → use fight_id tiebreak)
"""

import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from pathlib import Path

BASE     = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis')
TOTALS_P = BASE / 'ufcstats_raw' / 'fight_totals_clean.csv'
PANEL_P  = BASE / 'preliminary results' / 'style_panel.csv'
OUT_P    = BASE / 'preliminary results' / 'style_panel_clean.csv'

# ── Helper ───────────────────────────────────────────────────────────────────

def parse_time(t):
    """'M:SS' → minutes as float"""
    try:
        parts = str(t).split(':')
        return int(parts[0]) + int(parts[1]) / 60.0
    except Exception:
        return np.nan

# ── 1a. Load fight_totals_clean ──────────────────────────────────────────────
print('=' * 65)
print('STEP 1a — Loading fight_totals_clean.csv')
print('=' * 65)

ft = pd.read_csv(TOTALS_P)
n_raw = len(ft)
print(f'  Raw rows loaded: {n_raw:,}')
print(f'  Columns: {list(ft.columns)}')

# Parse date
ft['date'] = pd.to_datetime(ft['date'], format='mixed', errors='coerce')
n_bad_date = ft['date'].isna().sum()
if n_bad_date > 0:
    print(f'  WARNING: {n_bad_date} rows with unparseable dates dropped')
    ft = ft[ft['date'].notna()].copy()

# Parse round and time
ft['round_num'] = pd.to_numeric(ft['round'], errors='coerce')
ft['time_min']  = ft['time'].apply(parse_time)

# Fight duration in minutes: (round-1)*5 + time_in_round
ft['fight_min'] = (ft['round_num'] - 1) * 5.0 + ft['time_min']
ft['fight_min'] = ft['fight_min'].clip(lower=0.1)  # avoid division by zero

# fighter_id = last slug of fighter_url
ft['fighter_id']      = ft['fighter_url'].str.split('/').str[-1]
ft['fighter_id_opp']  = ft['fighter_url_opp'].str.split('/').str[-1]
ft['fight_id_slug']   = ft['fight_url'].str.split('/').str[-1]

# Numeric conversions
for col in ['kd', 'sig_str_landed', 'sig_str_att', 'total_str_landed', 'total_str_att',
            'td_landed', 'td_att', 'sub_att', 'rev', 'ctrl_sec']:
    ft[col] = pd.to_numeric(ft[col], errors='coerce')

print(f'  Date range: {ft["date"].min().date()} → {ft["date"].max().date()}')
print(f'  Unique fights: {ft["fight_url"].nunique():,}')
print(f'  Unique fighters: {ft["fighter_id"].nunique():,}')

# ── 1b. Compute per-fight stats ───────────────────────────────────────────────
print()
print('=' * 65)
print('STEP 1b — Computing per-fight stats')
print('=' * 65)

# For absorbed strikes (sapm), we need opponent's sig_str_landed.
# Each fight has exactly 2 rows. For fighter A: absorbed = fighter B's sig_str_landed.
# Build opponent-stats merge table.
opp_stats = ft[['fight_url', 'fighter_url', 'sig_str_landed', 'sig_str_att',
                 'td_landed', 'td_att', 'ctrl_sec']].copy()
opp_stats = opp_stats.rename(columns={
    'fighter_url':    'fighter_url_opp',
    'sig_str_landed': 'opp_sig_str_landed',
    'sig_str_att':    'opp_sig_str_att',
    'td_landed':      'opp_td_landed',
    'td_att':         'opp_td_att',
    'ctrl_sec':       'opp_ctrl_sec',
})

# Merge back: each row gets opponent stats
ft2 = ft.merge(opp_stats, on=['fight_url', 'fighter_url_opp'], how='left')

n_after_opp = len(ft2)
print(f'  Rows after opponent-stats merge: {n_after_opp:,}  (expected {n_raw:,})')

# Per-fight stat computations
ft2['slpm_fight']       = ft2['sig_str_landed'] / ft2['fight_min']
ft2['sapm_fight']       = ft2['opp_sig_str_landed'] / ft2['fight_min']
ft2['str_acc_fight']    = np.where(ft2['sig_str_att'] > 0,
                                    ft2['sig_str_landed'] / ft2['sig_str_att'], np.nan)
ft2['str_def_fight']    = np.where(ft2['opp_sig_str_att'] > 0,
                                    1.0 - ft2['opp_sig_str_landed'] / ft2['opp_sig_str_att'], np.nan)
ft2['td_per15_fight']   = ft2['td_landed'] / ft2['fight_min'] * 15.0
ft2['td_acc_fight']     = np.where(ft2['td_att'] > 0,
                                    ft2['td_landed'] / ft2['td_att'], np.nan)
ft2['td_def_fight']     = np.where(ft2['opp_td_att'] > 0,
                                    1.0 - ft2['opp_td_landed'] / ft2['opp_td_att'], np.nan)
ft2['sub_per15_fight']  = ft2['sub_att'] / ft2['fight_min'] * 15.0
ft2['kd_per15_fight']   = ft2['kd'] / ft2['fight_min'] * 15.0
ctrl_total = ft2['ctrl_sec'].fillna(0) + ft2['opp_ctrl_sec'].fillna(0)
ft2['ctrl_share_fight'] = np.where(ctrl_total > 0,
                                    ft2['ctrl_sec'] / ctrl_total, np.nan)
ft2['avg_fight_min_fight'] = ft2['fight_min']

# Finish indicator
ft2['finish_fight'] = ft2['method'].str.contains(
    r'KO|TKO|Submission', case=False, na=False).astype(float)

# Cap extreme outliers (likely parsing errors)
for col in ['slpm_fight', 'sapm_fight']:
    ft2.loc[ft2[col] > 50, col] = np.nan
for col in ['str_acc_fight', 'str_def_fight']:
    ft2.loc[ft2[col] > 1.0, col] = np.nan
for col in ['td_acc_fight', 'td_def_fight']:
    ft2.loc[ft2[col] > 1.0, col] = np.nan

STAT_COLS = [
    'sapm_fight', 'slpm_fight', 'str_acc_fight', 'str_def_fight',
    'td_per15_fight', 'td_acc_fight', 'td_def_fight',
    'sub_per15_fight', 'kd_per15_fight', 'ctrl_share_fight',
    'avg_fight_min_fight', 'finish_fight'
]

for col in STAT_COLS:
    n_ok = ft2[col].notna().sum()
    print(f'  {col}: {n_ok:,} non-null ({100*n_ok/len(ft2):.1f}%)')

# ── 1c. Expanding pre-fight means ────────────────────────────────────────────
print()
print('=' * 65)
print('STEP 1c — Building expanding pre-fight means')
print('=' * 65)

# Sort by fighter + date
ft2 = ft2.sort_values(['fighter_id', 'date', 'fight_url']).reset_index(drop=True)

# Compute expanding cumulative mean, then shift(1) to get PRIOR fights only
PREFIGHT_MAP = {
    'sapm_fight':        'sapm',
    'slpm_fight':        'slpm',
    'str_acc_fight':     'str_acc',
    'str_def_fight':     'str_def',
    'td_per15_fight':    'td_per15',
    'td_acc_fight':      'td_acc',
    'td_def_fight':      'td_def',
    'sub_per15_fight':   'sub_per15',
    'kd_per15_fight':    'kd_rate',
    'ctrl_share_fight':  'ctrl_share',
    'avg_fight_min_fight': 'avg_fight_min',
    'finish_fight':      'finish_rate',
}

for fight_col, prefight_name in PREFIGHT_MAP.items():
    cum_col  = f'{fight_col}_cum'
    pf_col   = f'{prefight_name}_prefight'
    ft2[cum_col] = (ft2.groupby('fighter_id')[fight_col]
                       .expanding().mean()
                       .reset_index(level=0, drop=True))
    ft2[pf_col]  = ft2.groupby('fighter_id')[cum_col].shift(1)

PREFIGHT_COLS = [f'{v}_prefight' for v in PREFIGHT_MAP.values()]

# Count coverage
for col in PREFIGHT_COLS:
    n_ok = ft2[col].notna().sum()
    print(f'  {col}: {n_ok:,} non-null ({100*n_ok/len(ft2):.1f}%)')

print(f'  Rows with all prefight stats: '
      f'{ft2[PREFIGHT_COLS].notna().all(axis=1).sum():,}')

# ── 1d. Merge with style_panel ───────────────────────────────────────────────
print()
print('=' * 65)
print('STEP 1d — Merging with style_panel.csv')
print('=' * 65)

panel = pd.read_csv(PANEL_P, parse_dates=['date'])
n_panel = len(panel)
print(f'  style_panel rows: {n_panel:,}')
print(f'  style_panel fighter_ids: {panel["fighter_id"].nunique():,}')
print(f'  style_panel fight_ids: {panel["fight_id"].nunique():,}')

# Add panel variables we need in the output
PANEL_KEEP = [
    'fight_id', 'fighter_id', 'opponent_id', 'date', 'division',
    'title_fight', 'method', 'corner', 'won', 'age_at_fight', 'layoff_days',
    'market_prob_shin', 'market_prob_prop', 'market_prob_shin_open',
    'q_close', 'q_open', 'calibration_gap', 'glicko', 'glicko_z',
    # Keep original style vars for reference / comparison
    'slpm', 'str_acc', 'sapm', 'kd_rate', 'td_per15', 'td_acc', 'td_def',
    'sub_per15', 'ctrl_share', 'avg_fight_min', 'finish_rate',
    # Already-residualised vars (for reference)
    'slpm_r', 'str_acc_r', 'kd_rate_r', 'td_per15_r', 'td_acc_r', 'td_def_r',
    'sub_per15_r', 'ctrl_share_r', 'sapm_r', 'avg_fight_min_r', 'finish_rate_r',
    # Positional vars (not rebuilt)
    'dist_share', 'clinch_share', 'ground_share',
    'head_share', 'body_share', 'leg_share',
    'dist_share_r', 'clinch_share_r', 'ground_share_r',
    'head_share_r', 'body_share_r', 'leg_share_r',
    # Composite vars
    'td_edge', 'anti_td_edge', 'drag_down', 'pace_durability',
    'ctrl_scramble', 'ground_exploit', 'ko_power_chin', 'stance_mismatch',
    'fight_min',
]
# Keep only cols that exist
PANEL_KEEP = [c for c in PANEL_KEEP if c in panel.columns]
panel_sub = panel[PANEL_KEEP].copy()

# Merge on fighter_id + date
# fighter_id in panel = last slug of fighter_url in fight_totals
# Use fight_id_slug as tiebreak for same-day fights via fight_id cross-reference

# The panel fight_id is from BFO and does NOT equal fight_url slug.
# We merge on fighter_id + date, then handle duplicates.

# For fight_totals: keep only one row per (fighter_id, date) for merging —
# actually we want to merge ALL rows. Multiple fights on same date are rare.
# Use left merge: panel (left) + fight_totals pre-fight stats (right)

ft_for_merge = ft2[['fighter_id', 'date', 'fight_url'] + PREFIGHT_COLS].copy()
ft_for_merge = ft_for_merge.rename(columns={'fight_url': 'fight_url_ufc'})

# Deduplicate ft_for_merge on (fighter_id, date): if same fighter fought twice on
# same date (essentially impossible), keep first. The sort by fight_url ensures stability.
ft_for_merge_dedup = ft_for_merge.drop_duplicates(subset=['fighter_id', 'date'], keep='first')

panel_aug = panel_sub.merge(
    ft_for_merge_dedup,
    on=['fighter_id', 'date'],
    how='left'
)

n_after_merge = len(panel_aug)
n_with_prefight = panel_aug[PREFIGHT_COLS[0]].notna().sum()
print(f'  Rows after merge: {n_after_merge:,}  (panel rows: {n_panel:,})')
print(f'  Panel rows with pre-fight sapm: {n_with_prefight:,} '
      f'({100*n_with_prefight/n_after_merge:.1f}%)')

# Missing merge analysis
n_missing = n_after_merge - n_with_prefight
print(f'  Panel rows WITHOUT pre-fight stats: {n_missing:,}')
if n_missing > 0:
    miss_dates = panel_aug[panel_aug[PREFIGHT_COLS[0]].isna()]['date'].dt.year.value_counts().head(10)
    print(f'  Missing by year:\n{miss_dates}')

# ── 1e. Row counts ───────────────────────────────────────────────────────────
print()
print('=' * 65)
print('STEP 1e — Row count summary')
print('=' * 65)

print(f'  fight_totals_clean rows:         {n_raw:,}')
print(f'  Per-fight stat rows:             {len(ft2):,}')
print(f'  style_panel rows:                {n_panel:,}')
print(f'  After merge:                     {n_after_merge:,}')

# Estimation sample: drop NaN on key vars
est_vars = PREFIGHT_COLS + ['calibration_gap', 'market_prob_shin', 'q_close',
                             'glicko_z', 'glicko', 'age_at_fight', 'layoff_days',
                             'won', 'division', 'fight_id', 'fighter_id']
est_vars = [v for v in est_vars if v in panel_aug.columns]
panel_aug['layoff_days_c'] = panel_aug['layoff_days'].clip(0, 365 * 2)
est_vars_check = [v for v in est_vars if v != 'layoff_days']
est_vars_check.append('layoff_days_c')

panel_est_preview = panel_aug[panel_aug[est_vars_check].notna().all(axis=1)]
print(f'  Estimation sample (pre-resid):   {len(panel_est_preview):,}')

# ── 1f. Write output ─────────────────────────────────────────────────────────
print()
print('=' * 65)
print('STEP 1f — Writing style_panel_clean.csv')
print('=' * 65)

panel_aug.to_csv(OUT_P, index=False)
print(f'  Written: {OUT_P}')
print(f'  Rows: {len(panel_aug):,}')
print(f'  Columns: {len(panel_aug.columns)}')
print(f'  Columns list: {list(panel_aug.columns)}')

print()
print('rebuild_panel_from_clean_totals.py — COMPLETE')
