#!/usr/bin/env python3
"""
Nation/region mispricing test: sin-stock hypothesis.
Do certain nationalities earn excess returns vs the closing line?
"""
import sys, math, re, warnings, functools, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict, Counter
from scipy.optimize import minimize
from scipy.special import expit
from scipy import stats as sp_stats
from sklearn.metrics import brier_score_loss

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# ═══════════════════════════════════════════════════════════════════
# LOAD & MATCH
# ═══════════════════════════════════════════════════════════════════
print("Loading data...")

wiki = pd.read_csv(r'C:\Research\ufc\odds\wikidata_mma_fighters.csv')
wiki_lookup = {}
for _, row in wiki.iterrows():
    nn = norm_name(row['name'])
    if nn not in wiki_lookup or (str(row.get('lat','')).strip() not in ('', 'nan')):
        wiki_lookup[nn] = row.to_dict()

panel = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\processed\analysis_panel_cc.csv')
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

# UFCStats fight stats for style control
fights_raw = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv')
fight_method = {}
for _, row in fights_raw.iterrows():
    if row['result'] == 'W':
        fight_method[row['fight_url']] = row['method']

# ═══════════════════════════════════════════════════════════════════
# ASSIGN NATION/REGION — separate Caucasus from ethnic Russian
# ═══════════════════════════════════════════════════════════════════

def assign_region(fighter_name):
    d = matched.get(fighter_name, {})
    country = d.get('country', '')
    if not country:
        return None

    if country == 'Russia':
        # Use geo-coordinates to separate Caucasus
        try:
            lat, lon = float(d.get('lat', 0)), float(d.get('lon', 0))
            if 41 < lat < 45 and 43 < lon < 49:
                return 'Caucasus'  # Dagestan, Chechnya, etc.
        except (ValueError, TypeError):
            pass
        # Check birthplace text
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

    # Central Asia
    if country in ('Kazakhstan', 'Kyrgyzstan', 'Uzbekistan', 'Tajikistan', 'Turkmenistan'):
        return 'Central Asia'

    # Group small nations into regions where needed
    if country in ('United States',):
        return 'USA'
    if country in ('Brazil',):
        return 'Brazil'
    if country in ('United Kingdom',):
        return 'UK'
    if country in ('Canada',):
        return 'Canada'
    if country in ('Australia',):
        return 'Australia'
    if country in ('Mexico',):
        return 'Mexico'
    if country in ('Japan',):
        return 'Japan'
    if country in ('South Korea',):
        return 'South Korea'
    if country in ('Poland',):
        return 'Poland'
    if country in ('Sweden',):
        return 'Sweden'
    if country in ('France',):
        return 'France'
    if country in ('Ireland',):
        return 'Ireland'
    if country in ('New Zealand',):
        return 'New Zealand'
    if country in ('Netherlands',):
        return 'Netherlands'
    if country in ('Nigeria', 'Cameroon', 'South Africa', 'Ghana',
                   'Senegal', 'Democratic Republic of the Congo',
                   'Republic of the Congo'):
        return 'Africa'
    if country in ('Georgia', 'Armenia', 'Azerbaijan'):
        return 'Caucasus/Georgia'
    if country in ('China',):
        return 'China'
    if country in ('Philippines', 'Indonesia', 'Thailand', 'Malaysia',
                   'Myanmar', 'India', 'Mongolia'):
        return 'SE/E Asia'
    if country in ('Iran', 'Iraq', 'Afghanistan', 'Pakistan',
                   'Egypt', 'Morocco', 'Tunisia', 'Turkey',
                   'Jordan', 'Syria', 'Lebanon', 'Algeria'):
        return 'MENA'
    if country in ('Argentina', 'Colombia', 'Ecuador', 'Peru', 'Chile',
                   'Venezuela', 'Cuba', 'Dominican Republic', 'Jamaica',
                   'Guyana', 'Trinidad and Tobago', 'Uruguay',
                   'Paraguay', 'Bolivia', 'Puerto Rico',
                   'Nicaragua', 'Guatemala'):
        return 'LatAm (non-Brazil)'

    return 'Other'

# ═══════════════════════════════════════════════════════════════════
# BUILD FIGHT-LEVEL DATASET (one row per fighter per fight)
# ═══════════════════════════════════════════════════════════════════
print("Building fight-level dataset...")

# Career fight counter
fight_counts = defaultdict(int)

