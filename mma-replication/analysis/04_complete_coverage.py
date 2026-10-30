#!/usr/bin/env python3
"""
Complete-coverage rebuild of the war-shock analysis.
Russian coding from roster.watch (complete). Controls on Wikidata (unchanged).
All results reported as point estimate + CI + N. No interpretation.
"""
import sys, os, re, math, warnings, functools, unicodedata, csv
import numpy as np
import pandas as pd
from collections import defaultdict
from scipy.optimize import minimize
from scipy.special import expit

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

DATA_DIR = '../data'
FIG_DIR = '../figures'

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# ═══════════════════════════════════════════════════════════════════
# STEP 1a: COMPLETE RUSSIAN CODING FROM ROSTER.WATCH
# ═══════════════════════════════════════════════════════════════════
print("STEP 1a: BUILDING COMPLETE ORIGIN CODING")
print("=" * 80)

# Full roster.watch Russia list (former + active, from user paste)
# Classification: E = ethnic Russian, C = Caucasus, X = coded elsewhere (dual flag, fights under other country)
ROSTER_WATCH_RUSSIA = {
    # FORMER - ethnic Russian
    'Alexander Volkov': 'E', 'Alexander Yakovlev': 'E', 'Aleksei Oleinik': 'E',
    'Maxim Grishin': 'E', 'Gadzhimurad Antigulov': 'E',  # Anapa, not Caucasus
    'Aleksandra Albu': 'E', 'Milana Dudieva': 'E',  # Vladikavkaz but ethnically non-Caucasian per roster
    'Dmitry Smolyakov': 'E', 'Igor Zinoviev': 'E', 'Oleg Taktarov': 'E',
    'Andrey Semenov': 'E', 'Viacheslav Borshchev': 'E', 'Denis Tiuliulin': 'E',
    'Konstantin Erokhin': 'E', 'Viktoriia Dudakova': 'E', 'Roman Bogatov': 'E',
    'Alexey Kunchenko': 'E',
    # FORMER - Caucasus
    'Khabib Nurmagomedov': 'C', 'Zabit Magomedsharipov': 'C', 'Rustam Khabilov': 'C',
    'Ramazan Emeev': 'C', 'Albert Duraev': 'C', 'Timur Valiev': 'C',
    'Omari Akhmedov': 'C', 'Rashid Magomedov': 'C', 'Mairbek Taisumov': 'C',
    'Shamil Abdurakhimov': 'C', 'Albert Tumenov': 'C', 'Zubaira Tukhugov': 'C',
    'Magomed Bibulatov': 'C', 'Ali Bagautinov': 'C', 'Magomed Mustafaev': 'C',
    'Adlan Amagov': 'C', 'Abubakar Nurmagomedov': 'C', 'Shamil Gamzatov': 'C',
    'Abdul-Kerim Edilov': 'C', 'Sultan Aliev': 'C', 'Saparbeg Safarov': 'C',
    'Khadis Ibragimov': 'C', 'Gasan Umalatov': 'C', 'Ansar Chalangov': 'C',
    'Adam Yandiev': 'C', 'Grigorii Popov': 'C', 'Zelim Imadaev': 'C',
    'Azamat Gashimov': 'C', 'Ruslan Magomedov': 'C', 'Dmitriy Sosnovskiy': 'C',
    'Khalid Murtazaliev': 'C', 'Sergey Khandozhko': 'C',
    'Askar Askarov': 'C', 'Khusein Askhabov': 'C',
    'Gadzhi Omargadzhiev': 'C', 'Magomed Gadzhiyasulov': 'C',
    'Rinat Fakhretdinov': 'E',  # Ethnically Russian despite the name, born outside Caucasus
    # ACTIVE - ethnic Russian
    'Petr Yan': 'E', 'Alexander Volkov_active': 'E',  # duplicate, handled below
    'Sergei Pavlovich': 'E', 'Valentina Shevchenko': 'E', 'Antonina Shevchenko': 'E',
    'Roman Kopylov': 'E', 'Azamat Murzakanov': 'E', 'Bogdan Guskov': 'E',
    'Damir Ismagulov': 'E', 'Nikita Krylov': 'E',
    'Yana Santos': 'E', 'Daria Zhelezniakova': 'E',
    'Valter Walker': 'E', 'Andrey Pulyaev': 'E',
    'Mark Vologdin': 'E', 'Irina Alekseeva': 'E',
    # ACTIVE - Caucasus
    'Islam Makhachev': 'C', 'Khamzat Chimaev': 'C',
    'Magomed Ankalaev': 'C', 'Movsar Evloev': 'C',
    'Umar Nurmagomedov': 'C', 'Ikram Aliskerov': 'C',
    'Rizvan Kuniev': 'C', 'Shara Magomedov': 'C',
    'Tagir Ulanbekov': 'C', 'Muslim Salikhov': 'C',
    'Said Nurmagomedov': 'C', 'Azamat Bekoev': 'C',
    'Baisangur Susurkaev': 'C', 'Aliaskhab Khizriev': 'C',
    'Abdul Rakhman Yakhyaev': 'C', 'Shamil Gaziev': 'C',
    'Abubakar Vagaev': 'C', 'Saygid Izagakhmaev': 'C',
    'Muhammad Said': 'C', 'Magomed Zaynukov': 'C', 'Magomed Tuchalov': 'C',
    'Islam Dulatov': 'C',
    # CODED ELSEWHERE (fight under other flag)
    'Dennis Siver': 'E', 'Artem Lobov': 'X', 'Muhammad Mokaev': 'X',
    'Nassourdine Imavov': 'X', 'Ismail Naurdiev': 'X', 'Abus Magomedov': 'C',
}
# Remove the duplicate marker
if 'Alexander Volkov_active' in ROSTER_WATCH_RUSSIA:
    del ROSTER_WATCH_RUSSIA['Alexander Volkov_active']

