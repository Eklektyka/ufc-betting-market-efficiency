#!/usr/bin/env python3
"""
Full home-advantage table: strict vs affinity definitions, per venue-country.
Everything net of closing line. Decision/finish split. BH correction.
"""
import sys, re, warnings, functools, unicodedata, math
import numpy as np
import pandas as pd
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000
MIN_VENUE_BOUTS = 10  # low threshold to include small venues like France

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
fights_raw = pd.read_csv(r'C:\Research\mma-paper\data\ufcstats_fights.csv')
events_raw = pd.read_csv(r'C:\Research\mma-paper\data\ufcstats_events.csv')

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

fight_to_event = dict(zip(fights_raw['fight_url'], fights_raw['event_url']))
event_to_loc = dict(zip(events_raw['event_url'], events_raw['location']))

fight_method = {}
for _, row in fights_raw.iterrows():
    if row['result'] == 'W':
        fight_method[row['fight_url']] = row['method']

# ── Country mapping ──
EC_MAP = {
    'USA': 'United States', 'Brazil': 'Brazil', 'Canada': 'Canada',
    'United Kingdom': 'United Kingdom', 'Australia': 'Australia',
    'United Arab Emirates': 'United Arab Emirates', 'China': 'China',
    'Japan': 'Japan', 'Mexico': 'Mexico', 'France': 'France',
    'Germany': 'Germany', 'Netherlands': 'Netherlands', 'Sweden': 'Sweden',
    'Ireland': 'Ireland', 'South Korea': 'South Korea', 'Singapore': 'Singapore',
    'New Zealand': 'New Zealand', 'Poland': 'Poland', 'Saudi Arabia': 'Saudi Arabia',
    'Qatar': 'Qatar', 'Russia': 'Russia', 'Azerbaijan': 'Azerbaijan',
    'Denmark': 'Denmark', 'Philippines': 'Philippines', 'Indonesia': 'Indonesia',
    'Uruguay': 'Uruguay', 'Czech Republic': 'Czech Republic',
    'Argentina': 'Argentina',
}

def get_event_country(loc_str):
    parts = [p.strip() for p in str(loc_str).split(',')]
    raw = parts[-1] if parts else ''
    return EC_MAP.get(raw, raw)

# ── Affinity table ──
# Maps (fighter_country, event_country) -> True if "affinity home"
# Built on cultural/political/geographic allegiance

ANGLO_BLOC = {'United States', 'Canada', 'United Kingdom', 'Australia',
              'New Zealand', 'Ireland'}
LATAM_BLOC = {'Brazil', 'Mexico', 'Argentina', 'Colombia', 'Ecuador', 'Peru',
              'Chile', 'Venezuela', 'Cuba', 'Dominican Republic', 'Uruguay',
              'Paraguay', 'Bolivia', 'Nicaragua', 'Guatemala'}
BALKAN_BLOC = {'Serbia', 'Croatia', 'Bosnia and Herzegovina', 'Montenegro',
               'North Macedonia', 'Slovenia', 'Kosovo'}
MUSLIM_FIGHTERS = {'Russia',  # Caucasus subset handled below
                   'Azerbaijan', 'Turkey', 'Uzbekistan', 'Kazakhstan',
                   'Kyrgyzstan', 'Tajikistan', 'Turkmenistan', 'Iran', 'Iraq',
                   'Egypt', 'Morocco', 'Tunisia', 'Algeria', 'Jordan', 'Syria',
                   'Lebanon', 'Indonesia', 'Malaysia', 'Pakistan', 'Afghanistan',
                   'Bahrain', 'Nigeria', 'Senegal', 'Cameroon'}
MUSLIM_VENUES = {'United Arab Emirates', 'Saudi Arabia', 'Qatar', 'Azerbaijan'}

def is_caucasus(fighter_name):
    """Check if a Russian-flagged fighter is from the Caucasus."""
    d = matched.get(fighter_name, {})
    if d.get('country') != 'Russia':
        return False
    try:
        lat, lon = float(d.get('lat', 0)), float(d.get('lon', 0))
        if 41 < lat < 45 and 43 < lon < 49:
            return True
    except:
        pass
    bp = str(d.get('birthplace', '')).lower()
    cauc = ['dagestan','chechnya','chechen','grozny','makhachkala','ingush',
            'kabardino','ossetia','nalchik','khasavyurt','buynaksk','derbent',
            'kizlyar','kaspiysk','kizilyurt','sildi','sunzha','teletl',
            'vladikavkaz','babugent','goksuv','batayurt','gvardeyskoe',
            'achkhoy','aymaki','dylym','madzhalis','mekegi','kasumkent','kamysh-kutan']
    return any(m in bp for m in cauc)

