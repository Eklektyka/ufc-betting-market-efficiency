#!/usr/bin/env python3
"""Debutant excess CIs and DiD: Russian vs USA post-2022 entrants."""
import sys, re, warnings, functools, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

DATA_DIR = '../data'

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# ── Origin coding (same as 04_complete_coverage.py) ──
ROSTER_WATCH_RUSSIA = {
    'Alexander Volkov': 'E', 'Alexander Yakovlev': 'E', 'Aleksei Oleinik': 'E',
    'Maxim Grishin': 'E', 'Gadzhimurad Antigulov': 'E', 'Aleksandra Albu': 'E',
    'Milana Dudieva': 'E', 'Dmitry Smolyakov': 'E', 'Igor Zinoviev': 'E',
    'Oleg Taktarov': 'E', 'Andrey Semenov': 'E', 'Viacheslav Borshchev': 'E',
    'Denis Tiuliulin': 'E', 'Konstantin Erokhin': 'E', 'Viktoriia Dudakova': 'E',
    'Roman Bogatov': 'E', 'Alexey Kunchenko': 'E', 'Rinat Fakhretdinov': 'E',
    'Petr Yan': 'E', 'Sergei Pavlovich': 'E', 'Valentina Shevchenko': 'E',
    'Antonina Shevchenko': 'E', 'Roman Kopylov': 'E', 'Azamat Murzakanov': 'E',
    'Bogdan Guskov': 'E', 'Damir Ismagulov': 'E', 'Nikita Krylov': 'E',
    'Yana Santos': 'E', 'Daria Zhelezniakova': 'E', 'Valter Walker': 'E',
    'Andrey Pulyaev': 'E', 'Mark Vologdin': 'E', 'Irina Alekseeva': 'E',
    'Dennis Siver': 'E',
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
    'Khalid Murtazaliev': 'C', 'Sergey Khandozhko': 'C', 'Askar Askarov': 'C',
    'Khusein Askhabov': 'C', 'Gadzhi Omargadzhiev': 'C', 'Magomed Gadzhiyasulov': 'C',
    'Islam Makhachev': 'C', 'Khamzat Chimaev': 'C', 'Magomed Ankalaev': 'C',
    'Movsar Evloev': 'C', 'Umar Nurmagomedov': 'C', 'Ikram Aliskerov': 'C',
    'Rizvan Kuniev': 'C', 'Shara Magomedov': 'C', 'Tagir Ulanbekov': 'C',
    'Muslim Salikhov': 'C', 'Said Nurmagomedov': 'C', 'Azamat Bekoev': 'C',
    'Baisangur Susurkaev': 'C', 'Aliaskhab Khizriev': 'C',
    'Abdul Rakhman Yakhyaev': 'C', 'Shamil Gaziev': 'C',
    'Abubakar Vagaev': 'C', 'Saygid Izagakhmaev': 'C',
    'Muhammad Said': 'C', 'Magomed Zaynukov': 'C', 'Magomed Tuchalov': 'C',
    'Islam Dulatov': 'C', 'Abus Magomedov': 'C',
    'Artem Lobov': 'X', 'Muhammad Mokaev': 'X', 'Nassourdine Imavov': 'X',
    'Ismail Naurdiev': 'X',
}

rw_lookup = {}
for name, code in ROSTER_WATCH_RUSSIA.items():
    rw_lookup[norm_name(name)] = (name, code)

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

def assign_origin(fighter_name):
    nn = norm_name(fighter_name)
    rw = rw_lookup.get(nn)
    if rw is None:
        parts = nn.split()
        if len(parts) >= 2:
            for rw_nn, (rw_name, rw_code) in rw_lookup.items():
                rw_parts = rw_nn.split()
                if len(rw_parts) >= 2 and parts[-1] == rw_parts[-1] and parts[0][0] == rw_parts[0][0]:
                    rw = (rw_name, rw_code)
                    break
    if rw:
        _, code = rw
        if code == 'E': return 'Russia (ethnic)'
        elif code == 'C': return 'Caucasus'
    d = wiki_matched.get(fighter_name, {})
    country = d.get('country', '')
    if not country: return None
    if country == 'Russia':
        try:
            lat, lon = float(d.get('lat', 0)), float(d.get('lon', 0))
            if 41 < lat < 45 and 43 < lon < 49: return 'Caucasus'
        except: pass
        bp = str(d.get('birthplace', '')).lower()
        cauc = ['dagestan','chechnya','chechen','grozny','makhachkala','ingush',
                'kabardino','ossetia','nalchik','khasavyurt','buynaksk','derbent',
                'kizlyar','kaspiysk','kizilyurt','sildi','sunzha','teletl',
                'vladikavkaz','babugent','goksuv','batayurt','gvardeyskoe']
        if any(m in bp for m in cauc): return 'Caucasus'
        return 'Russia (ethnic)'
    if country == 'United States': return 'USA'
    if country == 'Brazil': return 'Brazil'
    return 'Other'

