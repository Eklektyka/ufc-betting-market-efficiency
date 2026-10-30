#!/usr/bin/env python3
"""
CRITICAL: Audit the full odds dataset for East Asian name-order inversions.
Systematic issue: family-name-first names get odds joined to wrong corner.
"""
import csv, re, sys, unicodedata
import numpy as np
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8')
import os; os.chdir(os.path.dirname(os.path.abspath(__file__)))

def normalize(name):
    s = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()
def last_name(n):
    parts = normalize(n).split()
    return parts[-1] if parts else ''
def names_match(a, b):
    na, nb = normalize(a), normalize(b)
    if na == nb: return True
    la, lb = last_name(a), last_name(b)
    if la == lb and na and nb and na[0] == nb[0]: return True
    if len(na) > 4 and len(nb) > 4 and (na in nb or nb in na): return True
    return False

# ═══════════════════════════════════════════════════════════════════
# STEP 1: Build candidate list of East Asian name-order fighters
# ═══════════════════════════════════════════════════════════════════

# Known East Asian family-name-first patterns
# Chinese, Korean, Japanese (sometimes), Mongolian
# BFO often stores as "Family Given" while Tapology/ezoteryka uses "Given Family"
# The matcher then matches by last name... which is the GIVEN name for East Asians

# Build a list of fighters who appear in DIFFERENT name orders across sources

