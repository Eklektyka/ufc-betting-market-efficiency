"""
run_manifest_c7c8.py
====================
Computes manifest items C7 (univariate Romano-Wolf over 41 candidates)
and C8 (actual overround on top-decile OOS bets) on the clean pre-fight panel.

Uses:
  - sapm_r_final: division-only residualisation of sapm_prefight
  - Other _r vars: existing panel values (with note where contaminated)
  - Opponent versions via fight_id self-merge
"""

import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
from pathlib import Path

SEED   = 42
N_PERM = 5_000
rng    = np.random.default_rng(SEED)

BASE    = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis')
OUT_DIR = BASE / 'preliminary results'

# ── 1. Load panel ──────────────────────────────────────────────────────────
print('Loading panel...')
panel = pd.read_csv(OUT_DIR / 'style_panel_clean.csv', low_memory=False, parse_dates=['date'])
panel['year']          = panel['date'].dt.year
panel['layoff_days_c'] = panel['layoff_days'].clip(0, 365 * 2)
print(f'Panel: {panel.shape}')

# ── 2. Build clean residualised vars for the 12 prefight vars ──────────────
PREFIGHT_MAP = {
    'sapm_r':          'sapm_prefight',
    'slpm_r':          'slpm_prefight',
    'str_acc_r':       'str_acc_prefight',
    'str_def_r':       'str_def_prefight',
    'kd_rate_r':       'kd_rate_prefight',
    'td_per15_r':      'td_per15_prefight',
    'td_acc_r':        'td_acc_prefight',
    'td_def_r':        'td_def_prefight',
    'sub_per15_r':     'sub_per15_prefight',
    'ctrl_share_r':    'ctrl_share_prefight',
    'avg_fight_min_r': 'avg_fight_min_prefight',
    'finish_rate_r':   'finish_rate_prefight',
}

for r_col, pf_col in PREFIGHT_MAP.items():
    clean_col = r_col + '_clean'
    panel[clean_col] = np.nan
    sub = panel[pf_col].notna() & panel['division'].notna()
    if sub.sum() > 0:
        m = smf.ols(f'{pf_col} ~ C(division)', panel[sub]).fit()
        panel.loc[panel[sub].index, clean_col] = m.resid

print(f'Built clean _r for {len(PREFIGHT_MAP)} vars via division residualisation')
print(f'sapm_r_clean coverage: {panel["sapm_r_clean"].notna().sum()}')

# ── 3. Build 41-candidate list ─────────────────────────────────────────────
# For vars with clean prefight version, use _clean; else use existing _r
# Position/target share vars (dist_share, clinch_share, ground_share,
# head_share, body_share, leg_share) only have contaminated _r — use as-is.

CLEAN_VARS = list(PREFIGHT_MAP.keys())   # 12 vars with clean equivalents

# Full STYLE_VARS from original analysis (17 vars)
STYLE_VARS_ORIG = [
    'slpm_r', 'str_acc_r', 'dist_share_r', 'clinch_share_r', 'ground_share_r',
    'head_share_r', 'body_share_r', 'leg_share_r', 'kd_rate_r', 'td_per15_r',
    'td_acc_r', 'td_def_r', 'sub_per15_r', 'ctrl_share_r', 'sapm_r',
    'avg_fight_min_r', 'finish_rate_r',
]

# Create a working version: for clean vars, replace with _clean version
STYLE_VARS_WORK = []
for v in STYLE_VARS_ORIG:
    if v in PREFIGHT_MAP:
        wv = v + '_clean'
        panel[wv] = panel[v + '_clean']   # already exists
        STYLE_VARS_WORK.append(wv)
    else:
        STYLE_VARS_WORK.append(v)  # contaminated but no alternative

# Build opponent versions via fight_id merge
opp_src = panel[['fight_id', 'fighter_id'] + STYLE_VARS_WORK].copy()
opp_src_renamed = opp_src.rename(columns={
    'fighter_id': 'opponent_id',
    **{v: v + '_opp' for v in STYLE_VARS_WORK}
})
panel = panel.merge(opp_src_renamed, on=['fight_id', 'opponent_id'], how='left')

ALL_ATOMIC = STYLE_VARS_WORK + [v + '_opp' for v in STYLE_VARS_WORK]  # 34

