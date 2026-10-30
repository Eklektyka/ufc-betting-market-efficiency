#!/usr/bin/env python3
"""
War-shock natural experiment: ethnic Russian excess pre/post Feb 2022.
DiD with Caucasus/Central Asian/all-other placebos.
"""
import sys, math, re, warnings, functools, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict
from scipy.optimize import minimize
from scipy.special import expit

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# ═══════════════════════════════════════════════════════════════════
# LOAD (same pipeline as nation_mispricing.py)
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

fights_raw = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv')
events_raw = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_events.csv')
fight_to_event_url = dict(zip(fights_raw['fight_url'], fights_raw['event_url']))
event_url_to_loc = dict(zip(events_raw['event_url'], events_raw['location']))

fight_method = {}
for _, row in fights_raw.iterrows():
    if row['result'] == 'W':
        fight_method[row['fight_url']] = row['method']

# Fighter style from ufcstats
fighter_fight_stats = defaultdict(list)
for _, row in fights_raw.sort_values('date').iterrows():
    try:
        td_l = int(row['td_landed']) if pd.notna(row['td_landed']) else 0
        td_a = int(row['td_att']) if pd.notna(row['td_att']) else 0
        ctrl = int(row['ctrl_sec']) if pd.notna(row['ctrl_sec']) else 0
    except (ValueError, TypeError):
        td_l = td_a = ctrl = 0
    fighter_fight_stats[row['fighter_name']].append({
        'fight_url': row['fight_url'], 'td_landed': td_l, 'td_att': td_a, 'ctrl_sec': ctrl,
    })

def get_wrestling_score(fighter_name, fight_url):
    stats = fighter_fight_stats.get(fighter_name, [])
    cum_td, cum_ctrl, n = 0, 0, 0
    for s in stats:
        if s['fight_url'] == fight_url:
            break
        cum_td += s['td_landed']; cum_ctrl += s['ctrl_sec']; n += 1
    if n == 0:
        return 0
    return cum_td / n + cum_ctrl / n / 60

# Region assignment
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
    if country == 'Brazil':
        return 'Brazil'
    return 'Other'

# ═══════════════════════════════════════════════════════════════════
# BUILD FIGHT-LEVEL DATASET
# ═══════════════════════════════════════════════════════════════════
print("Building fight dataset...")

fight_counter = defaultdict(int)
rows = []
for _, r in panel.sort_values('date').iterrows():
    fighter = r['fighter']
    region = assign_region(fighter)
    if region is None:
        continue
    fight_counter[fighter] += 1

    event_url = fight_to_event_url.get(r['fight_url'])
    loc_str = event_url_to_loc.get(event_url, '') if event_url else ''

    rows.append({
        'fight_id': r['fight_id'], 'fight_url': r['fight_url'],
        'date': r['date'], 'year': r['year'],
        'fighter': fighter, 'opponent': r['opponent'],
        'region': region,
        'p_mkt': r['p_close_hi'], 'win': int(r['win']),
        'career_n': fight_counter[fighter],
        'layoff': r['layoff_days'],
        'wrestling': get_wrestling_score(fighter, r['fight_url']),
        'post': 1 if r['date'] >= pd.Timestamp('2022-02-24') else 0,
        'event_loc': loc_str,
    })

df = pd.DataFrame(rows)
df = df[(df['year'] >= 2017) & (df['year'] <= 2025)].copy()  # focus window
df['excess'] = df['win'] - df['p_mkt']

print(f"  Rows (2017-2025): {len(df)}")

# ═══════════════════════════════════════════════════════════════════
# ETHNIC RUSSIAN ROSTER
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("ETHNIC RUSSIAN FIGHTERS IN DATASET")
print(f"{'='*72}")

eth_rus = df[df['region'] == 'Russia (ethnic)']
for fighter, grp in eth_rus.groupby('fighter'):
    pre = grp[grp['post'] == 0]; post = grp[grp['post'] == 1]
    print(f"  {fighter:30s} pre={len(pre):>2}, post={len(post):>2}, "
          f"total={len(grp):>2}, WR={grp['win'].mean():.0%}, mkt={grp['p_mkt'].mean():.0%}")

# ═══════════════════════════════════════════════════════════════════
# DiD: TREATMENT = ETHNIC RUSSIAN, CONTROLS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("DiD: ETHNIC RUSSIAN EXCESS PRE/POST FEB 2022")
print(f"{'='*72}")

