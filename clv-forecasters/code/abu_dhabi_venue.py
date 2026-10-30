#!/usr/bin/env python3
"""
Abu Dhabi / Gulf venue effect: do Muslim-origin fighters beat the market
MORE at Gulf venues than elsewhere? Venue/judging frame, not identity.
"""
import sys, math, re, warnings, functools, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.metrics import brier_score_loss

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# ═══════════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════════
wiki = pd.read_csv(r'C:\Research\ufc\odds\wikidata_mma_fighters.csv')
wiki_lookup = {}
for _, row in wiki.iterrows():
    nn = norm_name(row['name'])
    if nn not in wiki_lookup or (row['lat'] and not wiki_lookup[nn].get('lat')):
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
            reversed_name = ' '.join(parts[1:] + parts[:1])
            if reversed_name in wiki_lookup:
                matched[f] = wiki_lookup[reversed_name]

events = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_events.csv')
fights_raw = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv')
fight_to_event_url = dict(zip(fights_raw['fight_url'], fights_raw['event_url']))
event_url_to_loc = dict(zip(events['event_url'], events['location']))

fight_method = {}
for _, row in fights_raw.iterrows():
    if row['result'] == 'W':
        fight_method[row['fight_url']] = row['method']

# ═══════════════════════════════════════════════════════════════════
# DEFINE FLAGS
# ═══════════════════════════════════════════════════════════════════

# Muslim-majority origin countries (Wikidata nationality)
MUSLIM_ORIGIN_COUNTRIES = {
    'Russia',  # catches Dagestan, Chechnya, Tatarstan etc. — imprecise but only option
    'Azerbaijan', 'Turkey', 'Uzbekistan', 'Kazakhstan', 'Kyrgyzstan',
    'Tajikistan', 'Turkmenistan', 'Iran', 'Iraq', 'Egypt', 'Morocco',
    'Tunisia', 'Algeria', 'Jordan', 'Syria', 'Lebanon', 'Indonesia',
    'Malaysia', 'Pakistan', 'Afghanistan', 'Bahrain', 'Kuwait',
    'Saudi Arabia', 'United Arab Emirates', 'Yemen', 'Nigeria',
    'Senegal', 'Cameroon', 'Somalia', 'Sudan',
}

# Gulf / Muslim-majority VENUES
GULF_VENUES = {
    'Abu Dhabi, Abu Dhabi, United Arab Emirates',
    'Abu Dhabi, United Arab Emirates',
    'Riyadh, Riyadh, Saudi Arabia',
    'Doha, Qatar',
    'Baku, Azerbaijan',
}

def is_muslim_origin(fighter_name):
    d = matched.get(fighter_name, {})
    return d.get('country', '') in MUSLIM_ORIGIN_COUNTRIES

def is_gulf_venue(loc_str):
    return loc_str in GULF_VENUES

# ═══════════════════════════════════════════════════════════════════
# BUILD BOUT DATASET
# ═══════════════════════════════════════════════════════════════════
print("Building bout dataset...")
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

    country_a = matched.get(fa, {}).get('country', '')
    country_b = matched.get(fb, {}).get('country', '')
    if not country_a or not country_b:
        continue

    method = fight_method.get(r1['fight_url'], '')
    method_str = str(method)
    is_decision = 'DEC' in method_str.upper() or 'Decision' in method_str
    # Split decision detection
    is_split = 'S-DEC' in method_str.upper() or 'Split' in method_str

    mo_a = is_muslim_origin(fa)
    mo_b = is_muslim_origin(fb)
    gulf = is_gulf_venue(loc_str)

    bouts.append({
        'fight_id': fid, 'date': r1['date'], 'year': r1['year'],
        'fa': fa, 'fb': fb,
        'p_mkt_a': r1['p_close_hi'], 'win_a': int(r1['win']),
        'country_a': country_a, 'country_b': country_b,
        'event_loc': loc_str,
        'mo_a': mo_a, 'mo_b': mo_b,
        'gulf': gulf,
        'is_decision': is_decision, 'is_split': is_split,
        'method': method,
    })

bouts = pd.DataFrame(bouts).sort_values('date').reset_index(drop=True)

# ═══════════════════════════════════════════════════════════════════
# DESCRIBE THE DATA
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("DATA OVERVIEW")
print(f"{'='*72}")

