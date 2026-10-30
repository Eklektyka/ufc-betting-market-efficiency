#!/usr/bin/env python3
"""
Deep dive on the long-layoff pattern from residual mining.
Mining set only — holdout untouched.
"""
import sys, os, re, math, warnings, functools, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 1000

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

RESULTS_DIR = Path('mining_results')

# ═══════════════════════════════════════════════════════════════════
# REBUILD MINING SET (same pipeline as residual_mining.py)
# ═══════════════════════════════════════════════════════════════════
print("Loading and rebuilding mining set...")

panel = pd.read_csv(r'C:\Research\mma-paper\data\analysis_panel_cc.csv')
panel['date'] = pd.to_datetime(panel['date'])
panel = panel[panel['year'] <= 2025].copy()
panel['excess'] = panel['win'] - panel['p_close_hi']

MINING_CUTOFF = pd.Timestamp('2023-01-01')
mining = panel[panel['date'] < MINING_CUTOFF].copy()
mining = mining.sort_values('date').reset_index(drop=True)
mining['residual'] = mining['win'] - mining['p_close_hi']

print(f"  Mining set: {len(mining)} rows, {mining['date'].min().date()} to {mining['date'].max().date()}")

# ═══════════════════════════════════════════════════════════════════
# 1. UNCONDITIONED RULE — LAYOFF THRESHOLDS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("1. UNCONDITIONED RULE — LAYOFF THRESHOLDS")
print("=" * 80)

def report_subgroup(df, mask, label):
    sub = df[mask]
    n = len(sub)
    if n == 0:
        print(f"  {label}: N=0")
        return
    resid = sub['residual'].values
    mean_r = resid.mean()
    boots = [resid[rng.choice(n, n, True)].mean() for _ in range(N_BOOT)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    excl = "yes" if (lo > 0 or hi < 0) else "no"

    # Flat-bet ROI: bet on this fighter at fair odds (1/p_close), collect if win
    profits = (1 / sub['p_close_hi'].values) * sub['win'].values - 1
    roi = profits.mean()
    # ROI after ~5% vig: approximate by multiplying payout by 0.95
    profits_vig = (0.95 / sub['p_close_hi'].values) * sub['win'].values - 1
    roi_vig = profits_vig.mean()

    print(f"  {label}:")
    print(f"    N={n}, mean residual={mean_r:+.3f} [{lo:+.3f},{hi:+.3f}] CI excl 0: {excl}")
    print(f"    Flat-bet ROI (fair): {roi:+.1%}, ROI (after 5% vig): {roi_vig:+.1%}")

report_subgroup(mining, mining['layoff_days'] > 365, "layoff > 365 days (1 year)")
report_subgroup(mining, mining['layoff_days'] > 545, "layoff > 545 days (1.5 years)")
report_subgroup(mining, mining['layoff_days'] > 730, "layoff > 730 days (2 years)")
report_subgroup(mining, mining['layoff_days'] > 1000, "layoff > 1000 days (2.7 years)")

# ═══════════════════════════════════════════════════════════════════
# 2. TAIL THINNESS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("2. TAIL THINNESS")
print("=" * 80)

for thresh in [365, 545, 730, 1000]:
    n = (mining['layoff_days'] > thresh).sum()
    pct = n / len(mining)
    print(f"  layoff > {thresh}: N={n} ({pct:.1%} of mining set)")

# Histogram
above365 = mining[mining['layoff_days'] > 365]['layoff_days'].values
plt.figure(figsize=(10, 5))
plt.hist(above365, bins=50, edgecolor='black', alpha=0.7)
plt.axvline(730, color='red', linestyle='--', linewidth=2, label='730 days')
plt.axvline(545, color='orange', linestyle='--', linewidth=1.5, label='545 days')
plt.xlabel('Layoff days')
plt.ylabel('Count')
plt.title('Distribution of layoff_days > 365 (mining set)')
plt.legend()
plt.tight_layout()
plt.savefig(RESULTS_DIR / 'layoff_histogram.png', dpi=150)
plt.close()
print(f"  Histogram saved to {RESULTS_DIR / 'layoff_histogram.png'}")

# Winsorised model comparison
print(f"\n  Winsorised model comparison:")
print(f"  Re-fitting residual model with layoff_days capped at 730...")

import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error

# Need to rebuild features (simplified — just the key ones)
fights_raw = pd.read_csv(r'C:\Research\mma-paper\data\ufcstats_fights.csv')
fights_raw['date'] = pd.to_datetime(fights_raw['date'], format='mixed')

# Minimal feature set (same as residual_mining but quicker)
# Use what's already in the panel + layoff
features = ['sapm_pre_r', 'sapm_pre_r_opp', 'p_close_hi', 'layoff_days']
X_orig = mining[features].fillna(0).copy()
X_capped = X_orig.copy()
X_capped['layoff_days'] = X_capped['layoff_days'].clip(upper=730)
y = mining['residual'].values

params = {
    'objective': 'regression', 'metric': 'mse', 'num_leaves': 31,
    'max_depth': 5, 'learning_rate': 0.05, 'min_child_samples': 50,
    'subsample': 0.8, 'colsample_bytree': 0.7, 'reg_alpha': 1.0,
    'reg_lambda': 1.0, 'verbose': -1, 'seed': SEED,
}

tscv = TimeSeriesSplit(n_splits=5)

for label, X in [("Original (uncapped)", X_orig), ("Capped at 730", X_capped)]:
    oof = np.full(len(y), np.nan)
    for train_idx, val_idx in tscv.split(X):
        dtrain = lgb.Dataset(X.iloc[train_idx], y[train_idx])
        dval = lgb.Dataset(X.iloc[val_idx], y[val_idx], reference=dtrain)
        model = lgb.train(params, dtrain, num_boost_round=500, valid_sets=[dval],
                          callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)])
        oof[val_idx] = model.predict(X.iloc[val_idx])
    mask = ~np.isnan(oof)
    mse_model = mean_squared_error(y[mask], oof[mask])
    mse_baseline = mean_squared_error(y[mask], np.zeros(mask.sum()))
    r2 = 1 - mse_model / mse_baseline
    print(f"    {label:<25s} OOF R²={r2:+.4f}")

