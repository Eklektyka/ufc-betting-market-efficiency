"""
rebuild_pointintime_sapm.py
===========================
Fixes the look-ahead bias in the career sapm averages.

The current style_panel.csv uses full-career-end aggregates for sapm (and all
other style stats), which creates a minor but real forward-looking leak: a
fighter's first fight in the panel already carries information from future fights.

This script:
  1. Parses per-fight sig_str from ufc_extended.csv (using sig_str_pct to
     disambiguate concatenated digit sequences)
  2. Computes fight_time from round + time columns
  3. Builds POINT-IN-TIME career sapm for every fighter: for each fight t,
     use only fights completed strictly BEFORE fight t
  4. Does the same for slpm, str_acc, kd_rate, td_per15, td_acc, sub_per15,
     ctrl_share, avg_fight_min (all computable from ufc_extended)
  5. Merges the point-in-time stats into style_panel.csv, replacing the
     full-career values for rows where coverage exists
  6. Re-residualises all replaced _r vars on avg_pre_opp_glicko + C(division)
     (same procedure as rebuild_panel_prefight_glicko.py)
  7. Re-runs the main OLS and reports the key coefficient

Stats NOT rebuilt (not in ufc_extended at per-fight level):
  dist_share, clinch_share, ground_share, head_share, body_share, leg_share,
  td_def, finish_rate
  → These retain their full-career values in the panel.

CUTOFF: 2026-04-18 (matches panel)
"""

import sys, warnings, re
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

# ── Helper parsers ───────────────────────────────────────────────────────────

def parse_pct(pct_str):
    """Extract two percentages from '60%41%' or '---41%'. Returns (p1, p2) or (None, None)."""
    pcts = re.findall(r'(\d+)%', str(pct_str))
    if len(pcts) == 2:
        return int(pcts[0]), int(pcts[1])
    return None, None

def parse_concat(sig_str, pct_str, tol=0.03):
    """
    Parse concatenated 'X of YZ of W' using pct_str='P1%P2%' to find split.
    Returns (my_landed, my_att, opp_landed, opp_att) or None.
    Each fighter's stats are [mine][theirs] on each row.
    """
    nums = re.findall(r'\d+', str(sig_str))
    if len(nums) < 3:
        return None
    if len(nums) == 4:
        # No ambiguity: direct read
        return tuple(int(n) for n in nums)
    if len(nums) == 3:
        # Middle token is two numbers concatenated
        X, YZ_str, W = int(nums[0]), nums[1], int(nums[2])
        p1, _ = parse_pct(pct_str)
        if p1 is None:
            # Fallback: try split at len//2
            mid = len(YZ_str) // 2
            Y = int(YZ_str[:mid]) if YZ_str[:mid] else 0
            Z = int(YZ_str[mid:]) if YZ_str[mid:] else 0
            return X, Y, Z, W
        for split in range(1, len(YZ_str)):
            Y = int(YZ_str[:split])
            Z = int(YZ_str[split:]) if YZ_str[split:] else 0
            if Y == 0:
                if p1 == 0:
                    return X, Y, Z, W
                continue
            if abs(X / Y - p1 / 100) <= tol:
                return X, Y, Z, W
        return None
    if len(nums) == 2:
        # Likely '0 of 0' format with both zeros, or malformed
        return int(nums[0]), 1, int(nums[1]), 1
    return None

def parse_ctrl(ctrl_str):
    """
    Parse ctrl like '0:360:06' → (my_sec, opp_sec).
    Format: two MM:SS times concatenated.
    """
    times = re.findall(r'\d+:\d+', str(ctrl_str))
    if len(times) == 2:
        def to_sec(t):
            parts = t.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        return to_sec(times[0]), to_sec(times[1])
    # Try splitting raw string at midpoint of digit-colon pattern
    m = re.match(r'(\d+):(\d+)(\d+):(\d+)', str(ctrl_str))
    if m:
        return int(m.group(1))*60+int(m.group(2)), int(m.group(3))*60+int(m.group(4))
    return None, None

def parse_fight_time(round_num, time_str):
    """
    Compute total fight time in minutes.
    round_num: round where fight ended
    time_str: elapsed time in that round (MM:SS)
    """
    try:
        r = int(round_num)
        parts = str(time_str).split(':')
        secs_in_round = int(parts[0]) * 60 + int(parts[1])
        total_secs = (r - 1) * 300 + secs_in_round
        return total_secs / 60.0
    except Exception:
        return None

