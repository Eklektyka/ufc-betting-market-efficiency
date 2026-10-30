#!/usr/bin/env python3
"""Expanded ethnic Russian mispricing check with roster.watch additions."""
import sys, re, unicodedata, warnings, functools
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

panel = pd.read_csv(r'C:\Research\mma-paper\data\analysis_panel_cc.csv')
panel['date'] = pd.to_datetime(panel['date'])
panel = panel[(panel['year'] >= 2017) & (panel['year'] <= 2025)].copy()
panel['excess'] = panel['win'] - panel['p_close_hi']

# Original N=35 ethnic Russians
original = ['Alexander Volkov', 'Valentina Shevchenko', 'Petr Yan', 'Roman Kopylov',
            'Azamat Murzakanov', 'Sergei Pavlovich', 'Bogdan Guskov', 'Damir Ismagulov',
            'Rinat Fakhretdinov', 'Antonina Shevchenko']

# Roster.watch additions - former (ethnic Russian)
new_former = ['Viacheslav Borshchev', 'Denis Tiuliulin', 'Aleksei Oleinik', 'Viktoriia Dudakova']

# Roster.watch additions - active (per user instruction)
new_active = ['Baisangur Susurkaev', 'Yana Santos', 'Daria Zhelezniakova',
              'Andrey Pulyaev', 'Valter Walker']

all_new = new_former + new_active
all_ethnic = original + all_new

def get_fights(fighters, post=None):
    mask = panel['fighter'].isin(fighters)
    if post is True:
        mask = mask & (panel['date'] >= '2022-02-24')
    elif post is False:
        mask = mask & (panel['date'] < '2022-02-24')
    return panel[mask].copy()

orig_pre = get_fights(original, False)
orig_post = get_fights(original, True)
new_pre = get_fights(all_new, False)
new_post = get_fights(all_new, True)
full_pre = get_fights(all_ethnic, False)
full_post = get_fights(all_ethnic, True)

print("ETHNIC RUSSIAN MISPRICING -- ORIGINAL vs EXPANDED")
print("=" * 80)

print(f"\n  {'Sample':<30s} {'Pre-war':>20s} {'Post-war':>20s} {'Swing':>10s}")
print("  " + "-" * 80)
for label, pre, post in [('Original (N=35 post)', orig_pre, orig_post),
                           ('Newly added', new_pre, new_post),
                           ('EXPANDED TOTAL', full_pre, full_post)]:
    pre_exc = pre['excess'].mean() if len(pre) > 0 else float('nan')
    post_exc = post['excess'].mean() if len(post) > 0 else float('nan')
    swing = post_exc - pre_exc if len(pre) > 0 and len(post) > 0 else float('nan')
    pre_str = f"{pre_exc:+.3f} (N={len(pre):>3})" if len(pre) > 0 else "n/a"
    post_str = f"{post_exc:+.3f} (N={len(post):>3})" if len(post) > 0 else "n/a"
    swing_str = f"{swing:+.3f}" if not np.isnan(swing) else "n/a"
    print(f"  {label:<30s} {pre_str:>20s} {post_str:>20s} {swing_str:>10s}")

# Fight-level detail for new additions (post-war only)
print(f"\n\nNEWLY ADDED -- POST-WAR FIGHTS")
print("=" * 80)
print(f"  {'Date':<12s} {'Fighter':<25s} {'Opponent':<22s} {'Mkt%':>5s} {'Won':>4s} {'Excess':>7s}")
print("  " + "-" * 78)
for _, r in new_post.sort_values('date').iterrows():
    won = 'YES' if r['win'] == 1 else 'no'
    print(f"  {str(r['date'])[:10]:<12s} {r['fighter'][:24]:<25s} {r['opponent'][:21]:<22s} "
          f"{r['p_close_hi']:>4.0%} {won:>4s} {r['excess']:>+6.3f}")

# Bootstrap CI comparison
print(f"\n\nBOOTSTRAP COMPARISON")
print("=" * 80)
for label, post_df in [('Original (N=35)', orig_post), ('Expanded', full_post)]:
    vals = post_df['excess'].values
    n = len(vals)
    mean = vals.mean()
    boots = [vals[rng.choice(n, n, True)].mean() for _ in range(N_BOOT)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"  {label:<25s} excess={mean:>+.3f} [{lo:>+.3f},{hi:>+.3f}] sig={sig} (N={n})")