# ═══════════════════════════════════════════════════════════════════
# 3. ERA STABILITY
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("3. ERA STABILITY")
print("=" * 80)

# Need >=15 long-layoff cases per era. Check counts first.
for label, ylo, yhi in [('2007-2013', 2007, 2013), ('2014-2018', 2014, 2018), ('2019-2022', 2019, 2022)]:
    era = mining[(mining['year'] >= ylo) & (mining['year'] <= yhi)]
    long = era[era['layoff_days'] > 730]
    print(f"  {label}: total={len(era)}, layoff>730={len(long)}")

# Adjust boundaries if needed
# Check if we need to shift
era_bounds = [('2007-2014', 2007, 2014), ('2015-2018', 2015, 2018), ('2019-2022', 2019, 2022)]
for label, ylo, yhi in era_bounds:
    era = mining[(mining['year'] >= ylo) & (mining['year'] <= yhi)]
    long = era[era['layoff_days'] > 730]
    if len(long) < 15:
        print(f"  ** {label} has only {len(long)} long-layoff cases, adjusting...")

# Find working boundaries
print(f"\n  Adjusted era boundaries:")
eras = []
for label, ylo, yhi in [('2007-2015', 2007, 2015), ('2016-2019', 2016, 2019), ('2020-2022', 2020, 2022)]:
    era = mining[(mining['year'] >= ylo) & (mining['year'] <= yhi)]
    long = era[era['layoff_days'] > 730]
    eras.append((label, ylo, yhi, era, long))
    print(f"  {label}: total={len(era)}, layoff>730={len(long)}")