def is_affinity_home(fighter_name, event_country):
    """Does the crowd plausibly root for this fighter at this venue?"""
    d = matched.get(fighter_name, {})
    country = d.get('country', '')
    if not country:
        return False

    # Strict match first
    if country == event_country:
        return True

    # Gulf/Muslim-majority venue + Muslim-origin fighter
    if event_country in MUSLIM_VENUES:
        if country in MUSLIM_FIGHTERS:
            # For Russia: only Caucasus fighters count as "affinity home" in Gulf
            if country == 'Russia':
                return is_caucasus(fighter_name)
            return True

    # Balkan bloc (Serb in Croatia venue = NOT home; keep strict per country)
    # Actually Balkans is complex — skip for now

    # Anglo bloc: a Brit in Australia isn't really "home" — too loose. Skip.
    # LatAm bloc: a Colombian in Brazil isn't "home" either. Skip.

    return False

# ── Build bout-level dataset ──
print("Building bout dataset...")
paired = panel.groupby('fight_id').filter(lambda x: len(x) == 2)

bouts = []
for fid, grp in paired.groupby('fight_id'):
    grp = grp.sort_values('fighter')
    r1, r2 = grp.iloc[0], grp.iloc[1]
    fa, fb = r1['fighter'], r1['opponent']

    event_url = fight_to_event.get(r1['fight_url'])
    loc_str = event_to_loc.get(event_url, '') if event_url else ''
    if not loc_str:
        continue

    event_country = get_event_country(loc_str)
    country_a = matched.get(fa, {}).get('country', '')
    country_b = matched.get(fb, {}).get('country', '')
    if not country_a or not country_b:
        continue

    method = fight_method.get(r1['fight_url'], '')
    is_dec = 'DEC' in str(method).upper() or 'Decision' in str(method)

    # Strict home
    home_strict_a = 1 if country_a == event_country else 0
    home_strict_b = 1 if country_b == event_country else 0

    # Affinity home
    home_aff_a = 1 if is_affinity_home(fa, event_country) else 0
    home_aff_b = 1 if is_affinity_home(fb, event_country) else 0

    bouts.append({
        'fight_id': fid, 'date': r1['date'], 'year': r1['year'],
        'fa': fa, 'fb': fb,
        'p_mkt_a': r1['p_close_hi'], 'win_a': int(r1['win']),
        'country_a': country_a, 'country_b': country_b,
        'event_country': event_country, 'event_loc': loc_str,
        'is_dec': is_dec,
        'home_strict_a': home_strict_a, 'home_strict_b': home_strict_b,
        'home_aff_a': home_aff_a, 'home_aff_b': home_aff_b,
    })

bouts = pd.DataFrame(bouts).sort_values('date').reset_index(drop=True)
bouts = bouts[bouts['year'] <= 2025]

# Exclude US events (US is the default, not a treatment)
non_us = bouts[bouts['event_country'] != 'United States'].copy()
# Exclude US-vs-US fights
non_us = non_us[~((non_us['country_a'] == 'United States') & (non_us['country_b'] == 'United States'))]

print(f"  Non-US events, no US-vs-US: {len(non_us)} bouts")

# ── Per venue-country analysis ──
def analyze_home(df_bouts, home_col_a, home_col_b, label):
    """Analyze home advantage for a given home definition."""
    # Clean: exactly one home fighter
    clean = df_bouts[(df_bouts[home_col_a] + df_bouts[home_col_b]) == 1].copy()
    if len(clean) == 0:
        return None

    # Orient to home fighter perspective
    hw, hm, is_dec_arr = [], [], []
    for _, row in clean.iterrows():
        if row[home_col_a] == 1:
            hw.append(row['win_a']); hm.append(row['p_mkt_a'])
        else:
            hw.append(1 - row['win_a']); hm.append(1 - row['p_mkt_a'])
        is_dec_arr.append(row['is_dec'])

    hw = np.array(hw, dtype=float)
    hm = np.array(hm, dtype=float)
    is_dec = np.array(is_dec_arr, dtype=bool)

    n = len(hw)
    excess = hw.mean() - hm.mean()

    # Bootstrap CI
    boots = []
    for _ in range(N_BOOT):
        bi = rng.choice(n, n, replace=True)
        boots.append(hw[bi].mean() - hm[bi].mean())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    raw_p = 2 * min(np.mean(np.array(boots) > 0), np.mean(np.array(boots) < 0))
    if raw_p == 0:
        raw_p = 1 / N_BOOT

    # Decision/finish split
    dec_excess = fin_excess = None
    n_dec = is_dec.sum()
    n_fin = (~is_dec).sum()
    if n_dec >= 10:
        dec_excess = hw[is_dec].mean() - hm[is_dec].mean()
    if n_fin >= 10:
        fin_excess = hw[~is_dec].mean() - hm[~is_dec].mean()

    # MDE at 80% power
    mde = 2.8 * math.sqrt(0.25 / n) if n > 0 else 999

    return {
        'n': n, 'wr': hw.mean(), 'mkt': hm.mean(), 'excess': excess,
        'ci_lo': lo, 'ci_hi': hi, 'raw_p': raw_p,
        'n_dec': n_dec, 'dec_excess': dec_excess,
        'n_fin': n_fin, 'fin_excess': fin_excess,
        'mde': mde,
    }