# Build cumulative style stats per fighter (pre-fight averages)
fighter_style = defaultdict(lambda: {'td_landed': 0, 'td_att': 0, 'ctrl_sec': 0,
                                      'sig_str_landed': 0, 'sig_str_att': 0, 'n_fights': 0})

# Pre-compute style stats from ufcstats (ordered by date)
fights_raw_sorted = fights_raw.sort_values('date')

# For style: we need per-fighter cumulative stats BEFORE each fight
# Build a dict of fighter -> list of (date, fight_url, stats)
fighter_fight_stats = defaultdict(list)
for _, row in fights_raw_sorted.iterrows():
    try:
        td_l = int(row['td_landed']) if pd.notna(row['td_landed']) else 0
        td_a = int(row['td_att']) if pd.notna(row['td_att']) else 0
        ctrl = int(row['ctrl_sec']) if pd.notna(row['ctrl_sec']) else 0
        sig_l = int(row['sig_str_landed']) if pd.notna(row['sig_str_landed']) else 0
        sig_a = int(row['sig_str_att']) if pd.notna(row['sig_str_att']) else 0
    except (ValueError, TypeError):
        td_l = td_a = ctrl = sig_l = sig_a = 0

    fighter_fight_stats[row['fighter_name']].append({
        'date': row['date'], 'fight_url': row['fight_url'],
        'td_landed': td_l, 'td_att': td_a, 'ctrl_sec': ctrl,
        'sig_str_landed': sig_l, 'sig_str_att': sig_a,
    })

# Build cumulative averages
def get_pre_fight_style(fighter_name, fight_url):
    """Get career-average style stats BEFORE this fight."""
    stats = fighter_fight_stats.get(fighter_name, [])
    cum_td_l, cum_td_a, cum_ctrl, cum_sig_l, cum_sig_a, n = 0, 0, 0, 0, 0, 0
    for s in stats:
        if s['fight_url'] == fight_url:
            break
        cum_td_l += s['td_landed']
        cum_td_a += s['td_att']
        cum_ctrl += s['ctrl_sec']
        cum_sig_l += s['sig_str_landed']
        cum_sig_a += s['sig_str_att']
        n += 1
    if n == 0:
        return {'td_rate': 0, 'ctrl_per_fight': 0, 'wrestling_score': 0}
    td_rate = cum_td_l / max(cum_td_a, 1)
    ctrl_per = cum_ctrl / n
    # Wrestling score = td_landed/fight + ctrl_sec/fight (normalized)
    td_per = cum_td_l / n
    wrestling = td_per + ctrl_per / 60  # ctrl in minutes
    return {'td_rate': td_rate, 'ctrl_per_fight': ctrl_per, 'wrestling_score': wrestling}

# Build panel-level rows
rows = []
fight_counter = defaultdict(int)

for _, r in panel.sort_values('date').iterrows():
    fighter = r['fighter']
    region = assign_region(fighter)
    if region is None:
        continue

    fight_counter[fighter] += 1
    career_n = fight_counter[fighter]

    # Style
    style = get_pre_fight_style(fighter, r['fight_url'])

    # Post-Ukraine war
    fight_date = r['date']
    post_ukraine = 1 if fight_date >= pd.Timestamp('2022-03-01') else 0

    rows.append({
        'fight_id': r['fight_id'],
        'fight_url': r['fight_url'],
        'date': fight_date,
        'year': r['year'],
        'fighter': fighter,
        'opponent': r['opponent'],
        'region': region,
        'p_mkt': r['p_close_hi'],
        'win': int(r['win']),
        'career_n': career_n,
        'wrestling_score': style['wrestling_score'],
        'td_rate': style['td_rate'],
        'ctrl_per_fight': style['ctrl_per_fight'],
        'post_ukraine': post_ukraine,
    })

df = pd.DataFrame(rows)
df = df[df['year'] <= 2025]  # exclude 2026
print(f"  Fight-level rows: {len(df)} ({df['year'].min()}-{df['year'].max()})")
print(f"  Unique fighters: {df['fighter'].nunique()}")

# Region counts
print(f"\n  Region distribution:")
for region, cnt in df['region'].value_counts().head(20).items():
    n_fighters = df[df['region']==region]['fighter'].nunique()
    print(f"    {region:<22s} {cnt:>5} fight-rows, {n_fighters:>4} fighters")