COMPOSITE = [
    'td_edge', 'anti_td_edge', 'drag_down', 'pace_durability',
    'ctrl_scramble', 'ground_exploit', 'ko_power_chin',
]  # 7

CANDIDATES = ALL_ATOMIC + COMPOSITE  # 41
print(f'\nCandidates: {len(CANDIDATES)}')
print(f'Key candidate: sapm_r_clean_opp present: {"sapm_r_clean_opp" in panel.columns}')

CONTROLS = ['glicko_z', 'age_at_fight', 'layoff_days_c']

# ── 4. Estimation sample ───────────────────────────────────────────────────
need = CANDIDATES + ['calibration_gap', 'glicko_z', 'age_at_fight',
                     'layoff_days_c', 'division', 'year', 'fighter_id', 'date']
# Only keep cols that exist
need_exist = [c for c in need if c in panel.columns]
missing_need = [c for c in need if c not in panel.columns]
if missing_need:
    print(f'Missing needed cols: {missing_need}')
    # Remove from candidates
    CANDIDATES = [c for c in CANDIDATES if c not in missing_need]

est = panel[need_exist].copy()
est_date = est['date'].copy()
est = est.dropna(subset=[c for c in CANDIDATES if c in est.columns] +
                 ['calibration_gap', 'glicko_z', 'age_at_fight', 'layoff_days_c'])
print(f'Estimation sample N={len(est):,}  '
      f'({est["date"].min().date()} to {est["date"].max().date()})')

# ── 5. Univariate regressions (with division + year dummies) ───────────────
print(f'\n=== C7: Univariate RW over {len(CANDIDATES)} candidates ===')

# Add dummies for division + year
est = pd.get_dummies(est, columns=['division', 'year'], drop_first=True, dtype=float)

y = est['calibration_gap'].values
div_year_cols = [c for c in est.columns if c.startswith('division_') or c.startswith('year_')]
ctrl_cols_base = ['glicko_z', 'age_at_fight', 'layoff_days_c']
ctrl_cols = [c for c in ctrl_cols_base if c in est.columns] + div_year_cols

# OLS t-stats for each candidate (univariate + controls)
t_obs = {}
coefs = {}
pvals = {}

X_ctrl = sm.add_constant(est[ctrl_cols].values)

for cand in CANDIDATES:
    if cand not in est.columns:
        continue
    x_c = est[cand].values.reshape(-1, 1)
    X_c = np.hstack([x_c, est[ctrl_cols].values])
    X_c = sm.add_constant(X_c)
    try:
        res = sm.OLS(y, X_c).fit()
        # candidate is column index 1 (after const)
        t_obs[cand] = res.tvalues[1]
        coefs[cand] = res.params[1]
        pvals[cand] = res.pvalues[1]
    except Exception as e:
        print(f'  Error {cand}: {e}')

print(f'Computed t-stats for {len(t_obs)} candidates')

# ── 6. Romano-Wolf stepdown ────────────────────────────────────────────────
print(f'Running RW stepdown with {N_PERM} permutations...')

cands_list = list(t_obs.keys())
t_abs = np.array([abs(t_obs[c]) for c in cands_list])

# Sort by |t| descending (step-down order)
order = np.argsort(-t_abs)
cands_sorted = [cands_list[i] for i in order]
t_sorted     = t_abs[order]

# Precompute X matrices for each candidate
X_mats = {}
for cand in cands_list:
    x_c = est[cand].values.reshape(-1, 1)
    X_c = np.hstack([x_c, est[ctrl_cols].values])
    X_c = sm.add_constant(X_c)
    X_mats[cand] = X_c

# Permutation null distribution (max t-stat in stepdown)
K = len(cands_sorted)
null_max = np.zeros((N_PERM, K))

for b in range(N_PERM):
    y_perm = rng.permutation(y)
    # Compute |t| for each candidate on permuted y
    t_perm = np.zeros(K)
    for ki, cand in enumerate(cands_sorted):
        Xc = X_mats[cand]
        try:
            XtX_inv = np.linalg.pinv(Xc.T @ Xc)
            beta = XtX_inv @ Xc.T @ y_perm
            resid = y_perm - Xc @ beta
            s2 = np.dot(resid, resid) / (len(y_perm) - Xc.shape[1])
            se = np.sqrt(s2 * np.diag(XtX_inv))
            t_perm[ki] = abs(beta[1] / se[1]) if se[1] > 0 else 0
        except Exception:
            t_perm[ki] = 0
    # Enforcing monotonicity: max from right
    for ki in range(K-2, -1, -1):
        t_perm[ki] = max(t_perm[ki], t_perm[ki+1])
    null_max[b] = t_perm
    if (b+1) % 1000 == 0:
        print(f'  {b+1}/{N_PERM}')