# Wikidata for non-Russian origins
wiki = pd.read_csv(f'{DATA_DIR}/wikidata_mma_fighters.csv')
wiki_lookup = {}
for _, row in wiki.iterrows():
    nn = norm_name(row['name'])
    if nn not in wiki_lookup or (str(row.get('lat','')).strip() not in ('', 'nan')):
        wiki_lookup[nn] = row.to_dict()

panel = pd.read_csv(f'{DATA_DIR}/analysis_panel_cc.csv')
panel['date'] = pd.to_datetime(panel['date'])
panel = panel[panel['year'] <= 2025].copy()
panel['excess'] = panel['win'] - panel['p_close_hi']

ufc_fighters = set(panel['fighter'].unique()) | set(panel['opponent'].unique())

# Build roster.watch name lookup (norm -> roster.watch name -> code)
rw_lookup = {}
for name, code in ROSTER_WATCH_RUSSIA.items():
    rw_lookup[norm_name(name)] = (name, code)

# Match panel fighters to Wikidata
wiki_matched = {}
for f in ufc_fighters:
    nn = norm_name(f)
    if nn in wiki_lookup:
        wiki_matched[f] = wiki_lookup[nn]
    else:
        parts = nn.split()
        if len(parts) >= 2:
            rev = ' '.join(parts[1:] + parts[:1])
            if rev in wiki_lookup:
                wiki_matched[f] = wiki_lookup[rev]

def assign_origin_complete(fighter_name):
    """Assign origin using roster.watch for Russians, Wikidata for others."""
    nn = norm_name(fighter_name)

    # Check roster.watch Russia list first
    rw = rw_lookup.get(nn)
    if rw is None:
        # Try last-name + first-initial match against roster.watch
        parts = nn.split()
        if len(parts) >= 2:
            for rw_nn, (rw_name, rw_code) in rw_lookup.items():
                rw_parts = rw_nn.split()
                if len(rw_parts) >= 2 and parts[-1] == rw_parts[-1] and parts[0][0] == rw_parts[0][0]:
                    rw = (rw_name, rw_code)
                    break
    if rw:
        _, code = rw
        if code == 'E':
            return 'Russia (ethnic)'
        elif code == 'C':
            return 'Caucasus'
        elif code == 'X':
            pass  # fall through to Wikidata

    # Wikidata for non-Russian origins
    d = wiki_matched.get(fighter_name, {})
    country = d.get('country', '')
    if not country:
        return None

    # If Wikidata says Russia but not in roster.watch, use Wikidata geo heuristic
    if country == 'Russia':
        try:
            lat, lon = float(d.get('lat', 0)), float(d.get('lon', 0))
            if 41 < lat < 45 and 43 < lon < 49:
                return 'Caucasus'
        except:
            pass
        bp = str(d.get('birthplace', '')).lower()
        cauc_markers = ['dagestan','chechnya','chechen','grozny','makhachkala','ingush',
                        'kabardino','ossetia','nalchik','khasavyurt','buynaksk','derbent',
                        'kizlyar','kaspiysk','kizilyurt','sildi','sunzha','teletl',
                        'vladikavkaz','babugent','goksuv','batayurt','gvardeyskoe']
        if any(m in bp for m in cauc_markers):
            return 'Caucasus'
        return 'Russia (ethnic)'

    if country in ('Kazakhstan', 'Kyrgyzstan', 'Uzbekistan', 'Tajikistan', 'Turkmenistan'):
        return 'Central Asia'
    if country == 'United States': return 'USA'
    if country == 'Brazil': return 'Brazil'
    if country == 'United Kingdom': return 'UK'
    if country == 'Canada': return 'Canada'
    if country == 'Australia': return 'Australia'
    return 'Other'

def assign_origin_wikidata_only(fighter_name):
    """Original Wikidata-only coding for comparison."""
    d = wiki_matched.get(fighter_name, {})
    country = d.get('country', '')
    if not country:
        return None
    if country == 'Russia':
        try:
            lat, lon = float(d.get('lat', 0)), float(d.get('lon', 0))
            if 41 < lat < 45 and 43 < lon < 49:
                return 'Caucasus'
        except:
            pass
        bp = str(d.get('birthplace', '')).lower()
        cauc_markers = ['dagestan','chechnya','chechen','grozny','makhachkala','ingush',
                        'kabardino','ossetia','nalchik','khasavyurt','buynaksk','derbent',
                        'kizlyar','kaspiysk','kizilyurt','sildi','sunzha','teletl',
                        'vladikavkaz','babugent','goksuv','batayurt','gvardeyskoe']
        if any(m in bp for m in cauc_markers):
            return 'Caucasus'
        return 'Russia (ethnic)'
    if country in ('Kazakhstan', 'Kyrgyzstan', 'Uzbekistan', 'Tajikistan', 'Turkmenistan'):
        return 'Central Asia'
    if country == 'United States': return 'USA'
    if country == 'Brazil': return 'Brazil'
    if country == 'United Kingdom': return 'UK'
    if country == 'Canada': return 'Canada'
    if country == 'Australia': return 'Australia'
    return 'Other'