n_gulf = bouts['gulf'].sum()
n_mo_any = ((bouts['mo_a']) | (bouts['mo_b'])).sum()
print(f"  Total bouts: {len(bouts)}")
print(f"  Gulf venue bouts: {n_gulf}")
print(f"  Bouts with at least one Muslim-origin fighter: {n_mo_any}")

# CRITICAL caveat: Russia = imprecise proxy
russia_fighters = set()
for f in ufc_fighters:
    d = matched.get(f, {})
    if d.get('country') == 'Russia':
        russia_fighters.add(f)
print(f"\n  Russia-coded fighters in panel: {len(russia_fighters)}")
print(f"  NOTE: Russia is an imprecise proxy. Includes ethnic Russians")
print(f"  (Volkov, Pavlovich, etc.) who are NOT the target population.")
print(f"  The 'Muslim-origin' flag is a VENUE INTERACTION test, not a")
print(f"  fighter-identity claim. Noise from mis-flagged Russians")
print(f"  biases the effect TOWARD zero (conservative).")

# Restrict to matchups with one MO fighter vs one non-MO
clean = bouts[(bouts['mo_a'] != bouts['mo_b'])].copy()
# Orient: MO fighter is always "the fighter of interest"
clean['mo_fighter'] = np.where(clean['mo_a'], clean['fa'], clean['fb'])
clean['mo_won'] = np.where(clean['mo_a'], clean['win_a'], 1 - clean['win_a'])
clean['mo_mkt'] = np.where(clean['mo_a'], clean['p_mkt_a'], 1 - clean['p_mkt_a'])

print(f"\n  Clean MO-vs-non-MO bouts: {len(clean)}")
print(f"    At Gulf venues: {clean['gulf'].sum()}")
print(f"    At non-Gulf venues: {(~clean['gulf']).sum()}")

# Gulf venue event breakdown
gulf_events = clean[clean['gulf']].groupby('event_loc').size()
print(f"\n  Gulf venue breakdown:")
for loc, n in gulf_events.items():
    print(f"    {loc}: {n} bouts")


# ═══════════════════════════════════════════════════════════════════
# TEST 1: THE INTERACTION
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 1: THE INTERACTION")
print("MO fighter excess at Gulf vs excess ELSEWHERE")
print("(controls for 'they're just good fighters')")
print(f"{'='*72}")

# At Gulf venues
gulf_mo = clean[clean['gulf']]
# Elsewhere
other_mo = clean[~clean['gulf']]

def excess_stats(subset, label):
    if len(subset) == 0:
        print(f"\n  {label}: no bouts")
        return None, None
    mo_won = subset['mo_won'].values
    mo_mkt = subset['mo_mkt'].values
    actual = mo_won.mean()
    implied = mo_mkt.mean()
    excess = actual - implied
    # Bootstrap CI
    n = len(mo_won)
    boots = []
    for _ in range(N_BOOT):
        bi = rng.choice(n, n, replace=True)
        boots.append(mo_won[bi].mean() - mo_mkt[bi].mean())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"\n  {label} (N={n}):")
    print(f"    MO win rate:      {actual:.3f}")
    print(f"    Market implied:   {implied:.3f}")
    print(f"    Excess:           {excess:+.3f} [{lo:+.3f}, {hi:+.3f}]  sig={sig}")
    return excess, boots

excess_gulf, boots_gulf = excess_stats(gulf_mo, "GULF VENUES")
excess_other, boots_other = excess_stats(other_mo, "ALL OTHER VENUES")

# Interaction: difference in excess
if boots_gulf is not None and boots_other is not None:
    # Bootstrap the DIFFERENCE in excess
    n_g, n_o = len(gulf_mo), len(other_mo)
    interaction_boots = []
    for _ in range(N_BOOT):
        bi_g = rng.choice(n_g, n_g, replace=True)
        bi_o = rng.choice(n_o, n_o, replace=True)
        exc_g = gulf_mo['mo_won'].values[bi_g].mean() - gulf_mo['mo_mkt'].values[bi_g].mean()
        exc_o = other_mo['mo_won'].values[bi_o].mean() - other_mo['mo_mkt'].values[bi_o].mean()
        interaction_boots.append(exc_g - exc_o)
    interaction_boots = np.array(interaction_boots)
    int_lo, int_hi = np.percentile(interaction_boots, [2.5, 97.5])
    int_sig = 'YES' if (int_lo > 0 or int_hi < 0) else 'no'
    int_point = excess_gulf - excess_other
    print(f"\n  INTERACTION (Gulf excess - Other excess):")
    print(f"    {int_point:+.3f} [{int_lo:+.3f}, {int_hi:+.3f}]  sig={int_sig}")
    print(f"    (positive = Gulf venue adds home-like tilt for MO fighters)")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: DECISION vs FINISH SPLIT
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 2: DECISION vs FINISH SPLIT (Gulf venue only)")
print("(Judging/crowd bias concentrates in decisions)")
print(f"{'='*72}")