def compute_did(treatment_df, control_df, label):
    """Compute DiD: (treatment_post - treatment_pre) - (control_post - control_pre)"""
    t_pre = treatment_df[treatment_df['post'] == 0]['excess']
    t_post = treatment_df[treatment_df['post'] == 1]['excess']
    c_pre = control_df[control_df['post'] == 0]['excess']
    c_post = control_df[control_df['post'] == 1]['excess']

    if len(t_pre) < 5 or len(t_post) < 5 or len(c_pre) < 5 or len(c_post) < 5:
        print(f"\n  {label}: insufficient data")
        print(f"    Treatment: pre={len(t_pre)}, post={len(t_post)}")
        print(f"    Control:   pre={len(c_pre)}, post={len(c_post)}")
        return None

    t_diff = t_post.mean() - t_pre.mean()
    c_diff = c_post.mean() - c_pre.mean()
    did = t_diff - c_diff

    # Bootstrap CI
    boots = []
    for _ in range(N_BOOT):
        bt_pre = t_pre.values[rng.choice(len(t_pre), len(t_pre), replace=True)].mean()
        bt_post = t_post.values[rng.choice(len(t_post), len(t_post), replace=True)].mean()
        bc_pre = c_pre.values[rng.choice(len(c_pre), len(c_pre), replace=True)].mean()
        bc_post = c_post.values[rng.choice(len(c_post), len(c_post), replace=True)].mean()
        boots.append((bt_post - bt_pre) - (bc_post - bc_pre))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'

    print(f"\n  {label}:")
    print(f"    Treatment (ethnic Russian):")
    print(f"      Pre:  N={len(t_pre):>3}, excess={t_pre.mean():+.3f}")
    print(f"      Post: N={len(t_post):>3}, excess={t_post.mean():+.3f}")
    print(f"      Diff: {t_diff:+.3f}")
    print(f"    Control ({label}):")
    print(f"      Pre:  N={len(c_pre):>3}, excess={c_pre.mean():+.3f}")
    print(f"      Post: N={len(c_post):>3}, excess={c_post.mean():+.3f}")
    print(f"      Diff: {c_diff:+.3f}")
    print(f"    DiD:    {did:+.3f} [{lo:+.3f}, {hi:+.3f}]  sig={sig}")
    return did

treatment = df[df['region'] == 'Russia (ethnic)']

# Control 1: Caucasus (key placebo)
control_caucasus = df[df['region'] == 'Caucasus']
did_cauc = compute_did(treatment, control_caucasus, "vs Caucasus (key placebo)")

# Control 2: Central Asia
control_ca = df[df['region'] == 'Central Asia']
did_ca = compute_did(treatment, control_ca, "vs Central Asia")

# Control 3: All non-Russian
control_all = df[~df['region'].isin(['Russia (ethnic)', 'Caucasus', 'Central Asia'])]
did_all = compute_did(treatment, control_all, "vs all non-Russian/Caucasus/CA")

# Control 4: USA only (largest, cleanest)
control_usa = df[df['region'] == 'USA']
did_usa = compute_did(treatment, control_usa, "vs USA only")

# Control 5: Brazil
control_brazil = df[df['region'] == 'Brazil']
did_brazil = compute_did(treatment, control_brazil, "vs Brazil")


# ═══════════════════════════════════════════════════════════════════
# TIME-SHAPE: ROLLING EXCESS 2019-2025
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TIME-SHAPE: HALF-YEAR ETHNIC RUSSIAN EXCESS 2019-2025")
print(f"{'='*72}")

# Create half-year periods
eth_all = df[df['region'] == 'Russia (ethnic)'].copy()
eth_all['half'] = eth_all['date'].dt.year.astype(str) + '-' + np.where(eth_all['date'].dt.month <= 6, 'H1', 'H2')

print(f"\n  {'Period':<10s} {'N':>4} {'WR':>5} {'Mkt':>5} {'Excess':>7} {'Fighters'}")
print("  " + "-" * 60)

for period in sorted(eth_all['half'].unique()):
    sub = eth_all[eth_all['half'] == period]
    if len(sub) == 0:
        continue
    fighters = ', '.join(sorted(sub['fighter'].unique()))
    wr = sub['win'].mean()
    mkt = sub['p_mkt'].mean()
    exc = wr - mkt
    marker = ' <<<' if '2022-H1' in period else ''
    print(f"  {period:<10s} {len(sub):>4} {wr:>4.0%} {mkt:>4.0%} {exc:>+6.3f} {fighters[:50]}{marker}")