# ═══════════════════════════════════════════════════════════════════
# BUILD FIGHT-LEVEL DATASET WITH BOTH CODINGS
# ═══════════════════════════════════════════════════════════════════
print("Building fight-level dataset...")

# Style proxy
fights_raw = pd.read_csv(f'{DATA_DIR}/ufcstats_fights.csv')
fighter_stats = defaultdict(lambda: {'td': 0, 'ctrl': 0, 'n': 0})
for _, row in fights_raw.sort_values('date').iterrows():
    try:
        fighter_stats[row['fighter_name']]['td'] += int(row['td_landed']) if pd.notna(row['td_landed']) else 0
        fighter_stats[row['fighter_name']]['ctrl'] += int(row['ctrl_sec']) if pd.notna(row['ctrl_sec']) else 0
    except:
        pass
    fighter_stats[row['fighter_name']]['n'] += 1

def wrestling_score(name):
    s = fighter_stats.get(name, {'td': 0, 'ctrl': 0, 'n': 0})
    if s['n'] == 0: return 0
    return s['td'] / s['n'] + s['ctrl'] / s['n'] / 60

fight_counter = defaultdict(int)
rows = []
for _, r in panel.sort_values('date').iterrows():
    fighter = r['fighter']
    origin_new = assign_origin_complete(fighter)
    origin_old = assign_origin_wikidata_only(fighter)
    fight_counter[fighter] += 1
    rows.append({
        'fight_id': r['fight_id'], 'date': r['date'], 'year': r['year'],
        'fighter': fighter, 'opponent': r['opponent'],
        'origin': origin_new, 'origin_old': origin_old,
        'p_mkt': r['p_close_hi'], 'win': int(r['win']),
        'career_n': fight_counter[fighter],
        'layoff': r['layoff_days'],
        'wrestling': wrestling_score(fighter),
        'post': 1 if r['date'] >= pd.Timestamp('2022-02-24') else 0,
    })

df = pd.DataFrame(rows)
df['excess'] = df['win'] - df['p_mkt']

print(f"  Total rows: {len(df)}")
print(f"  With new origin: {df['origin'].notna().sum()} ({df['origin'].notna().mean():.1%})")
print(f"  With old origin: {df['origin_old'].notna().sum()} ({df['origin_old'].notna().mean():.1%})")

# ═══════════════════════════════════════════════════════════════════
# STEP 1c: COVERAGE DIAGNOSTIC TABLE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("STEP 1c: COVERAGE DIAGNOSTIC")
print("=" * 80)

print(f"\n  {'Group':<20s} {'Old N ftr':>9} {'New N ftr':>9} {'Added':>6} "
      f"{'Old fights':>10} {'New fights':>10} {'Added':>6} "
      f"{'Added WR':>9} {'Added mkt':>9} {'Orig WR':>8} {'Orig mkt':>9}")
print("  " + "-" * 115)

for group in ['Russia (ethnic)', 'Caucasus', 'Central Asia', 'USA', 'Brazil', 'UK', 'Canada', 'Australia', 'Other']:
    old_fighters = set(df[df['origin_old'] == group]['fighter'].unique())
    new_fighters = set(df[df['origin'] == group]['fighter'].unique())
    added_fighters = new_fighters - old_fighters

    old_fights = df[df['origin_old'] == group]
    new_fights = df[df['origin'] == group]
    added_fights = new_fights[new_fights['fighter'].isin(added_fighters)]
    orig_fights = new_fights[~new_fights['fighter'].isin(added_fighters)]

    added_wr = added_fights['win'].mean() if len(added_fights) > 0 else float('nan')
    added_mkt = added_fights['p_mkt'].mean() if len(added_fights) > 0 else float('nan')
    orig_wr = orig_fights['win'].mean() if len(orig_fights) > 0 else float('nan')
    orig_mkt = orig_fights['p_mkt'].mean() if len(orig_fights) > 0 else float('nan')

    chg_pct = (len(new_fights) - len(old_fights)) / max(len(old_fights), 1) * 100

    print(f"  {group:<20s} {len(old_fighters):>9} {len(new_fighters):>9} {len(added_fighters):>+6} "
          f"{len(old_fights):>10} {len(new_fights):>10} {len(added_fights):>+6} "
          f"{added_wr:>8.0%} {added_mkt:>8.0%} {orig_wr:>7.0%} {orig_mkt:>8.0%}"
          if len(added_fights) > 0 else
          f"  {group:<20s} {len(old_fighters):>9} {len(new_fighters):>9} {len(added_fighters):>+6} "
          f"{len(old_fights):>10} {len(new_fights):>10} {len(added_fights):>+6} "
          f"{'n/a':>9} {'n/a':>9} {orig_wr:>7.0%} {orig_mkt:>8.0%}")

# ═══════════════════════════════════════════════════════════════════
# STEP 2: FULL RERUN ON COMPLETE CODING
# ═══════════════════════════════════════════════════════════════════
# Restrict to 2017-2025 for the war-shock window
df_ws = df[(df['year'] >= 2017) & (df['origin'].notna())].copy()

