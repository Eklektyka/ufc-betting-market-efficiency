#!/usr/bin/env python3
"""International home advantage: non-US events, excluding US-vs-US fights."""
import sys, math, re, csv, json, warnings, functools, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.metrics import brier_score_loss

warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# Load wikidata fighters
wiki = pd.read_csv(r'C:\Research\ufc\odds\wikidata_mma_fighters.csv')
wiki_lookup = {}
for _, row in wiki.iterrows():
    nn = norm_name(row['name'])
    if nn not in wiki_lookup or (row['lat'] and not wiki_lookup[nn].get('lat')):
        wiki_lookup[nn] = row.to_dict()

# Load panel
panel = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\processed\analysis_panel_cc.csv')
panel['date'] = pd.to_datetime(panel['date'])
ufc_fighters = set(panel['fighter'].unique()) | set(panel['opponent'].unique())

# Match fighters to wikidata
matched = {}
for f in ufc_fighters:
    nn = norm_name(f)
    if nn in wiki_lookup:
        matched[f] = wiki_lookup[nn]
    else:
        parts = nn.split()
        if len(parts) >= 2:
            reversed_name = ' '.join(parts[1:] + parts[:1])
            if reversed_name in wiki_lookup:
                matched[f] = wiki_lookup[reversed_name]

# Load events for location
events = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_events.csv')
fights_raw = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv')
fight_to_event_url = dict(zip(fights_raw['fight_url'], fights_raw['event_url']))
event_url_to_loc = dict(zip(events['event_url'], events['location']))

ec_map = {
    'USA': 'United States', 'Brazil': 'Brazil', 'Canada': 'Canada',
    'United Kingdom': 'United Kingdom', 'Australia': 'Australia',
    'United Arab Emirates': 'United Arab Emirates', 'China': 'China',
    'Japan': 'Japan', 'Mexico': 'Mexico', 'France': 'France',
    'Germany': 'Germany', 'Netherlands': 'Netherlands', 'Sweden': 'Sweden',
    'Ireland': 'Ireland', 'South Korea': 'South Korea', 'Singapore': 'Singapore',
    'New Zealand': 'New Zealand', 'Poland': 'Poland', 'Saudi Arabia': 'Saudi Arabia',
    'Qatar': 'Qatar', 'Russia': 'Russia', 'Azerbaijan': 'Azerbaijan',
    'Denmark': 'Denmark', 'Philippines': 'Philippines', 'Indonesia': 'Indonesia',
    'Uruguay': 'Uruguay',
}

def get_event_country(loc_str):
    parts = [p.strip() for p in loc_str.split(',')]
    raw = parts[-1] if parts else ''
    return ec_map.get(raw, raw)

# Build fight method lookup (winner row only)
fight_method = {}
for _, row in fights_raw.iterrows():
    if row['result'] == 'W':
        fight_method[row['fight_url']] = row['method']

# Build bout-level dataset
paired = panel.groupby('fight_id').filter(lambda x: len(x) == 2)

bouts = []
for fid, grp in paired.groupby('fight_id'):
    grp = grp.sort_values('fighter')
    r1, r2 = grp.iloc[0], grp.iloc[1]
    fa, fb = r1['fighter'], r1['opponent']

    event_url = fight_to_event_url.get(r1['fight_url'])
    loc_str = event_url_to_loc.get(event_url, '') if event_url else ''
    if not loc_str:
        continue

    event_country = get_event_country(loc_str)
    country_a = matched.get(fa, {}).get('country', '')
    country_b = matched.get(fb, {}).get('country', '')
    if not country_a or not country_b:
        continue

    method = fight_method.get(r1['fight_url'], '')
    is_decision = 'DEC' in str(method).upper() or 'Decision' in str(method)

    bouts.append({
        'fight_id': fid, 'date': r1['date'], 'year': r1['year'],
        'fa': fa, 'fb': fb,
        'p_mkt_a': r1['p_close_hi'], 'win_a': int(r1['win']),
        'country_a': country_a, 'country_b': country_b,
        'event_country': event_country, 'event_loc': loc_str,
        'is_decision': is_decision, 'method': method,
        'home_a': 1 if country_a == event_country else 0,
        'home_b': 1 if country_b == event_country else 0,
    })