# Build fight-level
fight_counter = defaultdict(int)
rows = []
for _, r in panel.sort_values('date').iterrows():
    fighter = r['fighter']
    origin = assign_origin(fighter)
    if origin is None: continue
    fight_counter[fighter] += 1
    rows.append({
        'fighter': fighter, 'origin': origin,
        'p_mkt': r['p_close_hi'], 'win': int(r['win']),
        'career_n': fight_counter[fighter],
        'post': 1 if r['date'] >= pd.Timestamp('2022-02-24') else 0,
        'date': r['date'], 'year': r['year'],
    })
df = pd.DataFrame(rows)
df['excess'] = df['win'] - df['p_mkt']

# ═══════════════════════════════════════════════════════════════════
# DEBUTANT EXCESS WITH CIs
# ═══════════════════════════════════════════════════════════════════
print("POST-2022 DEBUTANT EXCESS WITH CIs")
print("=" * 80)

debuts = df[df['career_n'] == 1]
post_debuts = debuts[debuts['post'] == 1]

print(f"\n  {'Group':<20s} {'N deb':>6} {'N fights':>8} {'Mean mkt':>9} {'Frac dog':>9} "
      f"{'WR':>5} {'Excess':>8} {'CI':>22} {'Excl 0':>7}")
print("  " + "-" * 95)

group_deb_excess = {}
for group in ['Russia (ethnic)', 'Caucasus', 'USA', 'Brazil', 'Other']:
    debs = post_debuts[post_debuts['origin'] == group]
    if len(debs) == 0:
        continue
    deb_fighters = debs['fighter'].tolist()
    all_fights = df[(df['fighter'].isin(deb_fighters)) & (df['origin'] == group)]
    if len(all_fights) == 0:
        continue

    exc_vals = all_fights['excess'].values
    n = len(exc_vals)
    mean_exc = exc_vals.mean()
    boots = [exc_vals[rng.choice(n, n, True)].mean() for _ in range(N_BOOT)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    excl = "yes" if (lo > 0 or hi < 0) else "no"

    group_deb_excess[group] = {'excess': exc_vals, 'mean': mean_exc, 'lo': lo, 'hi': hi}

    print(f"  {group:<20s} {len(deb_fighters):>6} {n:>8} "
          f"{all_fights['p_mkt'].mean():>8.3f} {(all_fights['p_mkt'] < 0.5).mean():>8.0%} "
          f"{all_fights['win'].mean():>4.0%} {mean_exc:>+7.3f} "
          f"[{lo:>+.3f},{hi:>+.3f}] {excl:>7}")

# ═══════════════════════════════════════════════════════════════════
# DEBUTANT DiD: RUSSIAN vs USA DEBUTANTS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("DEBUTANT DiD: RUSSIAN vs USA POST-2022 ENTRANTS")
print("=" * 80)

if 'Russia (ethnic)' in group_deb_excess and 'USA' in group_deb_excess:
    r_exc = group_deb_excess['Russia (ethnic)']['excess']
    u_exc = group_deb_excess['USA']['excess']
    diff = r_exc.mean() - u_exc.mean()

    boots_diff = []
    for _ in range(N_BOOT):
        br = r_exc[rng.choice(len(r_exc), len(r_exc), True)].mean()
        bu = u_exc[rng.choice(len(u_exc), len(u_exc), True)].mean()
        boots_diff.append(br - bu)
    lo_d, hi_d = np.percentile(boots_diff, [2.5, 97.5])
    excl_d = "yes" if (lo_d > 0 or hi_d < 0) else "no"

    print(f"\n  Russian debutant excess: {r_exc.mean():+.3f} (N={len(r_exc)})")
    print(f"  USA debutant excess:     {u_exc.mean():+.3f} (N={len(u_exc)})")
    print(f"  Difference (Rus - USA):  {diff:+.3f} [{lo_d:+.3f},{hi_d:+.3f}] excl 0: {excl_d}")

# Also vs every other group
print(f"\n  DiD vs each control group's debutants:")
print(f"  {'Control':<20s} {'Diff':>8} {'CI':>22} {'Excl 0':>7}")
print("  " + "-" * 60)
for ctrl in ['Caucasus', 'USA', 'Brazil', 'Other']:
    if ctrl not in group_deb_excess or 'Russia (ethnic)' not in group_deb_excess:
        continue
    r_e = group_deb_excess['Russia (ethnic)']['excess']
    c_e = group_deb_excess[ctrl]['excess']
    d = r_e.mean() - c_e.mean()
    boots = []
    for _ in range(N_BOOT):
        br = r_e[rng.choice(len(r_e), len(r_e), True)].mean()
        bc = c_e[rng.choice(len(c_e), len(c_e), True)].mean()
        boots.append(br - bc)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    excl = "yes" if (lo > 0 or hi < 0) else "no"
    print(f"  {ctrl:<20s} {d:>+7.3f} [{lo:>+.3f},{hi:>+.3f}] {excl:>7}")