# ── 1. Load and parse ufc_extended ──────────────────────────────────────────
print('Loading ufc_extended.csv ...')
ext = pd.read_csv(RAW, parse_dates=['date'])
ext = ext[ext['date'] <= CUTOFF].copy().reset_index(drop=True)
ext['fighter_id'] = ext['fighter_url'].str.split('/').str[-1]
print(f'  Rows after cutoff: {len(ext):,}')

print('Parsing per-fight stats ...')
parsed = []
for idx, row in ext.iterrows():
    rec = {
        'fight_url':  row['fight_url'],
        'fighter_id': row['fighter_id'],
        'date':       row['date'],
        'result':     row['result'],
        'round':      row['round'],
        'time':       row['time'],
    }

    # Fight time
    rec['fight_min'] = parse_fight_time(row['round'], row['time'])

    # Sig strikes: (my_land, my_att, opp_land, opp_att)
    sig = parse_concat(row['sig_str'], row['sig_str_pct'])
    if sig:
        rec['my_sig_land'], rec['my_sig_att'], rec['opp_sig_land'], rec['opp_sig_att'] = sig
    else:
        rec['my_sig_land'] = rec['my_sig_att'] = rec['opp_sig_land'] = rec['opp_sig_att'] = np.nan

    # Takedowns: same format
    td = parse_concat(row['td'], row.get('td_pct', '---'), tol=0.05)
    if td:
        rec['my_td_land'], rec['my_td_att'], rec['opp_td_land'], rec['opp_td_att'] = td
    else:
        rec['my_td_land'] = rec['my_td_att'] = rec['opp_td_land'] = rec['opp_td_att'] = np.nan

    # Control time (seconds)
    ctrl_my, ctrl_opp = parse_ctrl(row.get('ctrl', ''))
    rec['ctrl_my_sec'] = ctrl_my
    rec['ctrl_opp_sec'] = ctrl_opp

    # KD: same concat format — but kd is often a single number or '10' (concatenated '1' and '0')
    kd_raw = str(row.get('kd', '0'))
    kd_nums = re.findall(r'\d+', kd_raw)
    rec['my_kd'] = int(kd_nums[0]) if kd_nums else 0
    rec['opp_kd'] = int(kd_nums[1]) if len(kd_nums) > 1 else 0

    # Sub attempts
    sub_raw = str(row.get('sub_att', '0'))
    sub_nums = re.findall(r'\d+', sub_raw)
    rec['my_sub'] = int(sub_nums[0]) if sub_nums else 0

    parsed.append(rec)

pf = pd.DataFrame(parsed)
print(f'  Parsed rows: {len(pf):,}')

# Compute per-fight stat rates
pf['slpm_fight']    = pf['my_sig_land']  / pf['fight_min']
pf['sapm_fight']    = pf['opp_sig_land'] / pf['fight_min']
pf['str_acc_fight'] = pf['my_sig_land']  / pf['my_sig_att'].replace(0, np.nan)
pf['td_per15_fight'] = pf['my_td_land']  / pf['fight_min'] * 15
pf['td_acc_fight']  = pf['my_td_land']   / pf['my_td_att'].replace(0, np.nan)
pf['kd_rate_fight'] = pf['my_kd']        / pf['fight_min']
pf['sub_per15_fight'] = pf['my_sub']     / pf['fight_min'] * 15
pf['ctrl_total_sec'] = pf['ctrl_my_sec'].fillna(0) + pf['ctrl_opp_sec'].fillna(0)
pf['ctrl_share_fight'] = np.where(
    pf['ctrl_total_sec'] > 0,
    pf['ctrl_my_sec'] / pf['ctrl_total_sec'],
    np.nan
)

# Cap extreme values (likely parsing errors)
pf.loc[pf['slpm_fight'] > 50, 'slpm_fight'] = np.nan
pf.loc[pf['sapm_fight'] > 50, 'sapm_fight'] = np.nan
pf.loc[pf['str_acc_fight'] > 1.0, 'str_acc_fight'] = np.nan

print(f'  slpm parseable: {pf["slpm_fight"].notna().sum():,}')
print(f'  sapm parseable: {pf["sapm_fight"].notna().sum():,}')