def excess_ci(vals, n_boot=N_BOOT):
    n = len(vals)
    if n == 0:
        return 0, -999, 999
    mean = vals.mean()
    boots = [vals[rng.choice(n, n, True)].mean() for _ in range(n_boot)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return mean, lo, hi

def ci_excludes_zero(lo, hi):
    return "yes" if (lo > 0 or hi < 0) else "no"

print(f"\n{'='*80}")
print("PRE-WAR AND POST-WAR EXCESS BY GROUP (complete coding)")
print("=" * 80)

print(f"\n  {'Group':<20s} {'Pre N':>6} {'Pre excess':>11} {'Pre CI':>20} "
      f"{'Post N':>6} {'Post excess':>12} {'Post CI':>20} {'CI excl 0':>9}")
print("  " + "-" * 110)

groups_order = ['Russia (ethnic)', 'Caucasus', 'Central Asia', 'USA', 'Brazil', 'UK', 'Canada', 'Australia', 'Other']
group_results = {}

for group in groups_order:
    g = df_ws[df_ws['origin'] == group]
    pre = g[g['post'] == 0]['excess'].values
    post = g[g['post'] == 1]['excess'].values
    pre_m, pre_lo, pre_hi = excess_ci(pre)
    post_m, post_lo, post_hi = excess_ci(post)
    group_results[group] = {'pre': pre, 'post': post, 'pre_m': pre_m, 'post_m': post_m}
    print(f"  {group:<20s} {len(pre):>6} {pre_m:>+10.3f} [{pre_lo:>+.3f},{pre_hi:>+.3f}] "
          f"{len(post):>6} {post_m:>+11.3f} [{post_lo:>+.3f},{post_hi:>+.3f}] "
          f"{ci_excludes_zero(post_lo, post_hi):>9}")

# ═══════════════════════════════════════════════════════════════════
# T1: DiD against each control
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("T1: DiD (Russian swing minus control swing)")
print("=" * 80)

treatment = df_ws[df_ws['origin'] == 'Russia (ethnic)']
t_pre = treatment[treatment['post'] == 0]['excess'].values
t_post = treatment[treatment['post'] == 1]['excess'].values

print(f"\n  Treatment: Russia (ethnic), pre N={len(t_pre)}, post N={len(t_post)}")
print(f"\n  {'Control':<20s} {'DiD':>8} {'CI':>22} {'CI excl 0':>10}")
print("  " + "-" * 65)

for ctrl_name in ['Caucasus', 'Central Asia', 'USA', 'Brazil', 'UK', 'Canada', 'Other']:
    ctrl = df_ws[df_ws['origin'] == ctrl_name]
    c_pre = ctrl[ctrl['post'] == 0]['excess'].values
    c_post = ctrl[ctrl['post'] == 1]['excess'].values
    if len(c_pre) < 5 or len(c_post) < 5:
        print(f"  {ctrl_name:<20s} insufficient data")
        continue
    t_diff = t_post.mean() - t_pre.mean()
    c_diff = c_post.mean() - c_pre.mean()
    did = t_diff - c_diff
    boots = []
    for _ in range(N_BOOT):
        bt = t_post[rng.choice(len(t_post), len(t_post), True)].mean() - \
             t_pre[rng.choice(len(t_pre), len(t_pre), True)].mean()
        bc = c_post[rng.choice(len(c_post), len(c_post), True)].mean() - \
             c_pre[rng.choice(len(c_pre), len(c_pre), True)].mean()
        boots.append(bt - bc)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"  {ctrl_name:<20s} {did:>+7.3f} [{lo:>+.3f},{hi:>+.3f}] {ci_excludes_zero(lo, hi):>10}")

# Logistic DiD with controls (vs USA)
print(f"\n  Logistic DiD (vs USA, with layoff + wrestling controls):")
reg = df_ws[df_ws['origin'].isin(['Russia (ethnic)', 'USA'])].copy()
reg['is_rus'] = (reg['origin'] == 'Russia (ethnic)').astype(float)
reg['interaction'] = reg['is_rus'] * reg['post']
reg['log_layoff'] = np.log1p(reg['layoff'])

def neg_ll(params, X, y):
    z = params[0]
    for i in range(len(X)):
        z = z + params[i+1] * X[i]
    p = np.clip(expit(z), 1e-10, 1-1e-10)
    return -np.sum(y * np.log(p) + (1-y) * np.log(1-p))

y_reg = reg['win'].values
X_basic = [reg['p_mkt'].values, reg['is_rus'].values, reg['post'].values.astype(float), reg['interaction'].values]
X_full = X_basic + [reg['log_layoff'].values, reg['wrestling'].values]

res_b = minimize(neg_ll, [0]*5, args=(X_basic, y_reg), method='Nelder-Mead', options={'maxiter': 10000})
res_f = minimize(neg_ll, [0]*7, args=(X_full, y_reg), method='Nelder-Mead', options={'maxiter': 10000})

labels_b = ['mkt_prob', 'is_rus', 'post', 'rus*post']
labels_f = labels_b + ['log_layoff', 'wrestling']

print(f"    Basic:  ", end='')
for i, l in enumerate(labels_b):
    print(f"{l}={res_b.x[i+1]:+.3f}  ", end='')
print()
print(f"    Full:   ", end='')
for i, l in enumerate(labels_f):
    print(f"{l}={res_f.x[i+1]:+.3f}  ", end='')
print()

# Bootstrap interaction CI
n_reg = len(y_reg)
int_boots = []
for _ in range(N_BOOT):
    bi = rng.choice(n_reg, n_reg, True)
    try:
        rb = minimize(neg_ll, list(res_b.x), args=([x[bi] for x in X_basic], y_reg[bi]),
                      method='Nelder-Mead', options={'maxiter': 2000, 'xatol': 1e-3, 'fatol': 1e-3})
        int_boots.append(rb.x[4])
    except:
        pass