# ═══════════════════════════════════════════════════════════════════
# TEST 1: EXCESS vs MARKET BY NATION, RELATIVE TO US
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 1: NATION EXCESS vs MARKET (relative to US)")
print(f"{'='*72}")

# Compute excess = actual_win_rate - market_implied, per region
# US is the anchor (its excess is the baseline miscalibration)

us = df[df['region'] == 'USA']
us_excess = us['win'].mean() - us['p_mkt'].mean()
print(f"\n  US baseline: WR={us['win'].mean():.3f}, mkt={us['p_mkt'].mean():.3f}, excess={us_excess:+.3f}")

# Pre-compute US bootstrap (row-level, fast)
us_win = us['win'].values
us_mkt = us['p_mkt'].values
n_us = len(us_win)
us_boots = np.array([
    us_win[rng.choice(n_us, n_us, replace=True)].mean() -
    us_mkt[rng.choice(n_us, n_us, replace=True)].mean()
    for _ in range(N_BOOT)
])

results = []
regions_to_test = [r for r in df['region'].unique() if r != 'USA']

for region in sorted(regions_to_test):
    sub = df[df['region'] == region]
    n = len(sub)
    if n < 20:
        continue
    n_fighters = sub['fighter'].nunique()
    wr = sub['win'].mean()
    mkt = sub['p_mkt'].mean()
    excess = wr - mkt
    relative = excess - us_excess

    # Row-level bootstrap (fast, conservative — fight clustering adds ~10-20% to SE)
    win_arr = sub['win'].values
    mkt_arr = sub['p_mkt'].values
    boots = np.array([
        win_arr[rng.choice(n, n, replace=True)].mean() -
        mkt_arr[rng.choice(n, n, replace=True)].mean() -
        us_boots[i]
        for i in range(N_BOOT)
    ])
    lo, hi = np.percentile(boots, [2.5, 97.5])

    results.append({
        'region': region, 'n': n, 'n_fighters': n_fighters,
        'wr': wr, 'mkt': mkt, 'excess': excess,
        'relative': relative, 'ci_lo': lo, 'ci_hi': hi,
        'raw_p': 2 * min(np.mean(np.array(boots) > 0), np.mean(np.array(boots) < 0)),
    })

results = sorted(results, key=lambda x: -x['relative'])

# Multiplicity correction (Benjamini-Hochberg)
n_tests = len(results)
p_vals = [r['raw_p'] for r in results]
sorted_p = sorted(enumerate(p_vals), key=lambda x: x[1])
bh_threshold = {}
for rank, (idx, p) in enumerate(sorted_p, 1):
    bh_threshold[idx] = 0.05 * rank / n_tests

for i, r in enumerate(results):
    r['bh_sig'] = r['raw_p'] <= bh_threshold[i] if r['raw_p'] > 0 else False

print(f"\n  {'Region':<22s} {'N':>5} {'Ftr':>4} {'WR':>5} {'Mkt':>5} {'Excess':>7} {'vs US':>7} {'95% CI':>16} {'p':>6} {'BH sig':>6}")
print("  " + "-" * 100)
for r in results:
    sig = 'YES' if r['bh_sig'] else ''
    print(f"  {r['region']:<22s} {r['n']:>5} {r['n_fighters']:>4} {r['wr']:>4.0%} {r['mkt']:>4.0%} "
          f"{r['excess']:>+6.3f} {r['relative']:>+6.3f} [{r['ci_lo']:>+.3f},{r['ci_hi']:>+.3f}] "
          f"{r['raw_p']:>5.3f} {sig:>6}")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: CAREER-STAGE SPLIT (survivorship vs aversion)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 2: CAREER-STAGE SPLIT")
print("Survivorship = front-loaded; Aversion = uniform")
print(f"{'='*72}")

# Top under-priced regions
top_regions = [r['region'] for r in results if r['relative'] > 0.02 and r['n'] >= 30]
if not top_regions:
    top_regions = [results[0]['region']] if results else []