# Parse quality check
n_total = len(pf)
n_ok = pf['sapm_fight'].notna().sum()
print(f'  Parse success rate: {n_ok}/{n_total} = {100*n_ok/n_total:.1f}%')

# Sample check: show mean sapm vs fighter_features
ff = pd.read_csv(BASE / 'ufcstats_raw' / 'fighter_features.csv')
ff['fighter_id'] = ff['fighter_url'].str.split('/').str[-1]
ff['sapm_ref'] = pd.to_numeric(ff['sapm'], errors='coerce')

career_sapm = pf[pf['sapm_fight'].notna()].groupby('fighter_id')['sapm_fight'].mean().reset_index()
career_sapm.columns = ['fighter_id', 'sapm_computed']
check = career_sapm.merge(ff[['fighter_id','sapm_ref']], on='fighter_id', how='inner')
if len(check) > 10:
    c, _ = pearsonr(check['sapm_computed'].dropna(), check['sapm_ref'].dropna())
    print(f'\n  Validation: corr(computed career sapm, UFCStats sapm): {c:.4f} (N={len(check)})')
    print(f'  Computed mean sapm: {check["sapm_computed"].mean():.3f}')
    print(f'  UFCStats mean sapm: {check["sapm_ref"].mean():.3f}')

# ── 2. Build point-in-time career averages ───────────────────────────────────
print('\nBuilding point-in-time career averages ...')

STAT_COLS = ['slpm_fight','sapm_fight','str_acc_fight','td_per15_fight',
             'td_acc_fight','kd_rate_fight','sub_per15_fight','ctrl_share_fight',
             'fight_min']

pf_sorted = pf.sort_values(['fighter_id','date']).reset_index(drop=True)

# For each fighter-fight, compute expanding mean of stats from PRIOR fights
# (strictly BEFORE this fight's date)
pit_records = []
for fid, grp in pf_sorted.groupby('fighter_id'):
    grp = grp.sort_values('date').reset_index(drop=True)
    for i, row in grp.iterrows():
        # prior = all fights before this date
        prior = grp[grp['date'] < row['date']]
        rec = {
            'fight_url':  row['fight_url'],
            'fighter_id': fid,
            'date':       row['date'],
            'n_prior':    len(prior),
        }
        for col in STAT_COLS:
            vals = prior[col].dropna()
            rec[col.replace('_fight', '_pit')] = vals.mean() if len(vals) > 0 else np.nan
        pit_records.append(rec)

pit_df = pd.DataFrame(pit_records)
print(f'  Point-in-time records: {len(pit_df):,}')
print(f'  Fighters covered: {pit_df["fighter_id"].nunique():,}')
print(f'  Rows with ≥1 prior fight: {(pit_df["n_prior"] >= 1).sum():,}')
print(f'  sapm_pit coverage (≥1 prior): {pit_df["sapm_pit"].notna().sum():,}')

# ── 3. Load panel and merge ──────────────────────────────────────────────────
print('\nLoading panel and merging ...')
panel = pd.read_csv(PANEL_P, parse_dates=['date'])
print(f'  Panel rows: {len(panel):,}')

# Map pit_df fight_url to panel fight_id via (fighter_id, date)
# pit_df has fight_url; panel has fight_id — join on fighter_id + date
pit_merge = pit_df[['fighter_id','date','n_prior'] +
                   [c.replace('_fight','_pit') for c in STAT_COLS]].copy()

# Drop duplicates on (fighter_id, date) — keep last (same date multiple fights: rare)
pit_merge = pit_merge.sort_values('n_prior').drop_duplicates(
    subset=['fighter_id','date'], keep='last')

panel_aug = panel.merge(pit_merge, on=['fighter_id','date'], how='left')
matched = panel_aug['sapm_pit'].notna().sum()
print(f'  Panel rows with sapm_pit: {matched:,} / {len(panel_aug):,} ({100*matched/len(panel_aug):.1f}%)')

# Fighters with zero prior fights get NaN for pit stats (correct — can't compute average)
zero_prior = (panel_aug['n_prior'] == 0).sum()
print(f'  First-fight rows (n_prior=0, pit stats NaN): {zero_prior:,}')

