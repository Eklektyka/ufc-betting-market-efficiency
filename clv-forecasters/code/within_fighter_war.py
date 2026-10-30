#!/usr/bin/env python3
"""
Within-fighter war-shock test: sentiment vs selection.
Which STORY does the structural pattern support?
"""
import sys, re, warnings, functools, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# ═══════════════════════════════════════════════════════════════════
# LOAD (same pipeline)
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
        'region': region,
        'p_mkt': r['p_close_hi'], 'win': int(r['win']),
        'career_n': fight_counter[fighter],
        'post': 1 if r['date'] >= pd.Timestamp('2022-02-24') else 0,
    })

df = pd.DataFrame(rows)
df = df[df['year'] <= 2025].copy()
df['excess'] = df['win'] - df['p_mkt']

eth_rus = df[df['region'] == 'Russia (ethnic)']
print(f"  Total rows: {len(df)}, ethnic Russian: {len(eth_rus)}")


# ═══════════════════════════════════════════════════════════════════
# TEST 1: ENTRANT-QUALITY DISTRIBUTION
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 1: ENTRANT-QUALITY DISTRIBUTION")
print("Are post-2022 Russian entrants positively selected?")
print(f"{'='*72}")

# "Entrant" = first UFC fight after Feb 2022
# Find fighters whose career_n == 1 row is after the cutoff
all_debuts = df[df['career_n'] == 1].copy()
post_debuts = all_debuts[all_debuts['post'] == 1].copy()

rus_post_debuts = post_debuts[post_debuts['region'] == 'Russia (ethnic)']
other_post_debuts = post_debuts[~post_debuts['region'].isin(['Russia (ethnic)', 'Caucasus', 'Central Asia'])]

print(f"\n  Post-2022 UFC debutants:")
print(f"    Ethnic Russian: {len(rus_post_debuts)}")
print(f"    All other (excl Caucasus/CA): {len(other_post_debuts)}")

# For each debutant, get ALL their fights to assess quality
def get_fighter_career(fighter_name, df_all):
    return df_all[df_all['fighter'] == fighter_name].sort_values('date')

print(f"\n  RUSSIAN POST-2022 ENTRANTS:")
print(f"  {'Fighter':<25s} {'Debut':>10s} {'Fights':>6s} {'WR':>5s} {'Avg mkt':>7s} {'Excess':>7s}")
print("  " + "-" * 65)

rus_entrant_names = rus_post_debuts['fighter'].tolist()
rus_entrant_mkts = []
rus_entrant_excess = []

for fighter in sorted(rus_entrant_names):
    career = get_fighter_career(fighter, df)
    debut = career['date'].min().date()
    n_fights = len(career)
    wr = career['win'].mean()
    avg_mkt = career['p_mkt'].mean()
    exc = career['excess'].mean()
    rus_entrant_mkts.extend(career['p_mkt'].tolist())
    rus_entrant_excess.extend(career['excess'].tolist())
    print(f"  {fighter:<25s} {str(debut):>10s} {n_fights:>6} {wr:>4.0%} {avg_mkt:>6.0%} {exc:>+6.3f}")

# Matched non-Russian debutants: same window, random sample
# Get their quality distribution
other_entrant_mkts = []
other_entrant_excess = []
for fighter in other_post_debuts['fighter'].tolist():
    career = get_fighter_career(fighter, df)
    other_entrant_mkts.extend(career['p_mkt'].tolist())
    other_entrant_excess.extend(career['excess'].tolist())

rus_entrant_mkts = np.array(rus_entrant_mkts)
other_entrant_mkts = np.array(other_entrant_mkts)

print(f"\n  QUALITY COMPARISON (market-implied prob across all fights):")
print(f"    Russian entrants:     mean mkt={rus_entrant_mkts.mean():.3f}, "
      f"median={np.median(rus_entrant_mkts):.3f}, N fights={len(rus_entrant_mkts)}")
print(f"    Non-Russian entrants: mean mkt={other_entrant_mkts.mean():.3f}, "
      f"median={np.median(other_entrant_mkts):.3f}, N fights={len(other_entrant_mkts)}")
