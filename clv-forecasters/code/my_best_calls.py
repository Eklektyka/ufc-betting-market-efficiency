#!/usr/bin/env python3
"""Find picks where Ezoteryka was right and almost nobody else was."""
import csv, os, re, sys, unicodedata
import numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

PICKS_DIR = r'C:\Research\ufc\picks\users'
AUTHOR = 'Ezoteryka'

def normalize(name):
    s = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()
def normalize_event(name):
    return re.sub(r'\s+\d{1}$', '', normalize(name))
def names_match(a, b):
    na, nb = normalize(a), normalize(b)
    if na == nb: return True
    la = na.split()[-1] if na.split() else ''
    lb = nb.split()[-1] if nb.split() else ''
    if la == lb and len(na) > 0 and len(nb) > 0 and na[0] == nb[0]: return True
    if len(na) > 4 and len(nb) > 4 and (na in nb or nb in na): return True
    return False
def get_method_cat(s):
    s = s.strip().lower()
    if 'ko' in s or 'tko' in s: return 'KO/TKO'
    if 'submission' in s: return 'Submission'
    if 'decision' in s: return 'Decision'
    return None
def get_round(s):
    import re as re2
    m = re2.search(r'Round\s*(\d)', s)
    return int(m.group(1)) if m else None

# Load all users
import json
state = json.load(open(r'C:\Research\ufc\picks\state.json'))
all_users = [u for u, v in state['users'].items() if v['status'] == 'done']

# Load Ezoteryka's picks with method/round
with open(os.path.join(PICKS_DIR, 'Ezoteryka.csv'), encoding='utf-8') as f:
    my_picks = list(csv.DictReader(f))

# Build bout key → my pick info
my_bouts = {}
for p in my_picks:
    key = (normalize_event(p['event']), normalize(p['fighter_picked']), normalize(p['opponent']))
    alt_key = (normalize_event(p['event']), normalize(p['opponent']), normalize(p['fighter_picked']))
    my_bouts[key] = p
    my_bouts[alt_key] = p

# For each bout Ezoteryka picked, count how many peers picked the same fighter
print("Loading all users' picks...", flush=True)

# Index: (norm_event, norm_fighter_a, norm_fighter_b) → list of (username, picked_fighter, picked_method, picked_round)
bout_picks = defaultdict(list)

for username in all_users:
    safe = username.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): continue
    with open(path, encoding='utf-8') as f:
        for p in csv.DictReader(f):
            fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
            ev_n = normalize_event(p['event'])
            # Canonical key: sorted fighters
            fighters = tuple(sorted([fp_n, opp_n]))
            pm = get_method_cat(p.get('picked_method', '')) if p.get('picked_method') else None
            pr = p.get('picked_round', '').strip() if p.get('picked_round') else None
            bout_picks[(ev_n, fighters[0], fighters[1])].append({
                'user': username, 'picked': fp_n, 'method': pm, 'round': pr,
            })

print(f"Bouts with picks: {len(bout_picks)}")

# Now score each of my picks
results_a = []  # fighter-only contrarian
results_b = []  # fighter + method
results_c = []  # fighter + method + round

for p in my_picks:
    fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
    ev_n = normalize_event(p['event'])
    correct = p['correct'] == 'YES'
    if not correct: continue  # only care about picks I got RIGHT

    my_method = get_method_cat(p.get('picked_method', ''))
    my_round = p.get('picked_round', '').strip()
    actual_method = get_method_cat(p.get('actual_method', ''))
    actual_method_raw = p.get('actual_method', '')
    actual_round = get_round(actual_method_raw)

    fighters = tuple(sorted([fp_n, opp_n]))
    picks_on_bout = bout_picks.get((ev_n, fighters[0], fighters[1]), [])
    total_pickers = len(picks_on_bout)
    if total_pickers < 20: continue  # need enough peers for a meaningful %

    # a) How many picked the same FIGHTER?
    same_fighter = sum(1 for pk in picks_on_bout if pk['picked'] == fp_n)
    pct_same = same_fighter / total_pickers
    contrarian_pct = 1 - pct_same  # % who picked AGAINST me

    results_a.append({
        'event': p['event'], 'fighter': p['fighter_picked'], 'opponent': p['opponent'],
        'actual_method': actual_method_raw,
        'pickers': total_pickers, 'same_fighter': same_fighter,
        'contrarian_pct': contrarian_pct,
        'my_method': p.get('picked_method', ''), 'my_round': my_round,
    })

    # b) How many picked same fighter AND same method?
    if my_method and actual_method and my_method == actual_method:
        same_fm = sum(1 for pk in picks_on_bout
                      if pk['picked'] == fp_n and pk.get('method') == my_method)
        pct_fm = same_fm / total_pickers
        results_b.append({
            'event': p['event'], 'fighter': p['fighter_picked'], 'opponent': p['opponent'],
            'actual_method': actual_method_raw,
            'pickers': total_pickers, 'same_fm': same_fm, 'pct_fm': pct_fm,
            'my_method': p.get('picked_method', ''), 'my_round': my_round,
        })

        # c) How many picked same fighter + method + round?
        if my_round and actual_round:
            my_round_num = get_round(my_round) if 'Round' in my_round else None
            if my_round_num and my_round_num == actual_round:
                same_fmr = sum(1 for pk in picks_on_bout
                               if pk['picked'] == fp_n and pk.get('method') == my_method
                               and pk.get('round') and str(actual_round) in pk['round'])
                pct_fmr = same_fmr / total_pickers
                results_c.append({
                    'event': p['event'], 'fighter': p['fighter_picked'], 'opponent': p['opponent'],
                    'actual_method': actual_method_raw,
                    'pickers': total_pickers, 'same_fmr': same_fmr, 'pct_fmr': pct_fmr,
                    'my_method': p.get('picked_method', ''), 'my_round': my_round,
                })