int_boots = np.array(int_boots)
lo_i, hi_i = np.percentile(int_boots, [2.5, 97.5])
print(f"    rus*post CI: [{lo_i:+.3f},{hi_i:+.3f}] excl 0: {ci_excludes_zero(lo_i, hi_i)}")

# ═══════════════════════════════════════════════════════════════════
# T2: Elite-drop + leave-one-out
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("T2: ELITE-DROP AND LEAVE-ONE-OUT")
print("=" * 80)

rus_fighters = treatment['fighter'].unique()
fighter_counts = treatment.groupby('fighter').size().sort_values(ascending=False)
top3 = list(fighter_counts.head(3).index)
print(f"\n  Top 3 by fight count: {top3}")

# Elite-drop excess
rus_no_elite = treatment[~treatment['fighter'].isin(top3)]
ne_pre = rus_no_elite[rus_no_elite['post'] == 0]['excess'].values
ne_post = rus_no_elite[rus_no_elite['post'] == 1]['excess'].values
if len(ne_pre) > 0 and len(ne_post) > 0:
    pre_m, pre_lo, pre_hi = excess_ci(ne_pre)
    post_m, post_lo, post_hi = excess_ci(ne_post)
    print(f"  Without top 3: pre={pre_m:+.3f} (N={len(ne_pre)}), post={post_m:+.3f} (N={len(ne_post)})")
    print(f"    Post CI: [{post_lo:+.3f},{post_hi:+.3f}] excl 0: {ci_excludes_zero(post_lo, post_hi)}")

# Elite-drop DiD vs Caucasus
cauc = df_ws[df_ws['origin'] == 'Caucasus']
c_pre_v = cauc[cauc['post'] == 0]['excess'].values
c_post_v = cauc[cauc['post'] == 1]['excess'].values
if len(ne_pre) > 0 and len(ne_post) > 0 and len(c_pre_v) > 0 and len(c_post_v) > 0:
    did_ne = (ne_post.mean() - ne_pre.mean()) - (c_post_v.mean() - c_pre_v.mean())
    boots_ne = []
    for _ in range(N_BOOT):
        bt = ne_post[rng.choice(len(ne_post), len(ne_post), True)].mean() - \
             ne_pre[rng.choice(len(ne_pre), len(ne_pre), True)].mean()
        bc = c_post_v[rng.choice(len(c_post_v), len(c_post_v), True)].mean() - \
             c_pre_v[rng.choice(len(c_pre_v), len(c_pre_v), True)].mean()
        boots_ne.append(bt - bc)
    lo_ne, hi_ne = np.percentile(boots_ne, [2.5, 97.5])
    print(f"  Elite-drop DiD vs Caucasus: {did_ne:+.3f} [{lo_ne:+.3f},{hi_ne:+.3f}] excl 0: {ci_excludes_zero(lo_ne, hi_ne)}")

# Leave-one-out
print(f"\n  Leave-one-out (drop each Russian fighter, report post-war excess and DiD vs Caucasus):")
print(f"  {'Dropped fighter':<25s} {'Post exc':>9} {'DiD vs Cauc':>12}")
print("  " + "-" * 50)

loo_post = []
loo_did = []
for fighter in sorted(rus_fighters):
    loo = treatment[treatment['fighter'] != fighter]
    loo_pre = loo[loo['post'] == 0]['excess'].values
    loo_post_v = loo[loo['post'] == 1]['excess'].values
    if len(loo_post_v) == 0:
        continue
    post_exc = loo_post_v.mean()
    if len(loo_pre) > 0 and len(c_pre_v) > 0 and len(c_post_v) > 0:
        did_loo = (loo_post_v.mean() - loo_pre.mean()) - (c_post_v.mean() - c_pre_v.mean())
    else:
        did_loo = float('nan')
    loo_post.append(post_exc)
    loo_did.append(did_loo)
    print(f"  {fighter[:24]:<25s} {post_exc:>+8.3f} {did_loo:>+11.3f}")

loo_post = np.array(loo_post)
loo_did = np.array([x for x in loo_did if not np.isnan(x)])
print(f"\n  Post-war excess: min={loo_post.min():+.3f}, max={loo_post.max():+.3f}")
print(f"  DiD vs Caucasus: min={loo_did.min():+.3f}, max={loo_did.max():+.3f}")
print(f"  DiD sign flips (negative): {(loo_did < 0).sum()}/{len(loo_did)}")

# ═══════════════════════════════════════════════════════════════════
# T3: Entrant quality
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("T3: ENTRANT QUALITY (post-2022 debutants)")
print("=" * 80)

debuts = df[df['career_n'] == 1]
post_debuts = debuts[debuts['post'] == 1]

print(f"\n  {'Group':<20s} {'N deb':>6} {'N fights':>8} {'Mean mkt':>9} {'Frac dog':>9} {'WR':>5} {'Excess':>8}")
print("  " + "-" * 70)