# ── Run per venue-country ──
print(f"\nAnalyzing per venue-country...")

venue_countries = non_us['event_country'].value_counts()
print(f"\n  Venue-country bout counts (non-US, no US-vs-US):")
for vc, cnt in venue_countries.items():
    marker = ' <-- included' if cnt >= MIN_VENUE_BOUTS else ''
    print(f"    {vc:<30s} {cnt:>4}{marker}")
results = []

for vc, vc_count in venue_countries.items():
    vc_bouts = non_us[non_us['event_country'] == vc]

    # Strict
    strict = analyze_home(vc_bouts, 'home_strict_a', 'home_strict_b', f'{vc} (strict)')
    # Affinity
    aff = analyze_home(vc_bouts, 'home_aff_a', 'home_aff_b', f'{vc} (affinity)')

    if vc_count >= MIN_VENUE_BOUTS:
        results.append({
            'venue': vc, 'vc_count': vc_count,
            'n_strict': strict['n'] if strict else 0,
            'excess_strict': strict['excess'] if strict and strict['n'] >= 3 else None,
            'ci_lo_s': strict['ci_lo'] if strict and strict['n'] >= 3 else None,
            'ci_hi_s': strict['ci_hi'] if strict and strict['n'] >= 3 else None,
            'p_strict': strict['raw_p'] if strict and strict['n'] >= 3 else None,
            'dec_exc_s': strict['dec_excess'] if strict else None,
            'fin_exc_s': strict['fin_excess'] if strict else None,
            'n_dec_s': strict['n_dec'] if strict else 0,
            'n_fin_s': strict['n_fin'] if strict else 0,
            'mde_s': strict['mde'] if strict and strict['n'] >= 3 else None,
            'n_aff': aff['n'] if aff else 0,
            'excess_aff': aff['excess'] if aff and aff['n'] >= 3 else None,
            'ci_lo_a': aff['ci_lo'] if aff and aff['n'] >= 3 else None,
            'ci_hi_a': aff['ci_hi'] if aff and aff['n'] >= 3 else None,
            'wr_s': strict['wr'] if strict and strict['n'] >= 3 else None,
            'mkt_s': strict['mkt'] if strict and strict['n'] >= 3 else None,
        })

# Also compute the aggregate (all non-US)
agg_strict = analyze_home(non_us, 'home_strict_a', 'home_strict_b', 'ALL (strict)')
agg_aff = analyze_home(non_us, 'home_aff_a', 'home_aff_b', 'ALL (affinity)')

# Aggregate without Brazil
non_us_no_br = non_us[non_us['event_country'] != 'Brazil']
agg_no_br = analyze_home(non_us_no_br, 'home_strict_a', 'home_strict_b', 'ALL excl Brazil')

# BH correction on strict p-values
valid_p = [r for r in results if r['p_strict'] is not None]
valid_p.sort(key=lambda x: x['p_strict'])
n_tests = len(valid_p)
for rank, r in enumerate(valid_p, 1):
    r['bh_thresh'] = 0.05 * rank / n_tests
    r['bh_surv'] = r['p_strict'] <= r['bh_thresh']

# Sort by strict excess descending
results.sort(key=lambda x: -(x['excess_strict'] or -999))

# ═══════════════════════════════════════════════════════════════════
# MAIN TABLE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*130}")
print("HOME ADVANTAGE TABLE (non-US events, no US-vs-US, >=30 strict-home bouts)")
print(f"{'='*130}")

print(f"\n  {'Venue':<22s} {'N':>4} {'WR':>5} {'Mkt':>5} {'Excess':>7} {'95% CI':>17} {'p':>6} {'BH':>3} "
      f"{'Dec exc':>8} {'Fin exc':>8} {'MDE':>5}  "
      f"{'N aff':>5} {'Aff exc':>8}")
print("  " + "-" * 130)