bouts = pd.DataFrame(bouts).sort_values('date').reset_index(drop=True)
bouts['home_diff'] = bouts['home_a'] - bouts['home_b']

print(f"Total bouts with both fighters' nationality: {len(bouts)}")
print(f"US events: {(bouts['event_country'] == 'United States').sum()}")
print(f"Non-US events: {(bouts['event_country'] != 'United States').sum()}")

# ═══════════════════════════════════════════════════════════════════
# FILTER: non-US events, exclude US-vs-US
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("INTERNATIONAL HOME ADVANTAGE")
print("Non-US events, excluding US-vs-US fights")
print(f"{'='*72}")

non_us = bouts[bouts['event_country'] != 'United States'].copy()
non_us = non_us[~((non_us['country_a'] == 'United States') &
                   (non_us['country_b'] == 'United States'))].copy()

print(f"\n  After filter: {len(non_us)} bouts")
print(f"  Year range: {non_us['year'].min()}-{non_us['year'].max()}")

has_home = non_us[(non_us['home_a'] == 1) | (non_us['home_b'] == 1)]
no_home = non_us[(non_us['home_a'] == 0) & (non_us['home_b'] == 0)]
both_home = non_us[(non_us['home_a'] == 1) & (non_us['home_b'] == 1)]
print(f"  Bouts with at least one home fighter: {len(has_home)} ({len(has_home)/len(non_us):.1%})")
print(f"  Bouts with no home fighter: {len(no_home)}")
print(f"  Bouts with both home (domestic matchup): {len(both_home)}")

# Exclude domestic matchups for clean home-vs-away comparison
clean = has_home[(has_home['home_a'] + has_home['home_b']) == 1].copy()
print(f"  Clean home-vs-away bouts: {len(clean)}")

# Breakdown by event country
print(f"\n  Event country breakdown (clean home-vs-away):")
for country, grp in sorted(clean.groupby('event_country'), key=lambda x: -len(x[1])):
    hw = sum(((grp['home_a'] == 1) & (grp['win_a'] == 1)) |
             ((grp['home_b'] == 1) & (grp['win_a'] == 0)))
    mkt_home = []
    for _, row in grp.iterrows():
        if row['home_a'] == 1:
            mkt_home.append(row['p_mkt_a'])
        else:
            mkt_home.append(1 - row['p_mkt_a'])
    mkt_avg = np.mean(mkt_home)
    print(f"    {country:<25s} {len(grp):>3} bouts, home wins: {hw}/{len(grp)} ({hw/len(grp):.0%}), mkt implied: {mkt_avg:.0%}")

# ═══════════════════════════════════════════════════════════════════
# HOME FIGHTER EXCESS WIN RATE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("HOME FIGHTER EXCESS (clean home-vs-away only)")
print(f"{'='*72}")

home_wins_arr = []
home_mkt_arr = []
for _, row in clean.iterrows():
    if row['home_a'] == 1:
        home_wins_arr.append(row['win_a'])
        home_mkt_arr.append(row['p_mkt_a'])
    else:
        home_wins_arr.append(1 - row['win_a'])
        home_mkt_arr.append(1 - row['p_mkt_a'])

home_wins_arr = np.array(home_wins_arr)
home_mkt_arr = np.array(home_mkt_arr)

print(f"\n  N: {len(home_wins_arr)}")
print(f"  Home actual win rate:  {home_wins_arr.mean():.3f}")
print(f"  Market implied rate:   {home_mkt_arr.mean():.3f}")
excess = home_wins_arr.mean() - home_mkt_arr.mean()
print(f"  Excess:                {excess:+.3f}")

# Bootstrap CI
excess_boots = []
n_hw = len(home_wins_arr)
for _ in range(N_BOOT):
    bi = rng.choice(n_hw, n_hw, replace=True)
    excess_boots.append(home_wins_arr[bi].mean() - home_mkt_arr[bi].mean())