# Quarterly for finer resolution around the shock
print(f"\n  Quarterly view (2021-2023):")
eth_narrow = eth_all[(eth_all['year'] >= 2021) & (eth_all['year'] <= 2023)].copy()
eth_narrow['quarter'] = eth_narrow['date'].dt.to_period('Q').astype(str)
for q in sorted(eth_narrow['quarter'].unique()):
    sub = eth_narrow[eth_narrow['quarter'] == q]
    if len(sub) == 0:
        continue
    exc = sub['win'].mean() - sub['p_mkt'].mean()
    fighters = ', '.join(sorted(sub['fighter'].unique()))
    print(f"    {q}: N={len(sub):>2}, excess={exc:+.3f}  [{fighters[:60]}]")


# ═══════════════════════════════════════════════════════════════════
# LEAVE-OUT-THE-ELITE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("LEAVE-OUT-THE-ELITE: DROP TOP FIGHTERS BY FIGHT COUNT")
print(f"{'='*72}")

# Identify top fighters
fighter_counts = eth_rus.groupby('fighter').size().sort_values(ascending=False)
print(f"\n  Fighter fight counts (ethnic Russian, 2017-2025):")
for f, n in fighter_counts.items():
    post_n = eth_rus[(eth_rus['fighter'] == f) & (eth_rus['post'] == 1)]
    post_exc = post_n['excess'].mean() if len(post_n) > 0 else float('nan')
    print(f"    {f:30s} {n:>3} fights, post-war: {len(post_n):>2}, post excess: {post_exc:+.3f}" if len(post_n)>0 else f"    {f:30s} {n:>3} fights, post-war:  0")

# Drop top 3 by count
top3 = list(fighter_counts.head(3).index)
print(f"\n  Dropping: {top3}")

eth_no_elite = eth_rus[~eth_rus['fighter'].isin(top3)]
print(f"  Remaining: {len(eth_no_elite)} rows, {eth_no_elite['fighter'].nunique()} fighters")

pre_ne = eth_no_elite[eth_no_elite['post'] == 0]
post_ne = eth_no_elite[eth_no_elite['post'] == 1]
if len(pre_ne) >= 3 and len(post_ne) >= 3:
    exc_pre = pre_ne['excess'].mean()
    exc_post = post_ne['excess'].mean()
    diff = exc_post - exc_pre
    # Bootstrap
    boots = []
    for _ in range(N_BOOT):
        b_pre = pre_ne['excess'].values[rng.choice(len(pre_ne), len(pre_ne), replace=True)].mean()
        b_post = post_ne['excess'].values[rng.choice(len(post_ne), len(post_ne), replace=True)].mean()
        boots.append(b_post - b_pre)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"\n  Without top 3:")
    print(f"    Pre:  N={len(pre_ne)}, excess={exc_pre:+.3f}")
    print(f"    Post: N={len(post_ne)}, excess={exc_post:+.3f}")
    print(f"    Diff: {diff:+.3f} [{lo:+.3f}, {hi:+.3f}] sig={sig}")
else:
    print(f"  Insufficient rows after dropping elite (pre={len(pre_ne)}, post={len(post_ne)})")

# Also try dropping just the single biggest contributor
top1 = [fighter_counts.index[0]]
eth_no_top1 = eth_rus[~eth_rus['fighter'].isin(top1)]
pre_n1 = eth_no_top1[eth_no_top1['post'] == 0]
post_n1 = eth_no_top1[eth_no_top1['post'] == 1]
if len(pre_n1) >= 3 and len(post_n1) >= 3:
    exc_pre1 = pre_n1['excess'].mean()
    exc_post1 = post_n1['excess'].mean()
    diff1 = exc_post1 - exc_pre1
    boots1 = []
    for _ in range(N_BOOT):
        b_pre = pre_n1['excess'].values[rng.choice(len(pre_n1), len(pre_n1), replace=True)].mean()
        b_post = post_n1['excess'].values[rng.choice(len(post_n1), len(post_n1), replace=True)].mean()
        boots1.append(b_post - b_pre)
    lo1, hi1 = np.percentile(boots1, [2.5, 97.5])
    sig1 = 'YES' if (lo1 > 0 or hi1 < 0) else 'no'
    print(f"\n  Without {top1[0]} only:")
    print(f"    Pre:  N={len(pre_n1)}, excess={exc_pre1:+.3f}")
    print(f"    Post: N={len(post_n1)}, excess={exc_post1:+.3f}")
    print(f"    Diff: {diff1:+.3f} [{lo1:+.3f}, {hi1:+.3f}] sig={sig1}")