gulf_dec = gulf_mo[gulf_mo['is_decision']]
gulf_fin = gulf_mo[~gulf_mo['is_decision']]
gulf_split = gulf_mo[gulf_mo['is_split']]

for label, subset in [('DECISIONS', gulf_dec), ('FINISHES', gulf_fin),
                       ('SPLIT DECISIONS', gulf_split)]:
    if len(subset) < 3:
        print(f"\n  {label}: too few bouts ({len(subset)})")
        continue
    mo_won = subset['mo_won'].values
    mo_mkt = subset['mo_mkt'].values
    actual = mo_won.mean()
    implied = mo_mkt.mean()
    excess = actual - implied
    n = len(mo_won)
    boots = []
    for _ in range(N_BOOT):
        bi = rng.choice(n, n, replace=True)
        boots.append(mo_won[bi].mean() - mo_mkt[bi].mean())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"\n  {label} (N={n}):")
    print(f"    MO win rate:      {actual:.3f}")
    print(f"    Market implied:   {implied:.3f}")
    print(f"    Excess:           {excess:+.3f} [{lo:+.3f}, {hi:+.3f}]  sig={sig}")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: ORIGIN vs GENERIC HOME-CROWD
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 3: ORIGIN vs GENERIC HOME-CROWD EFFECT")
print("Is this MO-at-Gulf, or whoever-the-crowd-likes-at-any-venue?")
print(f"{'='*72}")

# Compare: MO excess at Gulf vs the intl home excess from intl_home.py
# The intl home excess was +3.8pp on 487 bouts
# Here we're testing whether the Gulf subset is just another instance of that

# At Gulf venues: ALL fighters, not just MO — does ANYONE get a home boost?
# "Home" at Gulf = UAE/Middle Eastern origin
gulf_all = bouts[bouts['gulf']].copy()
print(f"\n  All Gulf venue bouts: {len(gulf_all)}")

# General crowd-favorite effect at Gulf venues
# Who does the Abu Dhabi crowd favor? Probably MO fighters, but let's check
# by looking at the market-adjusted win rate of MO vs non-MO fighters AT Gulf
gulf_all['any_mo'] = gulf_all['mo_a'] | gulf_all['mo_b']
gulf_all['both_mo'] = gulf_all['mo_a'] & gulf_all['mo_b']
gulf_all['neither_mo'] = ~gulf_all['mo_a'] & ~gulf_all['mo_b']

for label, mask in [('MO vs non-MO (clean)', (gulf_all['mo_a'] != gulf_all['mo_b'])),
                     ('MO vs MO', gulf_all['both_mo']),
                     ('non-MO vs non-MO', gulf_all['neither_mo'])]:
    sub = gulf_all[mask]
    if len(sub) < 3:
        print(f"  {label}: {len(sub)} bouts (too few)")
        continue
    # For MO-vs-nonMO, orient to MO fighter perspective
    if 'clean' in label:
        mo_won = np.where(sub['mo_a'], sub['win_a'], 1 - sub['win_a'])
        mo_mkt = np.where(sub['mo_a'], sub['p_mkt_a'], 1 - sub['p_mkt_a'])
        wr = mo_won.mean()
        mkt = mo_mkt.mean()
        exc = wr - mkt
    else:
        # No natural orientation; just report overall accuracy vs market
        wr = sub['win_a'].mean()
        mkt = sub['p_mkt_a'].mean()
        exc = None  # not meaningful for symmetric matchups
    if exc is not None:
        print(f"  {label}: {len(sub)} bouts, MO WR: {wr:.3f}, mkt: {mkt:.3f}, excess: {exc:+.3f}")
    else:
        print(f"  {label}: {len(sub)} bouts")