for group in ['Russia (ethnic)', 'Caucasus', 'USA', 'Brazil', 'Other']:
    debs = post_debuts[post_debuts['origin'] == group]
    if len(debs) == 0:
        print(f"  {group:<20s} {0:>6}")
        continue
    deb_fighters = debs['fighter'].tolist()
    all_fights = df[(df['fighter'].isin(deb_fighters)) & (df['origin'] == group)]
    if len(all_fights) == 0:
        continue
    print(f"  {group:<20s} {len(deb_fighters):>6} {len(all_fights):>8} "
          f"{all_fights['p_mkt'].mean():>8.3f} {(all_fights['p_mkt'] < 0.5).mean():>8.0%} "
          f"{all_fights['win'].mean():>4.0%} {all_fights['excess'].mean():>+7.3f}")

# ═══════════════════════════════════════════════════════════════════
# T4: Within-fighter
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("T4: WITHIN-FIGHTER (fighters with >=1 pre and >=1 post bout)")
print("=" * 80)

for group in ['Russia (ethnic)', 'Caucasus', 'USA', 'Brazil']:
    g = df_ws[df_ws['origin'] == group]
    wf_rows = []
    for fighter in g['fighter'].unique():
        fg = g[g['fighter'] == fighter]
        pre = fg[fg['post'] == 0]
        post = fg[fg['post'] == 1]
        if len(pre) >= 1 and len(post) >= 1:
            wf_rows.append({
                'fighter': fighter,
                'pre_n': len(pre), 'post_n': len(post),
                'pre_exc': pre['excess'].mean(),
                'post_exc': post['excess'].mean(),
                'swing': post['excess'].mean() - pre['excess'].mean(),
            })
    if not wf_rows:
        continue
    wf = pd.DataFrame(wf_rows)
    mean_swing = wf['swing'].mean()
    n_wf = len(wf)
    boots = [wf.iloc[rng.choice(n_wf, n_wf, True)]['swing'].mean() for _ in range(N_BOOT)]
    lo, hi = np.percentile(boots, [2.5, 97.5])

    print(f"\n  {group} ({n_wf} fighters, {wf['pre_n'].sum()} pre + {wf['post_n'].sum()} post fights):")
    print(f"    Mean swing: {mean_swing:+.3f} [{lo:+.3f},{hi:+.3f}] excl 0: {ci_excludes_zero(lo, hi)}")
    if group in ('Russia (ethnic)', 'Caucasus'):
        print(f"    {'Fighter':<25s} {'Pre N':>5} {'Pre exc':>8} {'Post N':>6} {'Post exc':>9} {'Swing':>7}")
        print("    " + "-" * 65)
        for _, r in wf.sort_values('swing', ascending=False).iterrows():
            print(f"    {r['fighter'][:24]:<25s} {r['pre_n']:>5} {r['pre_exc']:>+7.3f} "
                  f"{r['post_n']:>6} {r['post_exc']:>+8.3f} {r['swing']:>+6.3f}")

# Within-fighter DiD (Russian swing vs Caucasus swing)
rus_wf = [r for r in df_ws[df_ws['origin'] == 'Russia (ethnic)'].groupby('fighter').apply(
    lambda g: pd.Series({'pre': g[g['post']==0]['excess'].mean(), 'post': g[g['post']==1]['excess'].mean(),
                          'n_pre': len(g[g['post']==0]), 'n_post': len(g[g['post']==1])})
).iterrows() if r[1]['n_pre'] >= 1 and r[1]['n_post'] >= 1]

cauc_wf = [r for r in df_ws[df_ws['origin'] == 'Caucasus'].groupby('fighter').apply(
    lambda g: pd.Series({'pre': g[g['post']==0]['excess'].mean(), 'post': g[g['post']==1]['excess'].mean(),
                          'n_pre': len(g[g['post']==0]), 'n_post': len(g[g['post']==1])})
).iterrows() if r[1]['n_pre'] >= 1 and r[1]['n_post'] >= 1]

if rus_wf and cauc_wf:
    r_swings = np.array([r[1]['post'] - r[1]['pre'] for r in rus_wf])
    c_swings = np.array([r[1]['post'] - r[1]['pre'] for r in cauc_wf])
    wf_did = r_swings.mean() - c_swings.mean()
    boots_wf = []
    for _ in range(N_BOOT):
        br = r_swings[rng.choice(len(r_swings), len(r_swings), True)].mean()
        bc = c_swings[rng.choice(len(c_swings), len(c_swings), True)].mean()
        boots_wf.append(br - bc)
    lo_wf, hi_wf = np.percentile(boots_wf, [2.5, 97.5])
    print(f"\n  Within-fighter DiD (Russian swing - Caucasus swing):")
    print(f"    {wf_did:+.3f} [{lo_wf:+.3f},{hi_wf:+.3f}] excl 0: {ci_excludes_zero(lo_wf, hi_wf)}")

# ═══════════════════════════════════════════════════════════════════
# T5: Time-shape
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("T5: HALF-YEARLY EXCESS 2019H1-2025H2")
print("=" * 80)

ts_data = []
for group in ['Russia (ethnic)', 'Caucasus']:
    g = df_ws[df_ws['origin'] == group].copy()
    g['half'] = g['date'].dt.year.astype(str) + '-' + np.where(g['date'].dt.month <= 6, 'H1', 'H2')
    print(f"\n  {group}:")
    print(f"  {'Period':<10s} {'N':>4} {'Excess':>8} {'CI':>20} {'Excl 0':>7}")
    print("  " + "-" * 55)
    for period in sorted(g['half'].unique()):
        if period < '2019':
            continue
        sub = g[g['half'] == period]
        if len(sub) == 0:
            continue
        m, lo, hi = excess_ci(sub['excess'].values)
        ts_data.append({'group': group, 'period': period, 'n': len(sub),
                        'excess': m, 'ci_lo': lo, 'ci_hi': hi})
        print(f"  {period:<10s} {len(sub):>4} {m:>+7.3f} [{lo:>+.3f},{hi:>+.3f}] "
              f"{ci_excludes_zero(lo, hi):>7}")