lo, hi = np.percentile(excess_boots, [2.5, 97.5])
sig_excess = 'YES' if (lo > 0 or hi < 0) else 'no'
print(f"  95% CI: [{lo:+.3f}, {hi:+.3f}]  significant: {sig_excess}")

# ═══════════════════════════════════════════════════════════════════
# LOGISTIC: home_diff net of market
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("LOGISTIC: win ~ market_prob + intl_home_diff (non-US, no US-vs-US)")
print(f"{'='*72}")

def neg_ll(params, X_dict, y):
    z = params[0]
    for i, (k, v) in enumerate(X_dict.items()):
        z = z + params[i+1] * v
    p = np.clip(expit(z), 1e-10, 1-1e-10)
    return -np.sum(y * np.log(p) + (1-y) * np.log(1-p))

y_nu = non_us['win_a'].values
X_nu = {
    'mkt_prob': non_us['p_mkt_a'].values,
    'home_diff': non_us['home_diff'].values.astype(float),
}

res = minimize(neg_ll, [0, 1, 0], args=(X_nu, y_nu), method='Nelder-Mead',
               options={'maxiter': 10000})
print(f"\n  Full non-US sample (N={len(non_us)}):")
print(f"    intercept: {res.x[0]:+.4f}")
print(f"    mkt_prob:  {res.x[1]:+.4f}")
print(f"    home_diff: {res.x[2]:+.4f}  (pos = home advantage)")

# Bootstrap CI on home_diff coefficient
print(f"  Bootstrapping (N={N_BOOT})...")
home_coefs = []
n_nu = len(y_nu)
for _ in range(N_BOOT):
    bi = rng.choice(n_nu, n_nu, replace=True)
    yb = y_nu[bi]
    Xb = {k: v[bi] for k, v in X_nu.items()}
    try:
        r = minimize(neg_ll, list(res.x), args=(Xb, yb), method='Nelder-Mead',
                     options={'maxiter': 3000, 'xatol': 1e-3, 'fatol': 1e-3})
        home_coefs.append(r.x[2])
    except:
        pass
home_coefs = np.array(home_coefs)
lo_c, hi_c = np.percentile(home_coefs, [2.5, 97.5])
sig_coef = 'YES' if (lo_c > 0 or hi_c < 0) else 'no'
print(f"    home_diff: {res.x[2]:+.4f} [{lo_c:+.4f}, {hi_c:+.4f}]  significant: {sig_coef}")

# ═══════════════════════════════════════════════════════════════════
# DECISION vs FINISH SPLIT
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("DECISION vs FINISH SPLIT")
print("(Judging mechanism should concentrate home advantage in decisions)")
print(f"{'='*72}")

for label, subset in [('DECISIONS', clean[clean['is_decision']]),
                       ('FINISHES', clean[~clean['is_decision']])]:
    hw, hm = [], []
    for _, row in subset.iterrows():
        if row['home_a'] == 1:
            hw.append(row['win_a']); hm.append(row['p_mkt_a'])
        else:
            hw.append(1 - row['win_a']); hm.append(1 - row['p_mkt_a'])
    hw, hm = np.array(hw), np.array(hm)
    if len(hw) < 5:
        print(f"\n  {label}: too few bouts ({len(hw)})")
        continue
    exc = hw.mean() - hm.mean()
    # Bootstrap
    boots = []
    for _ in range(N_BOOT):
        bi = rng.choice(len(hw), len(hw), replace=True)
        boots.append(hw[bi].mean() - hm[bi].mean())
    lo_s, hi_s = np.percentile(boots, [2.5, 97.5])
    sig_s = 'YES' if (lo_s > 0 or hi_s < 0) else 'no'
    print(f"\n  {label} (N={len(hw)}):")
    print(f"    Home win rate:    {hw.mean():.3f}")
    print(f"    Market implied:   {hm.mean():.3f}")
    print(f"    Excess:           {exc:+.3f} [{lo_s:+.3f}, {hi_s:+.3f}]  sig={sig_s}")