print(f"    Difference:           {rus_entrant_mkts.mean() - other_entrant_mkts.mean():+.3f}")

# Distribution: what fraction are market underdogs (<50%)?
rus_dog_frac = (rus_entrant_mkts < 0.5).mean()
other_dog_frac = (other_entrant_mkts < 0.5).mean()
print(f"\n    Fraction as market underdog (<50%):")
print(f"      Russian entrants:     {rus_dog_frac:.0%}")
print(f"      Non-Russian entrants: {other_dog_frac:.0%}")

# Actual win rate
rus_entrant_wr = np.array(rus_entrant_excess) + rus_entrant_mkts
other_entrant_wr_arr = np.array(other_entrant_excess) + other_entrant_mkts

print(f"\n    Actual win rate:")
print(f"      Russian entrants:     {(np.array(rus_entrant_excess) + rus_entrant_mkts).mean():.3f}")
print(f"      Non-Russian entrants: {(np.array(other_entrant_excess) + other_entrant_mkts).mean():.3f}")

# Verdict on selection
if rus_entrant_mkts.mean() > other_entrant_mkts.mean() + 0.05:
    selection_verdict = "POSITIVELY SELECTED (Russian entrants priced higher)"
elif abs(rus_entrant_mkts.mean() - other_entrant_mkts.mean()) <= 0.05:
    selection_verdict = "NORMAL SPREAD (similar to non-Russian entrants)"
else:
    selection_verdict = "NEGATIVELY SELECTED (Russian entrants priced lower)"
print(f"\n  SELECTION VERDICT: {selection_verdict}")

# Also check: the post-only Russians specifically
post_only_rus = [f for f in rus_entrant_names if f not in
                 set(eth_rus[eth_rus['post']==0]['fighter'].unique())]
print(f"\n  Post-only Russians (never fought pre-war): {post_only_rus}")
for f in post_only_rus:
    career = get_fighter_career(f, df)
    print(f"    {f}: {len(career)} fights, WR={career['win'].mean():.0%}, "
          f"avg mkt={career['p_mkt'].mean():.0%}, excess={career['excess'].mean():+.3f}")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: WITHIN-FIGHTER (SAME PEOPLE, BEFORE vs AFTER)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 2: WITHIN-FIGHTER (same people, before vs after)")
print("If same fighters priced fairly pre-war and underpriced post-war,")
print("selection is dead.")
print(f"{'='*72}")

# Ethnic Russians who fought on BOTH sides
both_sides = []
for fighter in eth_rus['fighter'].unique():
    pre = eth_rus[(eth_rus['fighter'] == fighter) & (eth_rus['post'] == 0)]
    post = eth_rus[(eth_rus['fighter'] == fighter) & (eth_rus['post'] == 1)]
    if len(pre) >= 1 and len(post) >= 1:
        both_sides.append({
            'fighter': fighter,
            'pre_n': len(pre), 'post_n': len(post),
            'pre_excess': pre['excess'].mean(),
            'post_excess': post['excess'].mean(),
            'pre_mkt': pre['p_mkt'].mean(),
            'post_mkt': post['p_mkt'].mean(),
            'pre_wr': pre['win'].mean(),
            'post_wr': post['win'].mean(),
        })

both_df = pd.DataFrame(both_sides)
print(f"\n  Fighters with fights on BOTH sides of Feb 2022: {len(both_df)}")
print(f"  Total pre-war fights: {both_df['pre_n'].sum()}")
print(f"  Total post-war fights: {both_df['post_n'].sum()}")