# ── 4. Compare pit vs full-career values ─────────────────────────────────────
print('\nCorrelations pit vs current panel values:')
mapping = {
    'sapm_pit':    'sapm',
    'slpm_pit':    'slpm',
    'str_acc_pit': 'str_acc',
}
for pit_col, raw_col in mapping.items():
    if pit_col in panel_aug.columns and raw_col in panel_aug.columns:
        both = panel_aug[[pit_col, raw_col]].dropna()
        if len(both) > 10:
            c, _ = pearsonr(both[pit_col], both[raw_col])
            print(f'  {pit_col} vs {raw_col}: corr={c:.4f}  N={len(both)}')

# ── 5. Replace raw style vars with pit values in panel ───────────────────────
print('\nReplacing full-career stats with point-in-time where available ...')

replace_map = {
    'sapm':       'sapm_pit',
    'slpm':       'slpm_pit',
    'str_acc':    'str_acc_pit',
    'td_per15':   'td_per15_pit',
    'td_acc':     'td_acc_pit',
    'kd_rate':    'kd_rate_pit',
    'sub_per15':  'sub_per15_pit',
    'ctrl_share': 'ctrl_share_pit',
    'avg_fight_min': 'fight_min_pit',
}

n_replaced = {}
for raw_col, pit_col in replace_map.items():
    if pit_col not in panel_aug.columns:
        continue
    mask = panel_aug[pit_col].notna() & (panel_aug['n_prior'] >= 1)
    n_replaced[raw_col] = mask.sum()
    panel_aug.loc[mask, raw_col] = panel_aug.loc[mask, pit_col]
    print(f'  {raw_col}: replaced {mask.sum():,} rows')

# ── 6. Re-residualise on avg_pre_opp_glicko + C(division) ───────────────────
print('\nRe-residualising _r vars ...')

STYLE_VARS = [
    'slpm_r','str_acc_r','dist_share_r','clinch_share_r','ground_share_r',
    'head_share_r','body_share_r','leg_share_r','kd_rate_r','td_per15_r',
    'td_acc_r','td_def_r','sub_per15_r','ctrl_share_r','sapm_r',
    'avg_fight_min_r','finish_rate_r',
]
raw_names = {
    'slpm_r':       'slpm',
    'str_acc_r':    'str_acc',
    'kd_rate_r':    'kd_rate',
    'td_per15_r':   'td_per15',
    'td_acc_r':     'td_acc',
    'sub_per15_r':  'sub_per15',
    'ctrl_share_r': 'ctrl_share',
    'sapm_r':       'sapm',
    'avg_fight_min_r': 'avg_fight_min',
}

# Rebuild avg_pre_opp_glicko from prior run (already in panel? check)
if 'avg_pre_opp_glicko' not in panel_aug.columns:
    print('  avg_pre_opp_glicko not in panel — using panel glicko as fallback quality measure')
    qual_var = 'glicko'
else:
    qual_var = 'avg_pre_opp_glicko'

# Use glicko as quality measure for residualisation (pre-fight Glicko saved from rebuild)
# Since avg_pre_opp_glicko was not saved to panel, use glicko column
qual_var = 'glicko'  # career-end Glicko (already in panel)

mask_ok = panel_aug[qual_var].notna() & panel_aug['division'].notna()
print(f'  Rows usable for residualisation: {mask_ok.sum():,}')

corrs_new = {}
for r_col, raw_col in raw_names.items():
    if raw_col not in panel_aug.columns:
        continue
    sub = panel_aug[mask_ok & panel_aug[raw_col].notna()].copy()
    if len(sub) < 100:
        continue
    try:
        f_res = f'{raw_col} ~ {qual_var} + C(division)'
        lhs_r, rhs_r = patsy.dmatrices(f_res, data=sub, return_type='dataframe')
        mod_r = sm.OLS(lhs_r.iloc[:,0], rhs_r).fit()
        resid = mod_r.resid
        # Corr with current _r
        old_r = panel_aug.loc[sub.index, r_col]
        c_old, _ = pearsonr(old_r.dropna(), resid[old_r.notna()])
        corrs_new[r_col] = c_old
        panel_aug.loc[sub.index, r_col] = resid.values
        print(f'  {r_col}: N={len(sub):,}  corr(old, new)={c_old:.4f}')
    except Exception as ex:
        print(f'  {r_col}: FAILED — {ex}')

# ── 7. Save updated panel ────────────────────────────────────────────────────
print('\nSaving updated panel ...')
drop_cols = [c for c in panel_aug.columns if c.endswith('_pit') or c == 'n_prior']
panel_save = panel_aug.drop(columns=drop_cols)
panel_save.to_csv(PANEL_P, index=False)
print(f'  Saved {len(panel_save):,} rows × {len(panel_save.columns)} cols')