for region in top_regions[:3]:
    sub = df[df['region'] == region]
    print(f"\n  {region} (N={len(sub)}):")
    print(f"    {'Stage':<15s} {'N':>5} {'WR':>5} {'Mkt':>5} {'Excess':>7}")
    print("    " + "-" * 40)
    for label, lo, hi in [('UFC 1-3', 1, 3), ('UFC 4-8', 4, 8), ('UFC 9+', 9, 999)]:
        stage = sub[(sub['career_n'] >= lo) & (sub['career_n'] <= hi)]
        if len(stage) < 5:
            print(f"    {label:<15s} {len(stage):>5} (too few)")
            continue
        wr = stage['win'].mean()
        mkt = stage['p_mkt'].mean()
        exc = wr - mkt
        print(f"    {label:<15s} {len(stage):>5} {wr:>4.0%} {mkt:>4.0%} {exc:>+6.3f}")

    # Interpretation
    stages_data = []
    for lo, hi in [(1, 3), (4, 8), (9, 999)]:
        stage = sub[(sub['career_n'] >= lo) & (sub['career_n'] <= hi)]
        if len(stage) >= 5:
            stages_data.append(stage['win'].mean() - stage['p_mkt'].mean())
    if len(stages_data) >= 2:
        if stages_data[0] > stages_data[-1] + 0.03:
            print(f"    -> FRONT-LOADED: excess decays with career -> survivorship/learning")
        elif abs(stages_data[0] - stages_data[-1]) <= 0.03:
            print(f"    -> UNIFORM: excess stable across career -> consistent with aversion")
        else:
            print(f"    -> BACK-LOADED: excess grows -> ???")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: STYLE CONFOUND (wrestling control)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 3: STYLE CONFOUND")
print("Does nation excess survive controlling for wrestling style?")
print(f"{'='*72}")

# For each fight-row: excess = win - p_mkt
# Regress: excess ~ region_dummies + wrestling_score
# If region coefficient survives, it's not about style

# Simpler: compare excess of wrestlers vs non-wrestlers WITHIN each nation
# and across nations

# Median wrestling score
med_wrestling = df['wrestling_score'].median()
print(f"\n  Median wrestling score: {med_wrestling:.2f}")

# For each top under-priced region: split by wrestling style
for region in top_regions[:3]:
    sub = df[df['region'] == region]
    wrestlers = sub[sub['wrestling_score'] > med_wrestling]
    strikers = sub[sub['wrestling_score'] <= med_wrestling]
    print(f"\n  {region}:")
    for label, s in [('Wrestlers (above median)', wrestlers), ('Strikers (below median)', strikers)]:
        if len(s) < 10:
            print(f"    {label}: {len(s)} rows (too few)")
            continue
        exc = s['win'].mean() - s['p_mkt'].mean()
        print(f"    {label:<30s} N={len(s):>4}, excess={exc:+.3f}")

# Cross-nation comparison: are ALL wrestlers under-priced regardless of nation?
print(f"\n  CROSS-NATION WRESTLING CHECK:")
print(f"  If 'public overbets strikers' is the story, ALL nations' wrestlers should be under-priced")
print(f"\n  {'Region':<22s} {'N wrest':>7} {'Exc wrest':>10} {'N strik':>7} {'Exc strik':>10} {'Diff':>7}")
print("  " + "-" * 70)
for r_info in results[:10]:
    region = r_info['region']
    sub = df[df['region'] == region]
    w = sub[sub['wrestling_score'] > med_wrestling]
    s = sub[sub['wrestling_score'] <= med_wrestling]
    if len(w) >= 10 and len(s) >= 10:
        exc_w = w['win'].mean() - w['p_mkt'].mean()
        exc_s = s['win'].mean() - s['p_mkt'].mean()
        print(f"  {region:<22s} {len(w):>7} {exc_w:>+9.3f} {len(s):>7} {exc_s:>+9.3f} {exc_w-exc_s:>+6.3f}")

# Logistic regression with wrestling control
print(f"\n  LOGISTIC: win ~ mkt_prob + region_Caucasus + wrestling_score")

# Build dataset for regression
reg_data = df[df['region'].isin(['USA', 'Caucasus'])].copy()
reg_data['is_caucasus'] = (reg_data['region'] == 'Caucasus').astype(float)

def neg_ll_reg(params, mkt, caucasus, wrestling, y):
    z = params[0] + params[1]*mkt + params[2]*caucasus + params[3]*wrestling
    p = np.clip(expit(z), 1e-10, 1-1e-10)
    return -np.sum(y*np.log(p) + (1-y)*np.log(1-p))

mkt_v = reg_data['p_mkt'].values
cauc_v = reg_data['is_caucasus'].values
wrest_v = reg_data['wrestling_score'].values
y_v = reg_data['win'].values