# Comparison to intl home effect
print(f"\n  Reference: international home excess (from intl_home.py):")
print(f"    487 clean home-vs-away bouts, excess: +0.038 [-0.003, +0.077]")
if excess_gulf is not None:
    print(f"    MO-at-Gulf excess:                    {excess_gulf:+.3f}")
    if abs(excess_gulf) > 0.038:
        print(f"    -> Gulf MO excess is LARGER than generic intl home effect")
        print(f"       But the Gulf N is much smaller, so this could be noise")
    else:
        print(f"    -> Gulf MO excess is SMALLER/comparable to generic intl home")
        print(f"       Consistent with 'just another home crowd' effect")


# ═══════════════════════════════════════════════════════════════════
# POWER ANALYSIS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("POWER ANALYSIS")
print(f"{'='*72}")

n_gulf_clean = len(gulf_mo)
# Minimum detectable effect at 80% power, alpha=0.05
# For a proportion test: MDE ~ 2.8 * sqrt(p*(1-p)/n) where p ~ 0.5
if n_gulf_clean > 0:
    p_hat = 0.5
    mde = 2.8 * math.sqrt(p_hat * (1-p_hat) / n_gulf_clean)
    print(f"\n  Gulf MO-vs-nonMO sample: N = {n_gulf_clean}")
    print(f"  Minimum detectable effect (80% power, alpha=0.05): {mde:+.3f} ({mde*100:.1f}pp)")
    print(f"  A 5pp effect would need N ~ {int(2.8**2 * 0.25 / 0.05**2)} bouts")
    print(f"  A 10pp effect would need N ~ {int(2.8**2 * 0.25 / 0.10**2)} bouts")
    print(f"  We have {n_gulf_clean} bouts -- can only detect effects > {mde*100:.0f}pp")


# ═══════════════════════════════════════════════════════════════════
# FIGHT-LEVEL DETAIL (Gulf, MO vs non-MO)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("FIGHT DETAIL: Gulf venue, MO vs non-MO")
print(f"{'='*72}")

if len(gulf_mo) > 0:
    print(f"\n  {'MO fighter':<22s} {'Opponent':<22s} {'MO mkt%':>7s} {'Won?':>5s} {'Method':<20s} {'Event'}")
    print("  " + "-" * 100)
    for _, row in gulf_mo.sort_values('date').iterrows():
        mo_name = row['mo_fighter']
        opp = row['fb'] if row['mo_a'] else row['fa']
        mo_m = row['mo_mkt']
        won = 'YES' if row['mo_won'] == 1 else 'no'
        print(f"  {mo_name[:21]:<22s} {opp[:21]:<22s} {mo_m:>6.0%} {won:>5s} {str(row['method'])[:19]:<20s} {row['event_loc'][:40]}")


# ═══════════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("VERDICT")
print(f"{'='*72}")

print(f"\n  Sample sizes:")
print(f"    MO-vs-nonMO at Gulf: {len(gulf_mo)}")
print(f"    MO-vs-nonMO elsewhere: {len(other_mo)}")

if excess_gulf is not None and excess_other is not None:
    print(f"\n  MO excess at Gulf:     {excess_gulf:+.3f}")
    print(f"  MO excess elsewhere:   {excess_other:+.3f}")
    print(f"  Interaction:           {excess_gulf - excess_other:+.3f}")

print(f"""
  INTERPRETATION:
    1. The Gulf venue sample is very small ({len(gulf_mo)} clean bouts).
       The minimum detectable effect is ~{mde*100:.0f}pp -- far above any
       plausible judging bias. This test CANNOT confirm or deny a
       moderate venue effect.

    2. The Russia-as-proxy problem: Wikidata codes all Russians as one
       nationality. Volkov, Pavlovich, Aspinall's opponents are coded
       the same as Makhachev. This adds noise and biases toward zero.

    3. Even if the excess is positive, the interaction (Gulf vs elsewhere)
       is the right test, and it requires the Gulf excess to be
       LARGER THAN the baseline MO excess -- which itself is noisy.

    4. The decision/finish split is the most informative output regardless
       of significance: if Gulf-venue excess concentrates in decisions,
       the mechanism is consistent with judging; if in finishes, it
       rules out the judging hypothesis.

  BOTTOM LINE: Underpowered. The sample cannot distinguish any plausible
  venue effect from zero. The fight-level detail above is more
  informative than the aggregate statistics.
""")