# ═══════════════════════════════════════════════════════════════════
# a) MOST CONTRARIAN CORRECT FIGHTER PICKS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("a) MY MOST CONTRARIAN CORRECT PICKS (fighter only)")
print("  Fights where I picked the winner and most people didn't")
print(f"{'='*80}")

results_a.sort(key=lambda x: -x['contrarian_pct'])
print(f"\n  {'Fighter I picked':<25} {'Opponent':<25} {'Result':<30} {'%Against':>8} {'n':>4}")
print("  " + "-" * 95)
for r in results_a[:20]:
    print(f"  {r['fighter'][:24]:<25} {r['opponent'][:24]:<25} {r['actual_method'][:29]:<30} "
          f"{r['contrarian_pct']:>7.0%} {r['pickers']:>4}")

# ═══════════════════════════════════════════════════════════════════
# b) MOST CONTRARIAN CORRECT FIGHTER + METHOD
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("b) MY MOST CONTRARIAN CORRECT FIGHTER + METHOD PICKS")
print("  Fights where I nailed both the winner AND the method, and few others did")
print(f"{'='*80}")

results_b.sort(key=lambda x: x['pct_fm'])
print(f"\n  {'Fighter':<22} {'Opp':<22} {'My method':<12} {'Result':<28} {'Same%':>6} {'n/tot':>8}")
print("  " + "-" * 100)
for r in results_b[:20]:
    print(f"  {r['fighter'][:21]:<22} {r['opponent'][:21]:<22} {r['my_method']:<12} "
          f"{r['actual_method'][:27]:<28} {r['pct_fm']:>5.0%} {r['same_fm']:>3}/{r['pickers']:<3}")

# ═══════════════════════════════════════════════════════════════════
# c) MOST CONTRARIAN CORRECT FIGHTER + METHOD + ROUND
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("c) MY MOST CONTRARIAN CORRECT FIGHTER + METHOD + ROUND PICKS")
print("  The full Nostradamus calls")
print(f"{'='*80}")

if results_c:
    results_c.sort(key=lambda x: x['pct_fmr'])
    print(f"\n  {'Fighter':<22} {'Opp':<22} {'Call':<18} {'Result':<28} {'Same%':>6} {'n/tot':>8}")
    print("  " + "-" * 105)
    for r in results_c[:15]:
        call = f"{r['my_method']} {r['my_round']}"
        print(f"  {r['fighter'][:21]:<22} {r['opponent'][:21]:<22} {call:<18} "
              f"{r['actual_method'][:27]:<28} {r['pct_fmr']:>5.0%} {r['same_fmr']:>3}/{r['pickers']:<3}")
else:
    print("\n  No fighter+method+round triple hits found (need method data for peers)")
    print("  Most peers are v1 users without method/round data.")

# Check: Dawson vs Rebecki specifically
print(f"\n{'='*80}")
print("YOUR DAWSON CALL:")
print(f"{'='*80}")
for r in results_b:
    if 'dawson' in r['fighter'].lower() or 'dawson' in r['opponent'].lower():
        print(f"  {r['fighter']} vs {r['opponent']}")
        print(f"  Your call: {r['my_method']} {r['my_round']}")
        print(f"  Result: {r['actual_method']}")
        print(f"  Same fighter+method: {r['same_fm']}/{r['pickers']} ({r['pct_fm']:.0%})")
        break
else:
    for r in results_a:
        if 'dawson' in r['fighter'].lower() or 'dawson' in r['opponent'].lower():
            print(f"  {r['fighter']} vs {r['opponent']}")
            print(f"  Your call: {r['my_method']} {r['my_round']}")
            print(f"  Result: {r['actual_method']}")
            print(f"  Same fighter: {r['same_fighter']}/{r['pickers']} ({1-r['contrarian_pct']:.0%})")
            print(f"  (Method not matched — may have been correct but different method category)")
            break