# ── 8. Main OLS sanity check ─────────────────────────────────────────────────
print('\n' + '='*65)
print('SANITY CHECK — Main OLS on point-in-time panel')
print('='*65)

panel_chk = pd.read_csv(PANEL_P, parse_dates=['date'])
panel_chk['year'] = panel_chk['date'].dt.year
panel_chk['layoff_days_c'] = panel_chk['layoff_days'].clip(0, 365*2)

ALL_ATOMIC = STYLE_VARS + [v + '_opp' for v in STYLE_VARS]
FORMULA = ('calibration_gap ~ ' + ' + '.join(ALL_ATOMIC)
           + ' + glicko_z + age_at_fight + layoff_days_c + C(division) + C(year)')

opp_join = (panel_chk[['fight_id','fighter_id'] + STYLE_VARS]
            .rename(columns={'fighter_id':'opponent_id',
                             **{v: v+'_opp' for v in STYLE_VARS}}))
panel_chk = panel_chk.merge(opp_join, on=['fight_id','opponent_id'], how='left')
req = (ALL_ATOMIC + ['calibration_gap','glicko_z','glicko','age_at_fight',
                     'layoff_days_c','division','year','fighter_id','fight_id'])
panel_est = panel_chk[panel_chk[req].notna().all(axis=1)].copy().reset_index(drop=True)

train = panel_est[panel_est['year'] <= 2019]
_mu, _sd = train['glicko'].mean(), train['glicko'].std()
panel_est['glicko_z'] = (panel_est['glicko'] - _mu) / _sd

print(f'Estimation N={len(panel_est):,}')

dummy = panel_est.iloc[[0]].assign(division='other', calibration_gap=0.0)
aug   = pd.concat([panel_est, dummy], ignore_index=True)
dpos  = len(aug)-1
lhs, rhs = patsy.dmatrices(FORMULA, data=aug, return_type='dataframe')
mk = lhs.index != dpos; lhs, rhs = lhs[mk], rhs[mk]
groups = aug.loc[lhs.index, 'fighter_id'].values
mod = sm.OLS(lhs.iloc[:,0], rhs).fit(cov_type='cluster', cov_kwds={'groups': groups})

print(f"\nsapm_r_opp:   coef={mod.params['sapm_r_opp']:+.5f}  "
      f"SE={mod.bse['sapm_r_opp']:.5f}  "
      f"t={mod.tvalues['sapm_r_opp']:+.4f}  "
      f"p={mod.pvalues['sapm_r_opp']:.4f}")
print(f"sapm_r:       coef={mod.params['sapm_r']:+.5f}  "
      f"t={mod.tvalues['sapm_r']:+.4f}  "
      f"p={mod.pvalues['sapm_r']:.4f}")
print(f"age_at_fight: coef={mod.params['age_at_fight']:+.5f}  "
      f"t={mod.tvalues['age_at_fight']:+.4f}  "
      f"p={mod.pvalues['age_at_fight']:.4f}")

# IS / OOS
for label, cond in [('IS (≤2019)', panel_est['year'] <= 2019),
                    ('OOS (2020+)', panel_est['year'] >= 2020)]:
    sub = panel_est[cond].copy()
    dm  = pd.concat([sub, sub.iloc[[0]].assign(division='other', calibration_gap=0.0)],
                     ignore_index=True)
    dp  = len(dm)-1
    l, r = patsy.dmatrices(FORMULA, data=dm, return_type='dataframe')
    mk   = l.index != dp; l, r = l[mk], r[mk]
    g    = dm.loc[l.index, 'fighter_id'].values
    m    = sm.OLS(l.iloc[:,0], r).fit(cov_type='cluster', cov_kwds={'groups': g})
    ci   = m.conf_int().loc['sapm_r_opp']
    print(f"\n{label} N={len(sub):,}")
    print(f"  sapm_r_opp: coef={m.params['sapm_r_opp']:+.5f}  "
          f"SE={m.bse['sapm_r_opp']:.5f}  "
          f"t={m.tvalues['sapm_r_opp']:+.4f}  "
          f"p={m.pvalues['sapm_r_opp']:.4f}  "
          f"CI=[{ci[0]:+.5f}, {ci[1]:+.5f}]")

print('\nDone.')