if len(both_df) > 0:
    print(f"\n  {'Fighter':<25s} {'Pre N':>5} {'Pre exc':>8} {'Post N':>6} {'Post exc':>9} {'Swing':>7}")
    print("  " + "-" * 65)
    for _, row in both_df.sort_values('post_excess', ascending=False).iterrows():
        swing = row['post_excess'] - row['pre_excess']
        flag = ' ***' if abs(swing) > 0.15 else ''
        print(f"  {row['fighter']:<25s} {row['pre_n']:>5} {row['pre_excess']:>+7.3f} "
              f"{row['post_n']:>6} {row['post_excess']:>+8.3f} {swing:>+6.3f}{flag}")

    # Aggregate within-fighter
    # Weight by fights or equal weight?
    # Equal weight per fighter (fixed effect analog)
    mean_pre = both_df['pre_excess'].mean()
    mean_post = both_df['post_excess'].mean()
    within_swing = mean_post - mean_pre
    print(f"\n  Within-fighter aggregate (equal weight per fighter):")
    print(f"    Mean pre excess:  {mean_pre:+.3f}")
    print(f"    Mean post excess: {mean_post:+.3f}")
    print(f"    Within swing:     {within_swing:+.3f}")

    # Fight-weighted
    total_pre_exc = sum(r['pre_excess'] * r['pre_n'] for _, r in both_df.iterrows())
    total_post_exc = sum(r['post_excess'] * r['post_n'] for _, r in both_df.iterrows())
    n_pre_total = both_df['pre_n'].sum()
    n_post_total = both_df['post_n'].sum()
    weighted_pre = total_pre_exc / n_pre_total
    weighted_post = total_post_exc / n_post_total
    weighted_swing = weighted_post - weighted_pre
    print(f"\n  Within-fighter aggregate (fight-weighted):")
    print(f"    Weighted pre excess:  {weighted_pre:+.3f} (N={n_pre_total})")
    print(f"    Weighted post excess: {weighted_post:+.3f} (N={n_post_total})")
    print(f"    Weighted swing:       {weighted_swing:+.3f}")

    # Bootstrap CI on within-fighter swing (resample fighters)
    n_both = len(both_df)
    boots = []
    for _ in range(N_BOOT):
        bi = rng.choice(n_both, n_both, replace=True)
        b_pre = both_df.iloc[bi]['pre_excess'].mean()
        b_post = both_df.iloc[bi]['post_excess'].mean()
        boots.append(b_post - b_pre)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"    Within-swing CI: [{lo:+.3f}, {hi:+.3f}]  sig={sig}")
    print(f"    (N={n_both} fighters, bootstrap resamples fighters)")

    # Flag sample size
    if n_pre_total + n_post_total < 15:
        print(f"\n    WARNING: only {n_pre_total + n_post_total} total fights across {n_both} fighters")
        print(f"    Within-fighter test is UNDERPOWERED")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: DECOMPOSITION
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 3: DECOMPOSITION")
print("How much of +18pp is within-career vs post-only entrants?")
print(f"{'='*72}")

# Both-sides fighters: their POST contribution
both_names = set(both_df['fighter']) if len(both_df) > 0 else set()
post_only_names = set(eth_rus[eth_rus['post']==1]['fighter'].unique()) - both_names

both_post_fights = eth_rus[(eth_rus['fighter'].isin(both_names)) & (eth_rus['post']==1)]
postonly_fights = eth_rus[(eth_rus['fighter'].isin(post_only_names)) & (eth_rus['post']==1)]

print(f"\n  Post-war ethnic Russian fights: {len(eth_rus[eth_rus['post']==1])}")
print(f"    (a) Both-sides fighters (within-career): {len(both_post_fights)} fights, "
      f"excess={both_post_fights['excess'].mean():+.3f}")
print(f"    (b) Post-only entrants:                  {len(postonly_fights)} fights, "
      f"excess={postonly_fights['excess'].mean():+.3f}")

if len(both_post_fights) > 0 and len(postonly_fights) > 0:
    pct_a = len(both_post_fights) / len(eth_rus[eth_rus['post']==1])
    pct_b = len(postonly_fights) / len(eth_rus[eth_rus['post']==1])
    contrib_a = both_post_fights['excess'].mean() * pct_a
    contrib_b = postonly_fights['excess'].mean() * pct_b
    total = both_post_fights['excess'].sum() + postonly_fights['excess'].sum()
    print(f"\n    Contribution to total post excess:")
    print(f"      (a) Within-career: {contrib_a:+.3f} ({pct_a:.0%} of fights)")
    print(f"      (b) Post-only:     {contrib_b:+.3f} ({pct_b:.0%} of fights)")
    print(f"      Total:             {contrib_a + contrib_b:+.3f}")

    if both_post_fights['excess'].mean() > 0.05 and postonly_fights['excess'].mean() > 0.05:
        print(f"\n    BOTH contributing positively -> robust, not purely selection")
    elif both_post_fights['excess'].mean() > 0.05 and postonly_fights['excess'].mean() <= 0.05:
        print(f"\n    Only within-career contributing -> pure sentiment (existing fighters repriced)")
    elif both_post_fights['excess'].mean() <= 0.05 and postonly_fights['excess'].mean() > 0.05:
        print(f"\n    Only post-entrants contributing -> LEAN ON TEST 1 to distinguish")