# Without wrestling
res_no_w = minimize(lambda p: neg_ll_reg(p, mkt_v, cauc_v, np.zeros_like(wrest_v), y_v),
                    [0, 1, 0, 0], method='Nelder-Mead', options={'maxiter': 10000})
# With wrestling
res_w_w = minimize(lambda p: neg_ll_reg(p, mkt_v, cauc_v, wrest_v, y_v),
                   [0, 1, 0, 0], method='Nelder-Mead', options={'maxiter': 10000})

print(f"\n    Without wrestling control:")
print(f"      intercept={res_no_w.x[0]:+.3f}, mkt={res_no_w.x[1]:+.3f}, caucasus={res_no_w.x[2]:+.3f}")
print(f"    With wrestling control:")
print(f"      intercept={res_w_w.x[0]:+.3f}, mkt={res_w_w.x[1]:+.3f}, caucasus={res_w_w.x[2]:+.3f}, wrestling={res_w_w.x[3]:+.3f}")
reduction = 1 - abs(res_w_w.x[2]) / max(abs(res_no_w.x[2]), 0.001)
print(f"    Caucasus coefficient reduction: {reduction:.0%}")
if reduction > 0.5:
    print(f"    -> Wrestling control ABSORBS most of the Caucasus excess")
    print(f"       Story: 'public overbets strikers vs wrestlers', not nation aversion")
else:
    print(f"    -> Caucasus excess SURVIVES wrestling control")
    print(f"       Consistent with nation-specific mispricing")


# ═══════════════════════════════════════════════════════════════════
# TEST 4: THE MIRROR — BELOVED NATIONS OVERPRICED?
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 4: THE MIRROR — BELOVED NATIONS OVERPRICED?")
print("Symmetric pattern = taste-based; asymmetric = noise")
print(f"{'='*72}")

# Brazil is the candidate: large, popular, heavily-backed
brazil = [r for r in results if r['region'] == 'Brazil']
if brazil:
    b = brazil[0]
    print(f"\n  Brazil: N={b['n']}, excess={b['excess']:+.3f}, vs US={b['relative']:+.3f} [{b['ci_lo']:+.3f},{b['ci_hi']:+.3f}]")
    if b['relative'] < -0.01:
        print(f"  -> Brazil is OVER-PRICED (negative excess vs US)")
        print(f"     Symmetric with Caucasus under-pricing = taste-based bias")
    elif b['relative'] > 0.01:
        print(f"  -> Brazil is ALSO under-priced — no symmetric pattern")
    else:
        print(f"  -> Brazil is fairly priced")

# List all over-priced nations
overpriced = [r for r in results if r['relative'] < -0.02 and r['n'] >= 30]
underpriced = [r for r in results if r['relative'] > 0.02 and r['n'] >= 30]
print(f"\n  Under-priced (vs US, >2pp, N>=30): {[r['region'] for r in underpriced]}")
print(f"  Over-priced  (vs US, <-2pp, N>=30): {[r['region'] for r in overpriced]}")


# ═══════════════════════════════════════════════════════════════════
# TEST 5: ERA + PERSISTENCE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 5: ERA + PERSISTENCE")
print(f"{'='*72}")

for region in top_regions[:3]:
    sub = df[df['region'] == region]
    print(f"\n  {region}:")
    print(f"    {'Era':<20s} {'N':>5} {'WR':>5} {'Mkt':>5} {'Excess':>7}")
    print("    " + "-" * 45)
    for label, yr_lo, yr_hi in [('2007-2015', 2007, 2015), ('2016-2020', 2016, 2020),
                                  ('2021-2023', 2021, 2023), ('2024-2025', 2024, 2025)]:
        era = sub[(sub['year'] >= yr_lo) & (sub['year'] <= yr_hi)]
        if len(era) < 5:
            print(f"    {label:<20s} {len(era):>5} (too few)")
            continue
        wr = era['win'].mean()
        mkt = era['p_mkt'].mean()
        exc = wr - mkt
        print(f"    {label:<20s} {len(era):>5} {wr:>4.0%} {mkt:>4.0%} {exc:>+6.3f}")

# ═══════════════════════════════════════════════════════════════════
# TEST 5b: UKRAINE WAR EFFECT (post March 2022)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 5b: UKRAINE WAR EFFECT (pre vs post March 2022)")
print("Does Russian/Caucasus excess change after invasion?")
print(f"{'='*72}")