# Source 1: ezoteryka_scored (the joined file we use)
scored_fighters = set()
scored_bouts = []
with open('ezoteryka_scored.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        parts = r['bout'].split(' vs ')
        if len(parts) != 2: continue
        scored_fighters.add(parts[0].strip())
        scored_fighters.add(parts[1].strip())
        scored_bouts.append(r)

# Source 2: bfo_close_all (the odds source)
bfo_fighters = set()
bfo_bouts = {}
with open('bfo_close_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        bfo_fighters.add(r['fighter1_name'])
        bfo_fighters.add(r['fighter2_name'])
        f1 = normalize(r['fighter1_name']); f2 = normalize(r['fighter2_name'])
        bfo_bouts[(f1, f2)] = r
        bfo_bouts[(f2, f1)] = r

# Source 3: bfo_odds_raw (original scrape, has BFO's native name order)
raw_path = r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_raw.csv'
bfo_raw_names = defaultdict(set)  # normalized -> set of raw name forms
with open(raw_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        fn = r['fighter_name'].strip()
        bfo_raw_names[normalize(fn)].add(fn)
        on = r['opponent_name'].strip()
        bfo_raw_names[normalize(on)].add(on)

# Find fighters whose name appears in REVERSED order between BFO and ezoteryka_scored
# A reversed name: "Zhang Mingyang" (BFO) vs "Mingyang Zhang" (Tapology)
# Detection: same set of name parts but in different order
print("=" * 80)
print("STEP 1: CANDIDATE EAST ASIAN NAME-ORDER FIGHTERS")
print("=" * 80)

reversed_names = {}  # normalized_name -> (bfo_form, scored_form)
for scored_name in scored_fighters:
    sn = normalize(scored_name)
    s_parts = sn.split()
    if len(s_parts) != 2: continue

    # Check if BFO has the same fighter with parts reversed
    reversed_n = ' '.join(reversed(s_parts))
    if reversed_n in bfo_raw_names and reversed_n != sn:
        # BFO has this name reversed
        bfo_forms = bfo_raw_names[reversed_n]
        reversed_names[sn] = {
            'scored_name': scored_name,
            'bfo_name': list(bfo_forms)[0],
            'scored_norm': sn,
            'bfo_norm': reversed_n,
        }
    # Also check if the same norm exists but with different raw forms
    if sn in bfo_raw_names:
        for raw_form in bfo_raw_names[sn]:
            raw_parts = normalize(raw_form).split()
            if len(raw_parts) == 2 and raw_parts != s_parts and set(raw_parts) == set(s_parts):
                reversed_names[sn] = {
                    'scored_name': scored_name,
                    'bfo_name': raw_form,
                    'scored_norm': sn,
                    'bfo_norm': normalize(raw_form),
                }

print(f"\nFighters with name-order reversal between BFO and scored: {len(reversed_names)}")
for sn, info in sorted(reversed_names.items()):
    print(f"  Scored: {info['scored_name']:<25} BFO: {info['bfo_name']:<25}")

# ═══════════════════════════════════════════════════════════════════
# STEP 2: Check each reversed-name fight for actual inversion
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("STEP 2: VERIFY INVERSIONS")
print("=" * 80)

# For each fight in ezoteryka_scored involving a reversed-name fighter:
# Compare p_fair_picked against the BFO close_all de-vigged prob
# If they disagree by >10pp, it's an inversion

inversions = []
close_calls = []  # matched correctly but worth noting

for s in scored_bouts:
    parts = s['bout'].split(' vs ')
    if len(parts) != 2: continue
    fa = parts[0].strip(); fb = parts[1].strip()
    fa_n = normalize(fa); fb_n = normalize(fb)

    # Is either fighter a reversed-name candidate?
    has_reversed = fa_n in reversed_names or fb_n in reversed_names
    if not has_reversed: continue

    picked_n = normalize(s['picked_fighter'])
    p_fair = float(s['p_fair_picked'])
    best_line = int(s['best_line'])

    # Find in bfo_close_all
    # Try both normal and reversed name forms
    bfo = None
    for (k1, k2), v in bfo_bouts.items():
        # Try all combinations of normal and reversed names
        fa_try = [fa_n]
        fb_try = [fb_n]
        if fa_n in reversed_names:
            fa_try.append(reversed_names[fa_n]['bfo_norm'])
        if fb_n in reversed_names:
            fb_try.append(reversed_names[fb_n]['bfo_norm'])

        for fa_t in fa_try:
            for fb_t in fb_try:
                if names_match(fa_t, k1) and names_match(fb_t, k2):
                    bfo = v; break
            if bfo: break
        if bfo: break

    if not bfo: continue

    # Which BFO fighter does the picked_fighter match?
    bfo_f1 = normalize(bfo['fighter1_name']); bfo_f2 = normalize(bfo['fighter2_name'])
    bfo_dv1 = float(bfo['f1_devigged_prob']); bfo_dv2 = float(bfo['f2_devigged_prob'])
    bfo_cons1 = float(bfo['f1_consensus_american']); bfo_cons2 = float(bfo['f2_consensus_american'])

    # The picked_fighter should match one BFO fighter
    if names_match(picked_n, bfo_f1):
        expected_p = bfo_dv1; expected_line = bfo_cons1
    elif names_match(picked_n, bfo_f2):
        expected_p = bfo_dv2; expected_line = bfo_cons2
    else:
        # Try reversed
        rev_picked = ' '.join(reversed(picked_n.split()))
        if names_match(rev_picked, bfo_f1):
            expected_p = bfo_dv1; expected_line = bfo_cons1
        elif names_match(rev_picked, bfo_f2):
            expected_p = bfo_dv2; expected_line = bfo_cons2
        else:
            continue

    diff = abs(p_fair - expected_p)
    entry = {
        'bout': s['bout'], 'picked': s['picked_fighter'],
        'p_fair_scored': p_fair, 'p_fair_bfo': expected_p,
        'diff': diff, 'best_line': best_line,
        'bfo_line': expected_line,
        'event': s.get('card_key', ''),
        'result': s['result'],
        'reversed_fighter': fa if fa_n in reversed_names else fb,
    }

    if diff > 0.10:
        inversions.append(entry)
    elif diff > 0.02:
        close_calls.append(entry)

print(f"\nConfirmed inversions (diff > 10pp): {len(inversions)}")
print(f"Close calls (2-10pp diff): {len(close_calls)}")

if inversions:
    print(f"\n{'Bout':<45} {'Picked':<20} {'Scored':>7} {'BFO':>6} {'Diff':>6} {'Reversed fighter'}")
    print("-" * 100)
    for inv in sorted(inversions, key=lambda x: -x['diff']):
        print(f"{inv['bout'][:44]:<45} {inv['picked'][:19]:<20} {inv['p_fair_scored']:>6.1%} "
              f"{inv['p_fair_bfo']:>5.1%} {inv['diff']:>5.1%} {inv['reversed_fighter'][:20]}")

if close_calls:
    print(f"\nClose calls:")
    for cc in close_calls:
        print(f"  {cc['bout'][:44]:<45} diff={cc['diff']:.1%}")

# ═══════════════════════════════════════════════════════════════════
# STEP 3: Distribution across analyses
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("STEP 3: CONTAMINATION SCOPE")
print("=" * 80)

# Women fighters
women_fighters = set()
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if 'women' in r.get('division', '').lower():
            women_fighters.add(normalize(r['fighter_name']))

# Division lookup
division_map = {}
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        fa = normalize(r['fighter_name']); fb = normalize(r['fighter_name_opp'])
        div = r.get('division', '').strip()
        if div: division_map[(fa, fb)] = div; division_map[(fb, fa)] = div

inv_events = set()
inv_women = 0; inv_men = 0
inv_divisions = Counter()

for inv in inversions:
    parts = inv['bout'].split(' vs ')
    fa_n = normalize(parts[0]); fb_n = normalize(parts[1])
    is_women = fa_n in women_fighters or fb_n in women_fighters
    if is_women: inv_women += 1
    else: inv_men += 1
    div = division_map.get((fa_n, fb_n), 'unknown')
    inv_divisions[div] += 1
    inv_events.add(inv['event'])

# Also count: how many of the 3 already-fixed inversions were East Asian?
already_fixed = ['sumudaerji', 'yadong song']
ea_in_fixed = sum(1 for f in already_fixed if any(normalize(f) in normalize(inv['reversed_fighter']) for inv in inversions))

print(f"\nInversions by gender: women={inv_women}, men={inv_men}")
print(f"Inversions by division: {dict(inv_divisions)}")
print(f"Events affected: {len(inv_events)}")
print(f"Previously fixed inversions that were East Asian: {ea_in_fixed} of 3")

# Which analyses are contaminated?
print(f"\n{'='*80}")
print("STEP 3b: CONTAMINATED ANALYSES")
print("=" * 80)

total_scored = len(scored_bouts)
n_inv = len(inversions)
print(f"\nTotal scored picks: {total_scored}")
print(f"Inversions: {n_inv} ({n_inv/total_scored:.1%})")

analyses = [
    ("Self-scout (all picks)", True, "odds magnitudes drive fav/dog/calibration splits"),
    ("Women's favorite analysis", inv_women > 0, f"{inv_women} inversions in women's fights"),
    ("Dispersion analysis", True, "uses same odds join"),
    ("Crowd vs market", True, "market prob from same odds join"),
    ("Peer benchmark", True, "odds-vs-implied uses same join"),
    ("R4 bot (contrarian guardrail)", False, "uses crowd consensus %, not odds magnitude"),
    ("Tapology scoring/backtest", False, "uses fighter pick correctness, not odds"),
    ("CLV persistence (main study)", True, "CLV computed from p_fair"),
    ("Method prop devig", False, "separate BFO prop data, different join"),
]

print(f"\n{'Analysis':<40} {'Contaminated?':>13} {'Why'}")
print("-" * 90)
for name, contaminated, reason in analyses:
    status = "YES — re-run" if contaminated else "SAFE"
    print(f"  {name:<38} {status:>13}   {reason}")

# ═══════════════════════════════════════════════════════════════════
# STEP 4: Broader check — ANY fight with big p_fair vs BFO mismatch
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("STEP 4: FULL DATASET SCAN (all fights, not just reversed-name candidates)")
print("=" * 80)

all_mismatches = []
for s in scored_bouts:
    parts = s['bout'].split(' vs ')
    if len(parts) != 2: continue
    fa_n = normalize(parts[0]); fb_n = normalize(parts[1])
    picked_n = normalize(s['picked_fighter'])
    p_fair = float(s['p_fair_picked'])

    # Find in close_all by trying all name forms
    bfo = bfo_bouts.get((fa_n, fb_n))
    if not bfo:
        for (k1, k2), v in bfo_bouts.items():
            if names_match(fa_n, k1) and names_match(fb_n, k2):
                bfo = v; break
    if not bfo: continue

    bfo_f1 = normalize(bfo['fighter1_name']); bfo_f2 = normalize(bfo['fighter2_name'])
    bfo_dv1 = float(bfo['f1_devigged_prob']); bfo_dv2 = float(bfo['f2_devigged_prob'])

    # Match picked to BFO
    if names_match(picked_n, bfo_f1):
        expected = bfo_dv1
    elif names_match(picked_n, bfo_f2):
        expected = bfo_dv2
    else:
        continue

    diff = abs(p_fair - expected)
    if diff > 0.10:
        all_mismatches.append({
            'bout': s['bout'], 'picked': s['picked_fighter'],
            'scored_p': p_fair, 'bfo_p': expected, 'diff': diff,
            'event': s.get('card_key', ''),
        })

print(f"\nAll fights with >10pp mismatch (any cause): {len(all_mismatches)}")
if all_mismatches:
    print(f"\n{'Bout':<45} {'Picked':<20} {'Scored':>7} {'BFO':>6} {'Diff':>6}")
    print("-" * 90)
    for m in sorted(all_mismatches, key=lambda x: -x['diff']):
        print(f"{m['bout'][:44]:<45} {m['picked'][:19]:<20} {m['scored_p']:>6.1%} "
              f"{m['bfo_p']:>5.1%} {m['diff']:>5.1%}")
        print(f"  {m['event'][:60]}")