# RW p-values
rw_p = np.zeros(K)
for ki in range(K):
    rw_p[ki] = (null_max[:, ki] >= t_sorted[ki]).mean()
# Enforce monotonicity (non-decreasing p-values going down)
for ki in range(1, K):
    rw_p[ki] = max(rw_p[ki], rw_p[ki-1])

print('\n=== C7 RESULTS: Univariate RW41 (clean panel) ===')
print(f'{"Rank":<5} {"Variable":<30} {"Coef":>9} {"Naive p":>9} {"RW p":>9}')
print('-' * 65)
for ki, cand in enumerate(cands_sorted[:15]):
    print(f'{ki+1:<5} {cand:<30} {coefs.get(cand,0):>+9.5f} {pvals.get(cand,0):>9.4f} {rw_p[ki]:>9.4f}')

# Find sapm_r_clean_opp rank
sapm_cand = 'sapm_r_clean_opp'
if sapm_cand in cands_sorted:
    rank = cands_sorted.index(sapm_cand) + 1
    ki   = cands_sorted.index(sapm_cand)
    print(f'\n>>> sapm_r_clean_opp: rank {rank}/{K}, coef={coefs[sapm_cand]:+.5f}, '
          f'naive p={pvals[sapm_cand]:.4f}, RW p={rw_p[ki]:.4f} <<<')
else:
    print(f'\nWARNING: {sapm_cand} not found in results. Available sapm-like:',
          [c for c in cands_sorted if 'sapm' in c])

# Age rank
age_cand = 'age_at_fight'
if age_cand in t_obs:
    rank_a = cands_sorted.index(age_cand) + 1 if age_cand in cands_sorted else 'N/A'
    print(f'>>> age_at_fight: rank {rank_a}/{K}, coef={coefs.get(age_cand,0):+.5f}, '
          f'naive p={pvals.get(age_cand,0):.4f} <<<')
else:
    print('NOTE: age_at_fight is a control, not a candidate in this run')

# ── 7. C8: Actual overround on top-decile OOS bets ─────────────────────────
print('\n=== C8: Actual overround on top-decile OOS bets ===')

# We need the raw odds to compute overround
# Top-decile from IS model, applied OOS
oos_mask = panel['date'].dt.year >= 2020
is_mask  = panel['date'].dt.year < 2020

# Use sapm_r_clean_opp for top decile
if 'sapm_r_clean_opp' in panel.columns:
    threshold_col = 'sapm_r_clean_opp'
else:
    threshold_col = None

if threshold_col:
    is_data  = panel[is_mask & panel[threshold_col].notna() & panel['calibration_gap'].notna()]
    oos_data = panel[oos_mask & panel[threshold_col].notna() & panel['calibration_gap'].notna()]

    # IS 90th percentile threshold
    thresh_val = is_data[threshold_col].quantile(0.90)
    top_decile_oos = oos_data[oos_data[threshold_col] >= thresh_val]
    print(f'IS 90th percentile threshold: {thresh_val:.4f}')
    print(f'Top-decile OOS bets N={len(top_decile_oos)}')

    # Overround = 1 - (1/implied_prob_A + 1/implied_prob_B)
    # We have market_prob_shin (devigged). To get implied, we need raw odds.
    # Check for implied_prob columns
    imp_cols = [c for c in panel.columns if 'implied' in c.lower() or 'overround' in c.lower() or 'vig' in c.lower()]
    print(f'Implied/vig columns: {imp_cols}')

    # Check bfo_odds_devigged.csv for overround info
    bfo_path = BASE / 'bfo_odds_final' / 'bfo_odds_devigged.csv'
    if bfo_path.exists():
        bfo = pd.read_csv(bfo_path, low_memory=False)
        print(f'\nbfo_odds_devigged.csv shape: {bfo.shape}')
        print(f'Columns: {list(bfo.columns[:20])}')
    else:
        print(f'bfo_odds_devigged.csv not found at {bfo_path}')

print('\nDone.')