all_positive = True
print(f"\n  {'Era':<15s} {'N total':>8} {'N >730':>7} {'Residual':>9} {'CI':>20} {'Excl 0':>7}")
print("  " + "-" * 70)
for label, ylo, yhi, era, long in eras:
    if len(long) < 5:
        print(f"  {label:<15s} {len(era):>8} {len(long):>7} too few")
        continue
    resid = long['residual'].values
    mean_r = resid.mean()
    n = len(resid)
    boots = [resid[rng.choice(n, n, True)].mean() for _ in range(N_BOOT)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    excl = "yes" if (lo > 0 or hi < 0) else "no"
    if mean_r <= 0:
        all_positive = False
    print(f"  {label:<15s} {len(era):>8} {n:>7} {mean_r:>+8.3f} [{lo:>+.3f},{hi:>+.3f}] {excl:>7}")

print(f"\n  Sign holds in all eras: {'YES' if all_positive else 'NO'}")

# ═══════════════════════════════════════════════════════════════════
# 4. COMPOSITION
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("4. COMPOSITION OF LAYOFF > 730 SUBGROUP")
print("=" * 80)

long_layoff = mining[mining['layoff_days'] > 730].copy()
rest = mining[mining['layoff_days'] <= 730].copy()

print(f"\n  {'Metric':<30s} {'Layoff >730':>15} {'Rest':>15}")
print("  " + "-" * 60)

n_ll = len(long_layoff)
fav_pct = (long_layoff['p_close_hi'] > 0.5).mean()
fav_pct_rest = (rest['p_close_hi'] > 0.5).mean()
print(f"  {'N':.<30s} {n_ll:>15} {len(rest):>15}")
print(f"  {'Share favorites':.<30s} {fav_pct:>14.0%} {fav_pct_rest:>14.0%}")
print(f"  {'Mean closing implied prob':.<30s} {long_layoff['p_close_hi'].mean():>14.3f} {rest['p_close_hi'].mean():>14.3f}")
print(f"  {'Actual win rate':.<30s} {long_layoff['win'].mean():>14.3f} {rest['win'].mean():>14.3f}")
print(f"  {'Mean layoff (days)':.<30s} {long_layoff['layoff_days'].mean():>14.0f} {rest['layoff_days'].mean():>14.0f}")

# Weight class distribution
wt_map = {
    "WOMEN'S STRAWWEIGHT": 115, "WOMEN'S FLYWEIGHT": 125, "WOMEN'S BANTAMWEIGHT": 135,
    "WOMEN'S FEATHERWEIGHT": 145, "FLYWEIGHT": 125, "BANTAMWEIGHT": 135,
    "FEATHERWEIGHT": 145, "LIGHTWEIGHT": 155, "WELTERWEIGHT": 170,
    "MIDDLEWEIGHT": 185, "LIGHT HEAVYWEIGHT": 205, "HEAVYWEIGHT": 265,
}
def div_to_wt(d):
    d_clean = str(d).replace(' BOUT', '').replace('UFC ', '').replace(' TITLE', '')
    for k, v in wt_map.items():
        if k in d_clean: return v
    return 170

long_layoff['wt'] = long_layoff['division'].apply(div_to_wt)
print(f"\n  Weight class distribution (layoff >730):")
for wt, cnt in long_layoff['wt'].value_counts().sort_index().items():
    print(f"    {wt:>5} lbs: {cnt:>3} ({cnt/n_ll:.0%})")

# Title fights
is_title = long_layoff['division'].str.contains('TITLE', na=False)
print(f"\n  Title fights: {is_title.sum()}/{n_ll} ({is_title.mean():.0%})")

# Top fighters in this subgroup
print(f"\n  Fighters in layoff >730 subgroup:")
print(f"  {'Fighter':<25s} {'Layoff':>7s} {'Mkt%':>5s} {'Won':>4s} {'Residual':>9s} {'Date':>12s}")
print("  " + "-" * 70)
for _, r in long_layoff.sort_values('layoff_days', ascending=False).head(25).iterrows():
    won = 'W' if r['win'] == 1 else 'L'
    print(f"  {r['fighter'][:24]:<25s} {r['layoff_days']:>6.0f}d {r['p_close_hi']:>4.0%} {won:>4s} "
          f"{r['residual']:>+8.3f} {str(r['date'])[:10]:>12s}")

# ═══════════════════════════════════════════════════════════════════
# 5. CONJUNCTION — MINED HALF VS NEGATION
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("5. CONJUNCTION: MINED CONDITION vs NEGATION")
print("=" * 80)

base_mask = mining['layoff_days'] > 730

# Use conditions available in the mining set panel columns

print(f"\n  Base: layoff > 730, N={base_mask.sum()}, residual={mining.loc[base_mask, 'residual'].mean():+.3f}")

cond_tests = [
    ('is_favorite (mkt > 50%)', mining['p_close_hi'] > 0.5),
    ('is_underdog (mkt <= 50%)', mining['p_close_hi'] <= 0.5),
    ('p_close <= 0.3', mining['p_close_hi'] <= 0.3),
    ('p_close > 0.3', mining['p_close_hi'] > 0.3),
    ('heavyweight (265)', mining['division'].str.contains('HEAVYWEIGHT', na=False) & ~mining['division'].str.contains('LIGHT', na=False)),
    ('not heavyweight', ~(mining['division'].str.contains('HEAVYWEIGHT', na=False) & ~mining['division'].str.contains('LIGHT', na=False))),
    ('pre-2017', mining['year'] <= 2017),
    ('post-2017', mining['year'] > 2017),
    ('sapm_pre_r < 0 (good)', mining['sapm_pre_r'] < 0),
    ('sapm_pre_r >= 0 (bad)', mining['sapm_pre_r'] >= 0),
]

print(f"\n  {'Condition':<30s} {'N':>5} {'Residual':>9} {'CI':>20} {'Excl 0':>7}")
print("  " + "-" * 75)

for cond_label, cond_mask in cond_tests:
    combined = base_mask & cond_mask
    n = combined.sum()
    if n < 5:
        print(f"  {cond_label:<30s} {n:>5} too few")
        continue
    resid = mining.loc[combined, 'residual'].values
    mean_r = resid.mean()
    boots = [resid[rng.choice(n, n, True)].mean() for _ in range(N_BOOT)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    excl = "yes" if (lo > 0 or hi < 0) else "no"
    print(f"  {cond_label:<30s} {n:>5} {mean_r:>+8.3f} [{lo:>+.3f},{hi:>+.3f}] {excl:>7}")

# ═══════════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VERDICT (three sentences)")
print("=" * 80)

uncond = mining.loc[base_mask, 'residual']
uncond_mean = uncond.mean()
uncond_boots = [uncond.values[rng.choice(len(uncond), len(uncond), True)].mean() for _ in range(N_BOOT)]
uncond_lo, uncond_hi = np.percentile(uncond_boots, [2.5, 97.5])
uncond_excl = uncond_lo > 0 or uncond_hi < 0

print(f"""
  1. Unconditioned effect: layoff >730 days, N={len(uncond)},
     residual={uncond_mean:+.3f} [{uncond_lo:+.3f},{uncond_hi:+.3f}],
     CI {'excludes' if uncond_excl else 'includes'} zero.

  2. Era stability: sign {'holds' if all_positive else 'does not hold'} across
     all three eras.

  3. The 730-day threshold: see the winsorised R2 comparison and the
     graded thresholds (365/545/730/1000) to judge whether the cutoff
     is a real discontinuity or a thin-tail artefact.
""")

# Save markdown
with open(RESULTS_DIR / 'layoff_deep_dive.md', 'w', encoding='utf-8') as f:
    f.write("# Long-Layoff Deep Dive\n\n")
    f.write("Mining set only. Holdout untouched.\n\n")
    f.write("See console output and layoff_histogram.png for full results.\n")
print(f"  Results saved to {RESULTS_DIR}")
