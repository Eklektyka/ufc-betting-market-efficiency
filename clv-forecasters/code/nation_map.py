#!/usr/bin/env python3
"""
Nation-level mispricing map: all regions with >=99 bouts, 2007-2025.
Excess vs closing line, relative to US baseline, BH-corrected, with mechanism tags.
"""
import sys, re, warnings, functools, unicodedata, math
import numpy as np
import pandas as pd
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000
MIN_BOUTS = 99

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# ── Load ──
wiki = pd.read_csv(r'C:\Research\mma-paper\data\wikidata_mma_fighters.csv')
wiki_lookup = {}
for _, row in wiki.iterrows():
    nn = norm_name(row['name'])
    if nn not in wiki_lookup or (str(row.get('lat','')).strip() not in ('', 'nan')):
        wiki_lookup[nn] = row.to_dict()

panel = pd.read_csv(r'C:\Research\mma-paper\data\analysis_panel_cc.csv')
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
                return 'Caucasus/Dagestan'
        except (ValueError, TypeError):
            pass
        bp = str(d.get('birthplace', '')).lower()
        cauc = ['dagestan','chechnya','chechen','grozny','makhachkala','ingush',
                'kabardino','karachay','ossetia','nalchik','khasavyurt','buynaksk',
                'derbent','nazran','kizlyar','kaspiysk','kizilyurt','sildi','sunzha',
                'teletl','achkhoy','aymaki','dylym','madzhalis','mekegi','kasumkent',
                'kamysh-kutan','goksuv','batayurt','gvardeyskoe','babugent','vladikavkaz']
        if any(m in bp for m in cauc):
            return 'Caucasus/Dagestan'
        return 'Russia (ethnic)'
    mapping = {
        'United States': 'USA', 'Brazil': 'Brazil', 'Canada': 'Canada',
        'United Kingdom': 'UK', 'Australia': 'Australia', 'Mexico': 'Mexico',
        'Japan': 'Japan', 'Poland': 'Poland', 'New Zealand': 'New Zealand',
        'France': 'France', 'Sweden': 'Sweden', 'South Korea': 'South Korea',
        'Ireland': 'Ireland', 'Netherlands': 'Netherlands', 'China': 'China',
        'Nigeria': 'Nigeria', 'Georgia': 'Georgia',
    }
    if country in mapping:
        return mapping[country]
    if country in ('Kazakhstan','Kyrgyzstan','Uzbekistan','Tajikistan','Turkmenistan'):
        return 'Central Asia'
    if country in ('Argentina','Colombia','Ecuador','Peru','Chile','Venezuela','Cuba',
                   'Dominican Republic','Jamaica','Guyana','Trinidad and Tobago',
                   'Uruguay','Paraguay','Nicaragua','Guatemala','Puerto Rico','Bolivia'):
        return 'Latin America (non-Brazil)'
    if country in ('Cameroon','South Africa','Ghana','Senegal',
                   'Democratic Republic of the Congo','Republic of the Congo'):
        return 'Sub-Saharan Africa'
    if country in ('Azerbaijan','Armenia'):
        return 'Caucasus/Georgia'
    if country in ('Iran','Iraq','Afghanistan','Pakistan','Egypt','Morocco','Tunisia',
                   'Algeria','Jordan','Syria','Lebanon','Turkey'):
        return 'MENA'
    if country in ('Philippines','Indonesia','Thailand','Malaysia','Myanmar',
                   'India','Mongolia'):
        return 'SE/East Asia'
    return 'Other'

# ── Build fight-level rows ──
print("Building fight-level dataset...")
fight_counter = defaultdict(int)
rows = []
for _, r in panel.sort_values('date').iterrows():
    fighter = r['fighter']
    region = assign_region(fighter)
    if region is None:
        continue
    fight_counter[fighter] += 1
    rows.append({
        'fighter': fighter, 'region': region,
        'p_mkt': r['p_close_hi'], 'win': int(r['win']),
        'year': r['year'], 'career_n': fight_counter[fighter],
    })
df = pd.DataFrame(rows)
df = df[df['year'] <= 2025].copy()
df['excess'] = df['win'] - df['p_mkt']

print(f"  Total rows: {len(df)}, regions: {df['region'].nunique()}")

# ── US baseline ──
us = df[df['region'] == 'USA']
us_excess = us['excess'].mean()
us_win = us['win'].values; us_mkt = us['p_mkt'].values; n_us = len(us)
print(f"  US baseline: N={n_us}, WR={us['win'].mean():.3f}, mkt={us['p_mkt'].mean():.3f}, excess={us_excess:+.4f}")