# ═══════════════════════════════════════════════════════════════════
# TEST 4: CAUCASUS WITHIN-FIGHTER PLACEBO
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("TEST 4: CAUCASUS WITHIN-FIGHTER PLACEBO")
print("Same pre/post on both-sides Caucasus fighters.")
print("Should be flat/negative if effect is Russian-specific.")
print(f"{'='*72}")

cauc = df[df['region'] == 'Caucasus']
cauc_both = []
for fighter in cauc['fighter'].unique():
    pre = cauc[(cauc['fighter'] == fighter) & (cauc['post'] == 0)]
    post = cauc[(cauc['fighter'] == fighter) & (cauc['post'] == 1)]
    if len(pre) >= 1 and len(post) >= 1:
        cauc_both.append({
            'fighter': fighter,
            'pre_n': len(pre), 'post_n': len(post),
            'pre_excess': pre['excess'].mean(),
            'post_excess': post['excess'].mean(),
        })

cauc_both_df = pd.DataFrame(cauc_both) if cauc_both else pd.DataFrame()

if len(cauc_both_df) > 0:
    print(f"\n  Caucasus fighters with fights on BOTH sides: {len(cauc_both_df)}")
    print(f"\n  {'Fighter':<25s} {'Pre N':>5} {'Pre exc':>8} {'Post N':>6} {'Post exc':>9} {'Swing':>7}")
    print("  " + "-" * 65)
    for _, row in cauc_both_df.sort_values('post_excess', ascending=False).iterrows():
        swing = row['post_excess'] - row['pre_excess']
        print(f"  {row['fighter']:<25s} {row['pre_n']:>5} {row['pre_excess']:>+7.3f} "
              f"{row['post_n']:>6} {row['post_excess']:>+8.3f} {swing:>+6.3f}")

    c_mean_pre = cauc_both_df['pre_excess'].mean()
    c_mean_post = cauc_both_df['post_excess'].mean()
    c_swing = c_mean_post - c_mean_pre
    print(f"\n  Within-fighter aggregate (equal weight):")
    print(f"    Mean pre excess:  {c_mean_pre:+.3f}")
    print(f"    Mean post excess: {c_mean_post:+.3f}")
    print(f"    Within swing:     {c_swing:+.3f}")

    # Bootstrap
    n_cb = len(cauc_both_df)
    boots_c = []
    for _ in range(N_BOOT):
        bi = rng.choice(n_cb, n_cb, replace=True)
        boots_c.append(cauc_both_df.iloc[bi]['post_excess'].mean() -
                       cauc_both_df.iloc[bi]['pre_excess'].mean())
    lo_c, hi_c = np.percentile(boots_c, [2.5, 97.5])
    sig_c = 'YES' if (lo_c > 0 or hi_c < 0) else 'no'
    print(f"    CI: [{lo_c:+.3f}, {hi_c:+.3f}]  sig={sig_c}")

    # Within-fighter DiD: Russian swing vs Caucasus swing
    if len(both_df) > 0:
        within_did = within_swing - c_swing
        # Bootstrap DiD
        boots_did = []
        for _ in range(N_BOOT):
            bi_r = rng.choice(n_both, n_both, replace=True)
            bi_c = rng.choice(n_cb, n_cb, replace=True)
            r_swing = both_df.iloc[bi_r]['post_excess'].mean() - both_df.iloc[bi_r]['pre_excess'].mean()
            c_swing_b = cauc_both_df.iloc[bi_c]['post_excess'].mean() - cauc_both_df.iloc[bi_c]['pre_excess'].mean()
            boots_did.append(r_swing - c_swing_b)
        lo_d, hi_d = np.percentile(boots_did, [2.5, 97.5])
        sig_d = 'YES' if (lo_d > 0 or hi_d < 0) else 'no'
        print(f"\n  WITHIN-FIGHTER DiD (Russian swing - Caucasus swing):")
        print(f"    {within_did:+.3f} [{lo_d:+.3f}, {hi_d:+.3f}]  sig={sig_d}")