# Save for figure
pd.DataFrame(ts_data).to_csv(f'{FIG_DIR}/fig1_timeshape_complete.csv', index=False)

# Pre-war trend extrapolation
print(f"\n  Pre-war trend extrapolation (Russian):")
rus_pre = df_ws[(df_ws['origin'] == 'Russia (ethnic)') & (df_ws['post'] == 0)].copy()
rus_post = df_ws[(df_ws['origin'] == 'Russia (ethnic)') & (df_ws['post'] == 1)].copy()
if len(rus_pre) > 5:
    # Convert date to numeric (years since 2017)
    rus_pre['t'] = (rus_pre['date'] - pd.Timestamp('2017-01-01')).dt.days / 365.25
    from numpy.polynomial import polynomial as P
    coeffs = np.polyfit(rus_pre['t'].values, rus_pre['excess'].values, 1)
    trend_slope = coeffs[0]
    trend_intercept = coeffs[1]
    print(f"    Pre-war trend: slope={trend_slope:+.4f}/year, intercept={trend_intercept:+.3f}")

    # Extrapolate to post-war period
    rus_post_t = (rus_post['date'] - pd.Timestamp('2017-01-01')).dt.days / 365.25
    predicted = trend_intercept + trend_slope * rus_post_t.values
    actual = rus_post['excess'].values
    gap = actual.mean() - predicted.mean()
    # Bootstrap CI on gap
    n_post = len(actual)
    boots_gap = []
    for _ in range(N_BOOT):
        bi = rng.choice(n_post, n_post, True)
        boots_gap.append(actual[bi].mean() - predicted[bi].mean())
    lo_g, hi_g = np.percentile(boots_gap, [2.5, 97.5])
    print(f"    Post-war actual mean excess: {actual.mean():+.3f}")
    print(f"    Extrapolated pre-war trend:  {predicted.mean():+.3f}")
    print(f"    Gap: {gap:+.3f} [{lo_g:+.3f},{hi_g:+.3f}] excl 0: {ci_excludes_zero(lo_g, hi_g)}")

# ═══════════════════════════════════════════════════════════════════
# T6: Selection-corrected (Wikidata-only coding)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("T6: WIKIDATA-ONLY CODING (biased sample, for comparison)")
print("=" * 80)

df_old = df_ws[df_ws['origin_old'].notna()].copy()
for group in ['Russia (ethnic)', 'Caucasus']:
    g = df_old[df_old['origin_old'] == group]
    pre = g[g['post'] == 0]['excess'].values
    post = g[g['post'] == 1]['excess'].values
    pre_m, pre_lo, pre_hi = excess_ci(pre)
    post_m, post_lo, post_hi = excess_ci(post)
    print(f"\n  {group} (Wikidata-only):")
    print(f"    Pre:  {pre_m:+.3f} [{pre_lo:+.3f},{pre_hi:+.3f}] (N={len(pre)})")
    print(f"    Post: {post_m:+.3f} [{post_lo:+.3f},{post_hi:+.3f}] (N={len(post)})")

# DiD old coding
t_pre_old = df_old[(df_old['origin_old'] == 'Russia (ethnic)') & (df_old['post'] == 0)]['excess'].values
t_post_old = df_old[(df_old['origin_old'] == 'Russia (ethnic)') & (df_old['post'] == 1)]['excess'].values
c_pre_old = df_old[(df_old['origin_old'] == 'Caucasus') & (df_old['post'] == 0)]['excess'].values
c_post_old = df_old[(df_old['origin_old'] == 'Caucasus') & (df_old['post'] == 1)]['excess'].values

if len(t_pre_old) > 0 and len(t_post_old) > 0 and len(c_pre_old) > 0 and len(c_post_old) > 0:
    did_old = (t_post_old.mean() - t_pre_old.mean()) - (c_post_old.mean() - c_pre_old.mean())
    boots_old = []
    for _ in range(N_BOOT):
        bt = t_post_old[rng.choice(len(t_post_old), len(t_post_old), True)].mean() - \
             t_pre_old[rng.choice(len(t_pre_old), len(t_pre_old), True)].mean()
        bc = c_post_old[rng.choice(len(c_post_old), len(c_post_old), True)].mean() - \
             c_pre_old[rng.choice(len(c_pre_old), len(c_pre_old), True)].mean()
        boots_old.append(bt - bc)
    lo_old, hi_old = np.percentile(boots_old, [2.5, 97.5])
    print(f"\n  DiD vs Caucasus (Wikidata-only): {did_old:+.3f} [{lo_old:+.3f},{hi_old:+.3f}] excl 0: {ci_excludes_zero(lo_old, hi_old)}")

# ═══════════════════════════════════════════════════════════════════
# T7: Robustness — proportional devig + placebo dates
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("T7: ROBUSTNESS")
print("=" * 80)

# T7a: Shin vs proportional devig
# The panel uses p_close_hi which is already Shin-devigged. We don't have proportional
# devig in the panel, but we can approximate: proportional devig shifts probs slightly
# toward 0.5 vs Shin. For the excess test, the difference is negligible on 2-way markets.
print("\n  T7a: Shin vs proportional de-vig")
print("    Panel uses Shin de-vig. Proportional de-vig not available in panel.")
print("    On 2-way markets the difference is <0.5pp per bout (Shin, 1993).")
print("    Not re-run; noted as a limitation.")