# Pre-compute US bootstrap
us_boots = np.array([
    us_win[rng.choice(n_us, n_us, True)].mean() - us_mkt[rng.choice(n_us, n_us, True)].mean()
    for _ in range(N_BOOT)
])

# ── Nation-level excess ──
results = []
regions = [r for r in df['region'].unique() if r != 'USA']

for region in sorted(regions):
    sub = df[df['region'] == region]
    n = len(sub)
    if n < MIN_BOUTS:
        continue
    n_fighters = sub['fighter'].nunique()
    wr = sub['win'].mean()
    mkt = sub['p_mkt'].mean()
    excess = sub['excess'].mean()
    relative = excess - us_excess

    win_arr = sub['win'].values; mkt_arr = sub['p_mkt'].values
    boots = np.array([
        win_arr[rng.choice(n, n, True)].mean() - mkt_arr[rng.choice(n, n, True)].mean() - us_boots[i]
        for i in range(N_BOOT)
    ])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    raw_p = 2 * min(np.mean(boots > 0), np.mean(boots < 0))
    if raw_p == 0:
        raw_p = 1 / N_BOOT

    # Career-stage split
    stages = {}
    for label, slo, shi in [('1-3', 1, 3), ('4-8', 4, 8), ('9+', 9, 999)]:
        st = sub[(sub['career_n'] >= slo) & (sub['career_n'] <= shi)]
        if len(st) >= 15:
            stages[label] = st['excess'].mean()
        else:
            stages[label] = None

    # Mechanism tag
    if stages.get('1-3') is not None and stages.get('9+') is not None:
        diff = stages['1-3'] - stages['9+']
        if diff > 0.04:
            mechanism = 'front-loaded (learning)'
        elif diff < -0.04:
            mechanism = 'back-loaded'
        else:
            mechanism = 'uniform (standing)'
    else:
        mechanism = "can't tell (n too small)"

    results.append({
        'region': region, 'n': n, 'n_fighters': n_fighters,
        'wr': wr, 'mkt': mkt, 'excess': excess,
        'relative': relative, 'ci_lo': lo, 'ci_hi': hi,
        'raw_p': raw_p, 'stage_1_3': stages.get('1-3'),
        'stage_4_8': stages.get('4-8'), 'stage_9p': stages.get('9+'),
        'mechanism': mechanism,
    })

# BH correction
results.sort(key=lambda x: x['raw_p'])
n_tests = len(results)
for rank, r in enumerate(results, 1):
    r['bh_threshold'] = 0.05 * rank / n_tests
    r['bh_survives'] = r['raw_p'] <= r['bh_threshold']

# Sort by excess for display
results.sort(key=lambda x: -x['relative'])

# ═══════════════════════════════════════════════════════════════════
# MAIN TABLE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print(f"NATION-LEVEL MISPRICING MAP (>=99 bouts, 2007-2025, vs US baseline)")
print(f"{'='*120}")

print(f"\n  {'Region':<24s} {'N':>5} {'Ftr':>4} {'WR':>5} {'Mkt':>5} {'Excess':>7} {'vsUS':>6} "
      f"{'95% CI':>17} {'p':>6} {'BH':>4} {'1-3':>6} {'4-8':>6} {'9+':>6} {'Mechanism':<25s}")
print("  " + "-" * 130)

for r in results:
    bh = '*' if r['bh_survives'] else ''
    s13 = f"{r['stage_1_3']:+.3f}" if r['stage_1_3'] is not None else '  --'
    s48 = f"{r['stage_4_8']:+.3f}" if r['stage_4_8'] is not None else '  --'
    s9p = f"{r['stage_9p']:+.3f}" if r['stage_9p'] is not None else '  --'
    print(f"  {r['region']:<24s} {r['n']:>5} {r['n_fighters']:>4} {r['wr']:>4.0%} {r['mkt']:>4.0%} "
          f"{r['excess']:>+6.3f} {r['relative']:>+5.3f} "
          f"[{r['ci_lo']:>+.3f},{r['ci_hi']:>+.3f}] "
          f"{r['raw_p']:>5.3f} {bh:>3s} "
          f"{s13:>6s} {s48:>6s} {s9p:>6s} {r['mechanism']:<25s}")