for region in ['Caucasus', 'Russia (ethnic)']:
    sub = df[df['region'] == region]
    if len(sub) < 20:
        print(f"\n  {region}: too few rows ({len(sub)})")
        continue
    pre = sub[sub['post_ukraine'] == 0]
    post = sub[sub['post_ukraine'] == 1]
    print(f"\n  {region}:")
    for label, s in [('Pre-war (before Mar 2022)', pre), ('Post-war (Mar 2022+)', post)]:
        if len(s) < 5:
            print(f"    {label}: {len(s)} rows (too few)")
            continue
        wr = s['win'].mean()
        mkt = s['p_mkt'].mean()
        exc = wr - mkt
        # Bootstrap
        n = len(s)
        boots = [s['win'].values[rng.choice(n,n,replace=True)].mean() -
                 s['p_mkt'].values[rng.choice(n,n,replace=True)].mean()
                 for _ in range(N_BOOT)]
        lo, hi = np.percentile(boots, [2.5, 97.5])
        sig = 'YES' if (lo > 0 or hi < 0) else 'no'
        print(f"    {label:<30s} N={len(s):>4}, WR={wr:.0%}, mkt={mkt:.0%}, excess={exc:+.3f} [{lo:+.3f},{hi:+.3f}] sig={sig}")

    # Difference in excess
    if len(pre) >= 5 and len(post) >= 5:
        exc_pre = pre['win'].mean() - pre['p_mkt'].mean()
        exc_post = post['win'].mean() - post['p_mkt'].mean()
        diff = exc_post - exc_pre
        # Bootstrap difference
        boots_diff = []
        for _ in range(N_BOOT):
            n_pre, n_post = len(pre), len(post)
            bi_pre = rng.choice(n_pre, n_pre, replace=True)
            bi_post = rng.choice(n_post, n_post, replace=True)
            b_pre = pre['win'].values[bi_pre].mean() - pre['p_mkt'].values[bi_pre].mean()
            b_post = post['win'].values[bi_post].mean() - post['p_mkt'].values[bi_post].mean()
            boots_diff.append(b_post - b_pre)
        lo_d, hi_d = np.percentile(boots_diff, [2.5, 97.5])
        sig_d = 'YES' if (lo_d > 0 or hi_d < 0) else 'no'
        print(f"    Diff (post - pre): {diff:+.3f} [{lo_d:+.3f},{hi_d:+.3f}] sig={sig_d}")
        if diff > 0.02:
            print(f"    -> Post-war excess is LARGER: consistent with increased aversion")
        elif diff < -0.02:
            print(f"    -> Post-war excess is SMALLER: aversion story doesn't fit")
        else:
            print(f"    -> No change: stable or underpowered")


# ═══════════════════════════════════════════════════════════════════
# TEST 6: BETTING ROI (if anything survives)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 6: BETTING ROI (flat-stake at fair odds)")
print(f"{'='*72}")

for region in top_regions[:3]:
    sub = df[df['region'] == region]
    # Bet on this fighter every fight at fair odds (1/p_mkt)
    profits = (1/sub['p_mkt'].values) * sub['win'].values - 1
    roi = profits.mean()
    n = len(profits)
    boots = [profits[rng.choice(n,n,replace=True)].mean() for _ in range(N_BOOT)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"  {region}: N={n}, ROI={roi:+.1%} [{lo:+.1%},{hi:+.1%}] sig={sig}")

    # Held-out (2024-25 only)
    test_sub = sub[sub['year'].isin([2024, 2025])]
    if len(test_sub) >= 10:
        prof_test = (1/test_sub['p_mkt'].values) * test_sub['win'].values - 1
        roi_test = prof_test.mean()
        print(f"    2024-25 held-out: N={len(test_sub)}, ROI={roi_test:+.1%}")


# ═══════════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("VERDICT")
print(f"{'='*72}")

print(f"""
  SIN-STOCK CHECKLIST:
  (a) Nation excess survives multiplicity?
  (b) Uniform across career (aversion), not front-loaded (learning)?
  (c) Survives wrestling style control?
  (d) Persists into 2024-25?
  (e) Symmetric mirror (beloved nation overpriced)?
  (f) Post-Ukraine war amplification?

  Each check narrows the interpretation. Report honestly.
""")