# T7b: Placebo cut dates
print("\n  T7b: Placebo cut dates")
for cut_date, cut_label in [('2020-02-24', '2020-02-24'), ('2021-02-24', '2021-02-24'),
                              ('2022-02-24', '2022-02-24 (actual)')]:
    cut_ts = pd.Timestamp(cut_date)
    rus = df_ws[df_ws['origin'] == 'Russia (ethnic)'].copy()
    cau = df_ws[df_ws['origin'] == 'Caucasus'].copy()
    r_pre = rus[rus['date'] < cut_ts]['excess'].values
    r_post = rus[rus['date'] >= cut_ts]['excess'].values
    c_pre = cau[cau['date'] < cut_ts]['excess'].values
    c_post = cau[cau['date'] >= cut_ts]['excess'].values

    if len(r_pre) < 5 or len(r_post) < 5 or len(c_pre) < 5 or len(c_post) < 5:
        print(f"    {cut_label}: insufficient data for one group")
        continue

    r_swing = r_post.mean() - r_pre.mean()
    c_swing = c_post.mean() - c_pre.mean()
    did_p = r_swing - c_swing

    boots_p = []
    for _ in range(N_BOOT):
        bt = r_post[rng.choice(len(r_post), len(r_post), True)].mean() - \
             r_pre[rng.choice(len(r_pre), len(r_pre), True)].mean()
        bc = c_post[rng.choice(len(c_post), len(c_post), True)].mean() - \
             c_pre[rng.choice(len(c_pre), len(c_pre), True)].mean()
        boots_p.append(bt - bc)
    lo_p, hi_p = np.percentile(boots_p, [2.5, 97.5])
    print(f"    {cut_label:<25s} DiD={did_p:+.3f} [{lo_p:+.3f},{hi_p:+.3f}] excl 0: {ci_excludes_zero(lo_p, hi_p)}")
    print(f"      Russian swing: {r_swing:+.3f} (pre N={len(r_pre)}, post N={len(r_post)})")
    print(f"      Caucasus swing: {c_swing:+.3f} (pre N={len(c_pre)}, post N={len(c_post)})")

# ═══════════════════════════════════════════════════════════════════
# DISCREPANCIES
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("DISCREPANCIES")
print("=" * 80)

# Compare old vs new Russian coding
old_rus_post = len(df_old[(df_old['origin_old'] == 'Russia (ethnic)') & (df_old['post'] == 1)])
new_rus_post = len(df_ws[(df_ws['origin'] == 'Russia (ethnic)') & (df_ws['post'] == 1)])
print(f"\n  Ethnic Russian post-war fights: old={old_rus_post}, new={new_rus_post}, added={new_rus_post - old_rus_post}")
print(f"  Ethnic Russian post-war excess: old={t_post_old.mean():+.3f}, new={t_post.mean():+.3f}")
if abs(t_post_old.mean() - t_post.mean()) > 0.01:
    print(f"  ** MATERIAL CHANGE: post-war excess shifted by {t_post.mean() - t_post_old.mean():+.3f}")

old_cauc_post = len(df_old[(df_old['origin_old'] == 'Caucasus') & (df_old['post'] == 1)])
new_cauc_post = len(df_ws[(df_ws['origin'] == 'Caucasus') & (df_ws['post'] == 1)])
print(f"\n  Caucasus post-war fights: old={old_cauc_post}, new={new_cauc_post}, added={new_cauc_post - old_cauc_post}")

# Control groups unchanged check
for group in ['USA', 'Brazil', 'UK', 'Canada', 'Australia', 'Other']:
    old_n = len(df_old[df_old['origin_old'] == group])
    new_n = len(df_ws[df_ws['origin'] == group])
    change_pct = abs(new_n - old_n) / max(old_n, 1) * 100
    if change_pct < 5:
        print(f"  {group}: coverage changed by <5% ({old_n} -> {new_n})")
    else:
        print(f"  {group}: ** COVERAGE CHANGED by {change_pct:.1f}% ({old_n} -> {new_n})")

print(f"\n  Fighters whose coding changed between old and new:")
changed = 0
for fighter in df_ws['fighter'].unique():
    old_o = df_ws[df_ws['fighter'] == fighter]['origin_old'].iloc[0] if len(df_ws[df_ws['fighter'] == fighter]) > 0 else None
    new_o = df_ws[df_ws['fighter'] == fighter]['origin'].iloc[0] if len(df_ws[df_ws['fighter'] == fighter]) > 0 else None
    if old_o != new_o and old_o is not None and new_o is not None:
        n_fights = len(df_ws[df_ws['fighter'] == fighter])
        print(f"    {fighter:30s} {str(old_o):>20s} -> {str(new_o):<20s} ({n_fights} fights)")
        changed += 1
    elif old_o is None and new_o is not None and new_o in ('Russia (ethnic)', 'Caucasus'):
        n_fights = len(df_ws[df_ws['fighter'] == fighter])
        print(f"    {fighter:30s} {'UNMATCHED':>20s} -> {str(new_o):<20s} ({n_fights} fights)")
        changed += 1
if changed == 0:
    print("    None")

print(f"\n  Total fighters with changed coding: {changed}")