# ═══════════════════════════════════════════════════════════════════
# OOS CHECK
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("OOS CHECK (train<=2023, test 2024-25)")
print(f"{'='*72}")

train_nu = non_us[non_us['year'] <= 2023].copy()
test_nu = non_us[(non_us['year'] >= 2024) & (non_us['year'] <= 2025)].copy()

print(f"  Train (<=2023): {len(train_nu)}")
print(f"  Test (2024-25): {len(test_nu)}")

if len(test_nu) >= 20:
    y_tr = train_nu['win_a'].values
    X_tr = {'mkt_prob': train_nu['p_mkt_a'].values,
            'home_diff': train_nu['home_diff'].values.astype(float)}
    r_tr = minimize(neg_ll, [0, 1, 0], args=(X_tr, y_tr), method='Nelder-Mead',
                    options={'maxiter': 10000})

    mkt_test = test_nu['p_mkt_a'].values
    y_test = test_nu['win_a'].values

    pred_home = expit(r_tr.x[0] + r_tr.x[1]*mkt_test +
                      r_tr.x[2]*test_nu['home_diff'].values.astype(float))

    brier_mkt = brier_score_loss(y_test, mkt_test)
    brier_home = brier_score_loss(y_test, np.clip(pred_home, 1e-6, 1-1e-6))

    print(f"\n  Train-fit: intercept={r_tr.x[0]:+.4f}, mkt={r_tr.x[1]:+.4f}, home={r_tr.x[2]:+.4f}")
    print(f"\n  Test Brier:")
    print(f"    Market raw:       {brier_mkt:.4f}")
    print(f"    Mkt + intl home:  {brier_home:.4f} ({brier_home-brier_mkt:+.4f})")

    # Home fighter stats in test
    has_home_test = test_nu[((test_nu['home_a']==1)|(test_nu['home_b']==1)) &
                             ((test_nu['home_a']+test_nu['home_b'])==1)]
    hw_t, hm_t = [], []
    for _, row in has_home_test.iterrows():
        if row['home_a'] == 1:
            hw_t.append(row['win_a']); hm_t.append(row['p_mkt_a'])
        else:
            hw_t.append(1 - row['win_a']); hm_t.append(1 - row['p_mkt_a'])
    hw_t, hm_t = np.array(hw_t), np.array(hm_t)
    if len(hw_t) > 0:
        print(f"\n  Home-vs-away in test (N={len(hw_t)}):")
        print(f"    Win rate: {hw_t.mean():.3f}, Market: {hm_t.mean():.3f}, Excess: {hw_t.mean()-hm_t.mean():+.3f}")
else:
    print(f"  Test too small ({len(test_nu)}) for OOS check")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("VERDICT")
print(f"{'='*72}")

print(f"\n  International home advantage (non-US events, no US-vs-US):")
print(f"    N total = {len(non_us)}, N clean home-vs-away = {len(clean)}")
print(f"    Home excess: {excess:+.3f} [{lo:+.3f}, {hi:+.3f}]")
print(f"    Logistic coef: {res.x[2]:+.4f} [{lo_c:+.4f}, {hi_c:+.4f}]")
if sig_coef == 'no' and sig_excess == 'no':
    print(f"\n    Neither the raw excess nor the logistic coefficient is significant.")
    print(f"    The international home sample ({len(clean)} clean bouts) is")
    if len(clean) < 300:
        print(f"    TOO SMALL to distinguish any plausible effect from zero.")
        print(f"    A 3pp home edge would need ~1000+ bouts to detect at 80% power.")
    else:
        print(f"    moderate but insufficient to detect a small effect.")
    print(f"    Verdict: UNDERPOWERED NULL, consistent with efficient.")
elif sig_coef == 'YES' or sig_excess == 'YES':
    print(f"\n    Signal detected -- but check decision/finish split for mechanism.")
    print(f"    If concentrated in decisions: judging bias (real but may be priced).")
    print(f"    If uniform: more likely noise or confounding.")
