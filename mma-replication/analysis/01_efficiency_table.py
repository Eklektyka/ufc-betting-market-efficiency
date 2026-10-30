#!/usr/bin/env python3
"""
Table 1: Efficiency summary — all models vs market benchmark.
Temporal split: train<=2020, validate 2021-23, test 2024-25.
Outputs: figures/table1_efficiency.csv
"""
import sys, math, warnings, functools
import numpy as np
import pandas as pd
from collections import defaultdict
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.metrics import brier_score_loss, log_loss, accuracy_score

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)

DATA_DIR = '../data'
OUT_DIR = '../figures'

# Load panel, de-duplicate to bout level
df = pd.read_csv(f'{DATA_DIR}/analysis_panel_cc.csv')
df['date'] = pd.to_datetime(df['date'])
paired = df.groupby('fight_id').filter(lambda x: len(x) == 2)

bouts = []
for fid, grp in paired.groupby('fight_id'):
    grp = grp.sort_values('fighter')
    r1 = grp.iloc[0]
    bouts.append({
        'fight_id': fid, 'date': r1['date'], 'year': r1['year'],
        'fa': r1['fighter'], 'fb': r1['opponent'],
        'rating_a': r1['sapm_pre_r'], 'rating_b': r1['sapm_pre_r_opp'],
        'layoff_a': r1['layoff_days'], 'layoff_b': grp.iloc[1]['layoff_days'],
        'p_mkt_a': r1['p_close_hi'], 'win_a': int(r1['win']),
    })
bouts = pd.DataFrame(bouts).sort_values('date').reset_index(drop=True)
bouts = bouts[bouts['year'] <= 2025]

test = bouts[(bouts['year'] >= 2024) & (bouts['year'] <= 2025)]
y_test = test['win_a'].values
mkt_test = test['p_mkt_a'].values

# Market benchmark
mkt_brier = brier_score_loss(y_test, mkt_test)
mkt_ll = log_loss(y_test, np.clip(mkt_test, 1e-6, 1-1e-6))
mkt_acc = accuracy_score(y_test, (mkt_test > 0.5).astype(int))

# Elo (K=40)
def run_elo(bouts_df, K):
    ratings = defaultdict(lambda: 1500.0)
    preds = []
    for _, row in bouts_df.iterrows():
        ra, rb = ratings[row['fa']], ratings[row['fb']]
        ea = 1 / (1 + 10**((rb - ra) / 400))
        preds.append(ea)
        sa = row['win_a']
        ratings[row['fa']] += K * (sa - ea)
        ratings[row['fb']] += K * ((1-sa) - (1-ea))
    return np.array(preds)

full = bouts.copy()
elo_preds = run_elo(full, 40)
test_mask = full['year'].isin([2024, 2025])
elo_test = elo_preds[test_mask.values]

# SAPM logistic
train_val = full[~test_mask]
def neg_ll(params, X, y):
    p = np.clip(expit(params[0] + params[1] * X), 1e-10, 1-1e-10)
    return -np.sum(y * np.log(p) + (1-y) * np.log(1-p))

X_tv = (train_val['rating_a'] - train_val['rating_b']).values
y_tv = train_val['win_a'].values
res = minimize(neg_ll, [0, 0.5], args=(X_tv, y_tv), method='Nelder-Mead')
X_te = (test['rating_a'] - test['rating_b']).values
sapm_test = expit(res.x[0] + res.x[1] * X_te)

# BT (rating + layoff)
bt_X_tv = np.column_stack([X_tv, np.log1p(train_val['layoff_a'].values) - np.log1p(train_val['layoff_b'].values)])
bt_X_te = np.column_stack([X_te, np.log1p(test['layoff_a'].values) - np.log1p(test['layoff_b'].values)])
def neg_ll_bt(params, X, y):
    z = params[0] + X @ params[1:]
    p = np.clip(expit(z), 1e-10, 1-1e-10)
    return -np.sum(y*np.log(p) + (1-y)*np.log(1-p))
res_bt = minimize(neg_ll_bt, [0,0,0], args=(bt_X_tv, y_tv), method='Nelder-Mead', options={'maxiter':10000})
bt_test = expit(res_bt.x[0] + bt_X_te @ res_bt.x[1:])

# BT + market (dominance check)
bt_mkt_X_tv = np.column_stack([bt_X_tv, train_val['p_mkt_a'].values])
bt_mkt_X_te = np.column_stack([bt_X_te, mkt_test])
res_btm = minimize(neg_ll_bt, [0,0,0,0], args=(bt_mkt_X_tv, y_tv), method='Nelder-Mead', options={'maxiter':10000})
btm_test = expit(res_btm.x[0] + bt_mkt_X_te @ res_btm.x[1:])

# Build results table
rows = []
for name, preds in [
    ('Market (closing line)', mkt_test),
    ('Elo (K=40)', elo_test),
    ('SAPM (logistic)', sapm_test),
    ('Bradley-Terry (rating+layoff)', bt_test),
    ('BT + market prob', btm_test),
]:
    pc = np.clip(preds, 1e-6, 1-1e-6)
    acc = accuracy_score(y_test, (preds > 0.5).astype(int))
    brier = brier_score_loss(y_test, pc)
    ll = log_loss(y_test, pc)
    delta = brier - mkt_brier
    rows.append({'Model': name, 'Accuracy': f'{acc:.1%}', 'Brier': f'{brier:.4f}',
                 'Log-loss': f'{ll:.4f}', 'vs Market Brier': f'{delta:+.4f}'})

table = pd.DataFrame(rows)
table.to_csv(f'{OUT_DIR}/table1_efficiency.csv', index=False)
print(table.to_string(index=False))
print(f"\nSaved to {OUT_DIR}/table1_efficiency.csv")
print(f"Test bouts: {len(y_test)} (2024-2025)")