for r in results:
    bh = '*' if r.get('bh_surv') else ''
    exc_s = f"{r['excess_strict']:+.3f}" if r['excess_strict'] is not None else '  --'
    ci = f"[{r['ci_lo_s']:+.3f},{r['ci_hi_s']:+.3f}]" if r['ci_lo_s'] is not None else '        --'
    p = f"{r['p_strict']:.3f}" if r['p_strict'] is not None else '  --'
    wr = f"{r['wr_s']:.0%}" if r['wr_s'] is not None else ' --'
    mkt = f"{r['mkt_s']:.0%}" if r['mkt_s'] is not None else ' --'
    dec = f"{r['dec_exc_s']:+.3f}" if r['dec_exc_s'] is not None else '   --'
    fin = f"{r['fin_exc_s']:+.3f}" if r['fin_exc_s'] is not None else '   --'
    mde = f"{r['mde_s']:.0%}" if r['mde_s'] is not None else ' --'
    n_a = f"{r['n_aff']}" if r['n_aff'] else '  --'
    aff = f"{r['excess_aff']:+.3f}" if r['excess_aff'] is not None else '   --'
    print(f"  {r['venue']:<22s} {r['n_strict']:>4} {wr:>5} {mkt:>5} {exc_s:>7} {ci:>17} {p:>6} {bh:>3} "
          f"{dec:>8} {fin:>8} {mde:>5}  {n_a:>5} {aff:>8}")

# Aggregates
print(f"\n  {'--- AGGREGATES ---':<22s}")
for label, agg in [('All intl (strict)', agg_strict),
                     ('All excl Brazil', agg_no_br),
                     ('All intl (affinity)', agg_aff)]:
    if agg:
        dec = f"{agg['dec_excess']:+.3f}" if agg['dec_excess'] is not None else '   --'
        fin = f"{agg['fin_excess']:+.3f}" if agg['fin_excess'] is not None else '   --'
        print(f"  {label:<22s} {agg['n']:>4} {agg['wr']:.0%} {agg['mkt']:.0%} "
              f"{agg['excess']:+.3f} [{agg['ci_lo']:+.3f},{agg['ci_hi']:+.3f}] "
              f"{agg['raw_p']:.3f}     {dec:>8} {fin:>8} {agg['mde']:.0%}")


# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("SUMMARY")
print(f"{'='*80}")

bh_survivors = [r for r in results if r.get('bh_surv')]
print(f"\n  Venues tested: {n_tests}")
print(f"  BH-surviving: {len(bh_survivors)}")
if bh_survivors:
    for r in bh_survivors:
        print(f"    {r['venue']}: {r['excess_strict']:+.3f}, p={r['p_strict']:.3f}")
else:
    print(f"    None survive BH correction.")

# Aggregate interpretation
print(f"\n  (1) DOES HOME HELP (aggregate, net of matchmaking)?")
print(f"      Strict: {agg_strict['excess']:+.3f} [{agg_strict['ci_lo']:+.3f},{agg_strict['ci_hi']:+.3f}] "
      f"(N={agg_strict['n']})")
print(f"      Excl Brazil: {agg_no_br['excess']:+.3f} [{agg_no_br['ci_lo']:+.3f},{agg_no_br['ci_hi']:+.3f}] "
      f"(N={agg_no_br['n']})")

print(f"\n  (2) CROWD OR MATCHMAKING RESIDUE?")
if agg_strict['dec_excess'] is not None and agg_strict['fin_excess'] is not None:
    print(f"      Decision excess: {agg_strict['dec_excess']:+.3f}")
    print(f"      Finish excess:   {agg_strict['fin_excess']:+.3f}")
    if abs(agg_strict['dec_excess']) > abs(agg_strict['fin_excess']) + 0.02:
        print(f"      -> Concentrates in DECISIONS -> judging/crowd mechanism")
    elif abs(agg_strict['fin_excess']) > abs(agg_strict['dec_excess']) + 0.02:
        print(f"      -> Concentrates in FINISHES -> not judging; crowd energy or residual matchmaking")
    else:
        print(f"      -> Roughly uniform -> indeterminate mechanism")

print(f"\n  (3) AFFINITY vs STRICT?")
if agg_aff and agg_strict:
    print(f"      Strict home excess:   {agg_strict['excess']:+.3f}")
    print(f"      Affinity home excess: {agg_aff['excess']:+.3f}")
    if agg_aff['excess'] > agg_strict['excess'] + 0.01:
        print(f"      -> Affinity > strict -> crowd allegiance extends beyond passport")
    else:
        print(f"      -> Affinity ~ strict -> crowd allegiance = nationality, not cultural bloc")