else:
    print(f"  No Caucasus fighters with fights on both sides")


# ═══════════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*72}")
print("VERDICT: SENTIMENT vs SELECTION")
print(f"{'='*72}")

print(f"""
  TEST 1 — ENTRANT-QUALITY:
    Selection predicts: Russian post-2022 entrants are UNUSUALLY GOOD
    (visa barriers filter to elite only).
    Data: Russian entrant avg mkt = {rus_entrant_mkts.mean():.0%}, non-Russian = {other_entrant_mkts.mean():.0%}
    Russian underdogs: {rus_dog_frac:.0%} of fights, non-Russian: {other_dog_frac:.0%}
    -> {selection_verdict}
""")

if len(both_df) > 0:
    print(f"""  TEST 2 -- WITHIN-FIGHTER:
    Selection predicts: no within-fighter change (same people, same skill).
    Sentiment predicts: same fighters repriced post-war.
    Data: {n_both} fighters fought both sides.
    Within-fighter swing: {within_swing:+.3f} (N={n_both} fighters, {n_pre_total}+{n_post_total} fights)
    Direction: {'POSITIVE (same fighters underpriced post-war)' if within_swing > 0.05 else 'FLAT/NEGATIVE' if within_swing <= 0.05 else '???'}
    -> {'Supports SENTIMENT' if within_swing > 0.05 else 'Supports SELECTION' if within_swing <= -0.05 else 'INDETERMINATE'}
""")

    print(f"""  TEST 3 -- DECOMPOSITION:
    Both-sides fighters post excess: {both_post_fights['excess'].mean():+.3f} ({len(both_post_fights)} fights)
    Post-only entrants excess:       {postonly_fights['excess'].mean():+.3f} ({len(postonly_fights)} fights)
    -> {'BOTH contributing' if both_post_fights['excess'].mean() > 0.05 and postonly_fights['excess'].mean() > 0.05 else 'Mixed'}
""")

if len(cauc_both_df) > 0:
    print(f"""  TEST 4 -- CAUCASUS PLACEBO (within-fighter):
    Caucasus within-fighter swing: {c_swing:+.3f} (N={n_cb} fighters)
    Russian within-fighter swing:  {within_swing:+.3f} (N={n_both} fighters)
    Within-fighter DiD:            {within_did:+.3f}
    -> {'Russian-specific: Caucasus flat, Russian positive' if within_swing > 0.05 and c_swing < 0.05 else 'Both move similarly -- era effect, not Russian-specific' if abs(within_swing - c_swing) < 0.1 else 'Mixed'}
""")

print(f"""  OVERALL:
    The question is not magnitude (N is too small) but WHICH STORY FITS.

    Sentiment predicts:
      - Within-fighter swing is positive (same people repriced)
      - Entrant quality is NORMAL (not positively selected)
      - Effect is Russian-specific (absent in Caucasus placebo)

    Selection predicts:
      - Within-fighter swing is zero (same people, same pricing)
      - Entrant quality is UNUSUALLY HIGH (only elite got through)
      - Effect is in the new entrants, not the continuing fighters

    Pattern match: {'SENTIMENT' if within_swing > 0.05 and abs(rus_entrant_mkts.mean() - other_entrant_mkts.mean()) < 0.05 and (len(cauc_both_df)==0 or c_swing < 0.05) else 'SELECTION' if within_swing <= 0.05 and rus_entrant_mkts.mean() > other_entrant_mkts.mean() + 0.05 else 'MIXED/INDETERMINATE'}

    Forward test: accumulate N through 2026-27. If within-fighter
    swing persists on N>50 with Caucasus flat, sentiment is confirmed.
""")
