#!/usr/bin/env python3
"""
Core result: ethnic-Russian post-2022 sentiment effect.
Produces: figures/fig1_timeshape.csv, figures/table3_within_fighter.csv,
          figures/table4_did.csv, figures/table5_entrant_quality.csv
"""
import sys, re, warnings, functools, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

DATA_DIR = '../data'
OUT_DIR = '../figures'

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# Load data
wiki = pd.read_csv(f'{DATA_DIR}/wikidata_mma_fighters.csv')
wiki_lookup = {}
for _, row in wiki.iterrows():
    nn = norm_name(row['name'])
    if nn not in wiki_lookup or (str(row.get('lat','')).strip() not in ('', 'nan')):
        wiki_lookup[nn] = row.to_dict()

panel = pd.read_csv(f'{DATA_DIR}/analysis_panel_cc.csv')
panel['date'] = pd.to_datetime(panel['date'])
ufc_fighters = set(panel['fighter'].unique()) | set(panel['opponent'].unique())

matched = {}
for f in ufc_fighters:
    nn = norm_name(f)
    if nn in wiki_lookup:
        matched[f] = wiki_lookup[nn]
    else:
        parts = nn.split()
        if len(parts) >= 2:
            rev = ' '.join(parts[1:] + parts[:1])
            if rev in wiki_lookup:
                matched[f] = wiki_lookup[rev]

def assign_region(fighter_name):
    d = matched.get(fighter_name, {})
    country = d.get('country', '')
    if not country:
        return None
    if country == 'Russia':
        try:
            lat, lon = float(d.get('lat', 0)), float(d.get('lon', 0))
            if 41 < lat < 45 and 43 < lon < 49:
                return 'Caucasus'
        except (ValueError, TypeError):
            pass
        bp = str(d.get('birthplace', '')).lower()
        caucasus_markers = ['dagestan', 'chechnya', 'chechen', 'grozny', 'makhachkala',
                            'ingush', 'kabardino', 'karachay', 'ossetia', 'nalchik',
                            'khasavyurt', 'buynaksk', 'derbent', 'nazran', 'kizlyar',
                            'kaspiysk', 'kizilyurt', 'sildi', 'sunzha', 'teletl',
                            'achkhoy', 'aymaki', 'dylym', 'madzhalis', 'mekegi',
                            'kasumkent', 'kamysh-kutan', 'goksuv', 'batayurt',
                            'gvardeyskoe', 'babugent', 'vladikavkaz']
        if any(m in bp for m in caucasus_markers):
            return 'Caucasus'
        return 'Russia (ethnic)'
    if country in ('Kazakhstan', 'Kyrgyzstan', 'Uzbekistan', 'Tajikistan', 'Turkmenistan'):
        return 'Central Asia'
    if country == 'United States':
        return 'USA'
    return 'Other'

# Build fight-level dataset
fight_counter = defaultdict(int)
rows = []
for _, r in panel.sort_values('date').iterrows():
    fighter = r['fighter']
    region = assign_region(fighter)
    if region is None:
        continue
    fight_counter[fighter] += 1
    rows.append({
        'fight_id': r['fight_id'], 'date': r['date'], 'year': r['year'],
        'fighter': fighter, 'opponent': r['opponent'],
        'region': region, 'p_mkt': r['p_close_hi'], 'win': int(r['win']),
        'career_n': fight_counter[fighter],
        'post': 1 if r['date'] >= pd.Timestamp('2022-02-24') else 0,
    })

df = pd.DataFrame(rows)
df = df[(df['year'] >= 2017) & (df['year'] <= 2025)].copy()
df['excess'] = df['win'] - df['p_mkt']

eth_rus = df[df['region'] == 'Russia (ethnic)']
cauc = df[df['region'] == 'Caucasus']

# ═══════════════════════════════════════════════════════════════════
# FIGURE 1: TIME-SHAPE (half-year excess)
# ═══════════════════════════════════════════════════════════════════
print("Generating Figure 1: time-shape...")
ts_rows = []
for region, sub in [('Ethnic Russian', eth_rus), ('Caucasus', cauc)]:
    sub = sub.copy()
    sub['half'] = sub['date'].dt.year.astype(str) + '-' + np.where(sub['date'].dt.month <= 6, 'H1', 'H2')
    for period in sorted(sub['half'].unique()):
        p_sub = sub[sub['half'] == period]
        if len(p_sub) == 0:
            continue
        ts_rows.append({
            'Region': region, 'Period': period, 'N': len(p_sub),
            'WinRate': p_sub['win'].mean(), 'MarketImplied': p_sub['p_mkt'].mean(),
            'Excess': p_sub['excess'].mean(),
        })
ts_df = pd.DataFrame(ts_rows)
ts_df.to_csv(f'{OUT_DIR}/fig1_timeshape.csv', index=False)
print(ts_df.to_string(index=False))