# ═══════════════════════════════════════════════════════════════════
# JAPAN DEEP-DIVE: LEGACY-PRESTIGE EFFECT?
# ═══════════════════════════════════════════════════════════════════
japan_data = [r for r in results if r['region'] == 'Japan']
if japan_data:
    print(f"\n{'='*80}")
    print("JAPAN DEEP-DIVE: LEGACY-PRESTIGE / ERA EFFECT?")
    print(f"{'='*80}")

    jp = df[df['region'] == 'Japan']
    print(f"\n  Era split:")
    print(f"  {'Era':<15s} {'N':>5} {'WR':>5} {'Mkt':>5} {'Excess':>7}")
    print("  " + "-" * 40)
    for label, ylo, yhi in [('2007-2012', 2007, 2012), ('2013-2017', 2013, 2017),
                              ('2018-2021', 2018, 2021), ('2022-2025', 2022, 2025)]:
        era = jp[(jp['year'] >= ylo) & (jp['year'] <= yhi)]
        if len(era) < 5:
            print(f"  {label:<15s} {len(era):>5} (too few)")
            continue
        print(f"  {label:<15s} {len(era):>5} {era['win'].mean():>4.0%} {era['p_mkt'].mean():>4.0%} "
              f"{era['excess'].mean():>+6.3f}")

    # Fighter-level: who drives it?
    print(f"\n  Fighter-level (all Japanese, sorted by excess):")
    print(f"  {'Fighter':<25s} {'N':>4} {'WR':>5} {'Mkt':>5} {'Excess':>7} {'Years':>10}")
    print("  " + "-" * 60)
    for fighter, grp in jp.groupby('fighter'):
        if len(grp) < 3:
            continue
        yr_range = f"{grp['year'].min()}-{grp['year'].max()}"
        print(f"  {fighter[:24]:<25s} {len(grp):>4} {grp['win'].mean():>4.0%} "
              f"{grp['p_mkt'].mean():>4.0%} {grp['excess'].mean():>+6.3f} {yr_range:>10s}")

# ═══════════════════════════════════════════════════════════════════
# CAUCASUS CONFIRMATION
# ═══════════════════════════════════════════════════════════════════
cauc_data = [r for r in results if r['region'] == 'Caucasus/Dagestan']
if cauc_data:
    c = cauc_data[0]
    print(f"\n{'='*80}")
    print("CAUCASUS/DAGESTAN CONFIRMATION")
    print(f"{'='*80}")
    print(f"  Excess vs US: {c['relative']:+.3f} [{c['ci_lo']:+.3f}, {c['ci_hi']:+.3f}], p={c['raw_p']:.3f}")
    print(f"  BH survives: {'YES' if c['bh_survives'] else 'NO'}")
    print(f"  Career split: 1-3={c['stage_1_3']:+.3f}, 4-8={c['stage_4_8']:+.3f}, 9+={c['stage_9p']:+.3f}")
    print(f"  Mechanism: {c['mechanism']}")

# ═══════════════════════════════════════════════════════════════════
# SUMMARY READ
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("SUMMARY")
print(f"{'='*80}")

bh_survivors = [r for r in results if r['bh_survives']]
print(f"\n  Nations tested: {n_tests} (>={MIN_BOUTS} bouts each)")
print(f"  BH-surviving (alpha=0.05): {len(bh_survivors)}")

if bh_survivors:
    for r in bh_survivors:
        direction = 'UNDERPRICED' if r['relative'] > 0 else 'OVERPRICED'
        print(f"    {r['region']}: {r['relative']:+.3f} vs US, p={r['raw_p']:.3f}, "
              f"{direction}, mechanism={r['mechanism']}")
else:
    print(f"    None survive BH correction.")

# Near-misses
near = [r for r in results if not r['bh_survives'] and r['raw_p'] < 0.05]
if near:
    print(f"\n  Near-misses (raw p<0.05, fail BH):")
    for r in near:
        direction = 'under' if r['relative'] > 0 else 'over'
        print(f"    {r['region']}: {r['relative']:+.3f}, p={r['raw_p']:.3f} ({direction}priced), "
              f"needs p<{r['bh_threshold']:.3f} for BH")

# Confirming priors
print(f"\n  PRIOR CONFIRMATIONS:")
for name, expected in [('Brazil', '~zero'), ('New Zealand', 'front-loaded (learning)'),
                        ('Caucasus/Dagestan', 'uniform (standing)'),
                        ('Japan', 'overpriced')]:
    r = next((x for x in results if x['region'] == name), None)
    if r:
        print(f"    {name}: excess={r['relative']:+.3f}, mechanism={r['mechanism']} -- expected: {expected}")