# Caucasus placebo (unchanged)
wiki = pd.read_csv(r'C:\Research\mma-paper\data\wikidata_mma_fighters.csv')
wiki_lookup = {}
for _, row in wiki.iterrows():
    nn = norm_name(row['name'])
    if nn not in wiki_lookup or (str(row.get('lat','')).strip() not in ('', 'nan')):
        wiki_lookup[nn] = row.to_dict()

ufc_fighters = set(panel['fighter'].unique())
caucasus_fighters = set()
for f in ufc_fighters:
    nn = norm_name(f)
    d = wiki_lookup.get(nn)
    if d is None:
        parts = nn.split()
        if len(parts) >= 2:
            d = wiki_lookup.get(' '.join(parts[1:] + parts[:1]))
    if d and d.get('country') == 'Russia':
        try:
            lat, lon = float(d.get('lat', 0)), float(d.get('lon', 0))
            if 41 < lat < 45 and 43 < lon < 49:
                caucasus_fighters.add(f)
                continue
        except:
            pass
        bp = str(d.get('birthplace', '')).lower()
        cauc = ['dagestan','chechnya','chechen','grozny','makhachkala','ingush',
                'kabardino','ossetia','nalchik','khasavyurt','buynaksk','derbent',
                'kizlyar','kaspiysk','kizilyurt','sildi','sunzha','teletl',
                'vladikavkaz','babugent','goksuv','batayurt','gvardeyskoe']
        if any(m in bp for m in cauc):
            caucasus_fighters.add(f)

cauc_pre = panel[(panel['fighter'].isin(caucasus_fighters)) & (panel['date'] < '2022-02-24')]
cauc_post = panel[(panel['fighter'].isin(caucasus_fighters)) & (panel['date'] >= '2022-02-24')]

# DiD
print(f"\n\nDiD vs CAUCASUS")
print("=" * 80)

t_diff = full_post['excess'].mean() - full_pre['excess'].mean()
c_diff = cauc_post['excess'].mean() - cauc_pre['excess'].mean()
did = t_diff - c_diff

boots_did = []
for _ in range(N_BOOT):
    bt = full_post['excess'].values[rng.choice(len(full_post), len(full_post), True)].mean() - \
         full_pre['excess'].values[rng.choice(len(full_pre), len(full_pre), True)].mean()
    bc = cauc_post['excess'].values[rng.choice(len(cauc_post), len(cauc_post), True)].mean() - \
         cauc_pre['excess'].values[rng.choice(len(cauc_pre), len(cauc_pre), True)].mean()
    boots_did.append(bt - bc)
lo_d, hi_d = np.percentile(boots_did, [2.5, 97.5])
sig_d = 'YES' if (lo_d > 0 or hi_d < 0) else 'no'

orig_t_diff = orig_post['excess'].mean() - orig_pre['excess'].mean()
orig_did = orig_t_diff - c_diff

print(f"  Ethnic Russian (expanded):")
print(f"    Pre:  {full_pre['excess'].mean():>+.3f} (N={len(full_pre)})")
print(f"    Post: {full_post['excess'].mean():>+.3f} (N={len(full_post)})")
print(f"    Diff: {t_diff:>+.3f}")
print(f"  Caucasus:")
print(f"    Pre:  {cauc_pre['excess'].mean():>+.3f} (N={len(cauc_pre)})")
print(f"    Post: {cauc_post['excess'].mean():>+.3f} (N={len(cauc_post)})")
print(f"    Diff: {c_diff:>+.3f}")
print(f"  DiD: {did:>+.3f} [{lo_d:>+.3f},{hi_d:>+.3f}] sig={sig_d}")
print(f"\n  Original DiD (N=35 post): {orig_did:+.3f}")
print(f"  Expanded DiD (N={len(full_post)} post): {did:+.3f}")
print(f"  Change: {did - orig_did:+.3f}")

# Per-fighter summary
print(f"\n\nPER-FIGHTER POST-WAR SUMMARY (expanded)")
print("=" * 80)
print(f"  {'Fighter':<25s} {'N':>3} {'WR':>5} {'Mkt':>5} {'Excess':>7} {'Source'}")
print("  " + "-" * 60)
for fighter in sorted(all_ethnic):
    post = panel[(panel['fighter'] == fighter) & (panel['date'] >= '2022-02-24')]
    if len(post) == 0:
        continue
    source = 'original' if fighter in original else 'NEW (rw)'
    print(f"  {fighter[:24]:<25s} {len(post):>3} {post['win'].mean():>4.0%} "
          f"{post['p_close_hi'].mean():>4.0%} {post['excess'].mean():>+6.3f} {source}")