# ═══════════════════════════════════════════════════════════════════
# TABLE 3: WITHIN-FIGHTER PRE/POST
# ═══════════════════════════════════════════════════════════════════
print("\nGenerating Table 3: within-fighter...")
wf_rows = []
for region_name, region_df in [('Ethnic Russian', eth_rus), ('Caucasus', cauc)]:
    for fighter in region_df['fighter'].unique():
        pre = region_df[(region_df['fighter'] == fighter) & (region_df['post'] == 0)]
        post = region_df[(region_df['fighter'] == fighter) & (region_df['post'] == 1)]
        if len(pre) >= 1 and len(post) >= 1:
            wf_rows.append({
                'Region': region_name, 'Fighter': fighter,
                'Pre_N': len(pre), 'Pre_excess': round(pre['excess'].mean(), 3),
                'Post_N': len(post), 'Post_excess': round(post['excess'].mean(), 3),
                'Swing': round(post['excess'].mean() - pre['excess'].mean(), 3),
            })
wf_df = pd.DataFrame(wf_rows)
wf_df.to_csv(f'{OUT_DIR}/table3_within_fighter.csv', index=False)
print(wf_df.to_string(index=False))

# Aggregate within-fighter by region
for region_name in ['Ethnic Russian', 'Caucasus']:
    sub = wf_df[wf_df['Region'] == region_name]
    if len(sub) == 0:
        continue
    mean_swing = sub['Swing'].mean()
    n_fighters = len(sub)
    # Bootstrap CI
    boots = [sub.iloc[rng.choice(n_fighters, n_fighters, replace=True)]['Swing'].mean()
             for _ in range(N_BOOT)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"\n  {region_name} within-fighter swing: {mean_swing:+.3f} [{lo:+.3f}, {hi:+.3f}] sig={sig} (N={n_fighters})")

# ═══════════════════════════════════════════════════════════════════
# TABLE 4: DiD
# ═══════════════════════════════════════════════════════════════════
print("\nGenerating Table 4: DiD...")
did_rows = []
treatment = eth_rus
for ctrl_name, ctrl_df in [('Caucasus', cauc),
                            ('USA', df[df['region'] == 'USA']),
                            ('All non-Russian', df[~df['region'].isin(['Russia (ethnic)', 'Caucasus'])])]:
    t_pre = treatment[treatment['post'] == 0]['excess']
    t_post = treatment[treatment['post'] == 1]['excess']
    c_pre = ctrl_df[ctrl_df['post'] == 0]['excess']
    c_post = ctrl_df[ctrl_df['post'] == 1]['excess']
    if min(len(t_pre), len(t_post), len(c_pre), len(c_post)) < 5:
        continue
    t_diff = t_post.mean() - t_pre.mean()
    c_diff = c_post.mean() - c_pre.mean()
    did = t_diff - c_diff
    boots = []
    for _ in range(N_BOOT):
        bt = t_post.values[rng.choice(len(t_post), len(t_post), True)].mean() - \
             t_pre.values[rng.choice(len(t_pre), len(t_pre), True)].mean()
        bc = c_post.values[rng.choice(len(c_post), len(c_post), True)].mean() - \
             c_pre.values[rng.choice(len(c_pre), len(c_pre), True)].mean()
        boots.append(bt - bc)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    did_rows.append({
        'Control': ctrl_name,
        'Treatment_pre': f'{t_pre.mean():+.3f} (N={len(t_pre)})',
        'Treatment_post': f'{t_post.mean():+.3f} (N={len(t_post)})',
        'Control_pre': f'{c_pre.mean():+.3f} (N={len(c_pre)})',
        'Control_post': f'{c_post.mean():+.3f} (N={len(c_post)})',
        'DiD': f'{did:+.3f}', 'CI_95': f'[{lo:+.3f}, {hi:+.3f}]', 'Sig': sig,
    })

did_df = pd.DataFrame(did_rows)
did_df.to_csv(f'{OUT_DIR}/table4_did.csv', index=False)
print(did_df.to_string(index=False))

# ═══════════════════════════════════════════════════════════════════
# TABLE 5: ENTRANT-QUALITY DISTRIBUTION
# ═══════════════════════════════════════════════════════════════════
print("\nGenerating Table 5: entrant quality...")
all_debuts = df[df['career_n'] == 1]
post_debuts = all_debuts[all_debuts['post'] == 1]
rus_debs = post_debuts[post_debuts['region'] == 'Russia (ethnic)']
other_debs = post_debuts[~post_debuts['region'].isin(['Russia (ethnic)', 'Caucasus', 'Central Asia'])]

# Get all fights for each debutant
eq_rows = []
for label, debs in [('Russian entrants', rus_debs), ('Non-Russian entrants', other_debs)]:
    fighters = debs['fighter'].tolist()
    all_fights = df[df['fighter'].isin(fighters)]
    eq_rows.append({
        'Group': label, 'N_fighters': len(fighters), 'N_fights': len(all_fights),
        'Mean_market_prob': f'{all_fights["p_mkt"].mean():.3f}',
        'Median_market_prob': f'{all_fights["p_mkt"].median():.3f}',
        'Frac_underdog': f'{(all_fights["p_mkt"] < 0.5).mean():.0%}',
        'Actual_WR': f'{all_fights["win"].mean():.3f}',
        'Excess': f'{all_fights["excess"].mean():+.3f}',
    })
eq_df = pd.DataFrame(eq_rows)
eq_df.to_csv(f'{OUT_DIR}/table5_entrant_quality.csv', index=False)
print(eq_df.to_string(index=False))

print(f"\nAll tables saved to {OUT_DIR}/")