# ═══════════════════════════════════════════════════════════════════
# COMPOSITION CHECK: PRE vs POST SAMPLE QUALITY
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("COMPOSITION: PRE vs POST ETHNIC RUSSIAN SAMPLE")
print(f"{'='*72}")

pre_all = eth_rus[eth_rus['post'] == 0]
post_all = eth_rus[eth_rus['post'] == 1]

print(f"\n  {'Metric':<25s} {'Pre (N={})'.format(len(pre_all)):>15} {'Post (N={})'.format(len(post_all)):>15}")
print("  " + "-" * 55)
for metric, col in [('Market implied prob', 'p_mkt'),
                     ('Layoff (days)', 'layoff'),
                     ('Wrestling score', 'wrestling'),
                     ('Career fight #', 'career_n')]:
    pre_v = pre_all[col].mean()
    post_v = post_all[col].mean()
    print(f"  {metric:<25s} {pre_v:>15.1f} {post_v:>15.1f}")

print(f"\n  Unique fighters pre: {pre_all['fighter'].nunique()}")
print(f"  Unique fighters post: {post_all['fighter'].nunique()}")
overlap = set(pre_all['fighter'].unique()) & set(post_all['fighter'].unique())
print(f"  Overlap (appear in both): {len(overlap)}")
pre_only = set(pre_all['fighter'].unique()) - set(post_all['fighter'].unique())
post_only = set(post_all['fighter'].unique()) - set(pre_all['fighter'].unique())
print(f"  Pre-only fighters: {pre_only}")
print(f"  Post-only fighters: {post_only}")

# DiD with controls for composition
print(f"\n  DiD WITH COMPOSITION CONTROLS (logistic):")
print(f"  win ~ mkt_prob + is_ethnic_russian + post + is_ethnic_russian*post + layoff + wrestling")

# Build regression dataset: ethnic Russians + USA as control
reg = df[df['region'].isin(['Russia (ethnic)', 'USA'])].copy()
reg['is_rus'] = (reg['region'] == 'Russia (ethnic)').astype(float)
reg['interaction'] = reg['is_rus'] * reg['post']
reg['log_layoff'] = np.log1p(reg['layoff'])

def neg_ll(params, X, y):
    z = params[0]
    for i in range(len(X)):
        z = z + params[i+1] * X[i]
    p = np.clip(expit(z), 1e-10, 1-1e-10)
    return -np.sum(y * np.log(p) + (1-y) * np.log(1-p))

y = reg['win'].values
features_basic = [reg['p_mkt'].values, reg['is_rus'].values, reg['post'].values, reg['interaction'].values]
features_full = features_basic + [reg['log_layoff'].values, reg['wrestling'].values]
labels_basic = ['mkt_prob', 'is_rus', 'post', 'rus*post']
labels_full = labels_basic + ['log_layoff', 'wrestling']

# Without controls
res_b = minimize(neg_ll, [0]*(1+len(features_basic)), args=(features_basic, y),
                 method='Nelder-Mead', options={'maxiter': 10000})
# With controls
res_f = minimize(neg_ll, [0]*(1+len(features_full)), args=(features_full, y),
                 method='Nelder-Mead', options={'maxiter': 10000})

print(f"\n    Basic DiD (no controls):")
for i, l in enumerate(labels_basic):
    print(f"      {l:<15s} {res_b.x[i+1]:+.4f}")

print(f"\n    Full DiD (with layoff + wrestling):")
for i, l in enumerate(labels_full):
    print(f"      {l:<15s} {res_f.x[i+1]:+.4f}")

# Bootstrap the interaction coefficient
print(f"\n    Bootstrapping rus*post interaction (N={N_BOOT})...")
int_boots_b = []
int_boots_f = []
n_reg = len(y)
for _ in range(N_BOOT):
    bi = rng.choice(n_reg, n_reg, replace=True)
    yb = y[bi]
    fb = [x[bi] for x in features_basic]
    ff = [x[bi] for x in features_full]
    try:
        rb = minimize(neg_ll, list(res_b.x), args=(fb, yb), method='Nelder-Mead',
                      options={'maxiter': 3000, 'xatol': 1e-3, 'fatol': 1e-3})
        int_boots_b.append(rb.x[4])  # interaction = index 4
    except:
        pass
    try:
        rf = minimize(neg_ll, list(res_f.x), args=(ff, yb), method='Nelder-Mead',
                      options={'maxiter': 3000, 'xatol': 1e-3, 'fatol': 1e-3})
        int_boots_f.append(rf.x[4])
    except:
        pass

for label, boots, point in [('Basic DiD', int_boots_b, res_b.x[4]),
                              ('Full DiD', int_boots_f, res_f.x[4])]:
    boots = np.array(boots)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"    {label}: rus*post = {point:+.4f} [{lo:+.4f}, {hi:+.4f}] sig={sig}")


# ═══════════════════════════════════════════════════════════════════
# FIGHT-LEVEL DETAIL: POST-WAR ETHNIC RUSSIAN FIGHTS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("FIGHT DETAIL: POST-WAR ETHNIC RUSSIAN FIGHTS")
print(f"{'='*72}")

post_fights = eth_rus[eth_rus['post'] == 1].sort_values('date')
print(f"\n  {'Date':<12s} {'Fighter':<25s} {'Opponent':<25s} {'Mkt%':>5s} {'Won':>4s} {'Excess':>7s}")
print("  " + "-" * 85)
for _, row in post_fights.iterrows():
    won = 'YES' if row['win'] == 1 else 'no'
    exc = row['win'] - row['p_mkt']
    print(f"  {str(row['date'].date()):<12s} {row['fighter'][:24]:<25s} {row['opponent'][:24]:<25s} "
          f"{row['p_mkt']:>4.0%} {won:>4s} {exc:>+6.3f}")

n_wins = post_fights['win'].sum()
n_total = len(post_fights)
upsets = post_fights[post_fights['win'] > post_fights['p_mkt'].round()]  # won as underdog
print(f"\n  Post-war record: {n_wins}/{n_total} ({n_wins/n_total:.0%})")
print(f"  Upsets (won as underdog, mkt<50%): {len(post_fights[(post_fights['win']==1)&(post_fights['p_mkt']<0.5)])}")
print(f"  Mean market prob: {post_fights['p_mkt'].mean():.0%}")


# ═══════════════════════════════════════════════════════════════════
# CAUCASUS PLACEBO CHECK (same format)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("CAUCASUS PLACEBO: SAME TIME SPLIT")
print(f"{'='*72}")

cauc = df[df['region'] == 'Caucasus']
cauc_pre = cauc[cauc['post'] == 0]
cauc_post = cauc[cauc['post'] == 1]
print(f"  Pre:  N={len(cauc_pre)}, excess={cauc_pre['excess'].mean():+.3f}")
print(f"  Post: N={len(cauc_post)}, excess={cauc_post['excess'].mean():+.3f}")
print(f"  Diff: {cauc_post['excess'].mean() - cauc_pre['excess'].mean():+.3f}")
print(f"  (Ethnic Russian diff was: {post_all['excess'].mean() - pre_all['excess'].mean():+.3f})")


# ═══════════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("VERDICT")
print(f"{'='*72}")

eth_pre_exc = pre_all['excess'].mean()
eth_post_exc = post_all['excess'].mean()
eth_diff = eth_post_exc - eth_pre_exc
cauc_diff_val = cauc_post['excess'].mean() - cauc_pre['excess'].mean()

print(f"""
  ETHNIC RUSSIAN POST-WAR DISCONTINUITY:
    Pre-war excess:  {eth_pre_exc:+.3f} (N={len(pre_all)})
    Post-war excess: {eth_post_exc:+.3f} (N={len(post_all)})
    Swing:           {eth_diff:+.3f}

  CAUCASUS PLACEBO:
    Pre-war excess:  {cauc_pre['excess'].mean():+.3f} (N={len(cauc_pre)})
    Post-war excess: {cauc_post['excess'].mean():+.3f} (N={len(cauc_post)})
    Swing:           {cauc_diff_val:+.3f}

  DiD (ethnic Russian vs Caucasus): {eth_diff - cauc_diff_val:+.3f}

  CHECKLIST:
    1. Russian-specific discontinuity? {eth_diff:+.3f}
    2. Absent in Caucasus placebo?     Caucasus swing = {cauc_diff_val:+.3f}
    3. Survives elite dropout?         See above
    4. Survives composition controls?  See logistic DiD
    5. 2024-25 level?                  See time-shape

  The N={len(post_all)} post-war sample is the binding constraint.
  A +18pp excess needs N~100+ to reach 80% power.
  Report as: suggestive / confirmed / collapsed.
""")
