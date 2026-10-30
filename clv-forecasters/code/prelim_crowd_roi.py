#!/usr/bin/env python3
"""
Final ROI test: prelim-favorite crowd edge at consensus closing line.
Garden-of-forking-paths acknowledged. Split-half persistence required.
"""
import csv, json, os, re, sys, unicodedata, math
import numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
SEED = 67; N_BOOT = 5000
rng = np.random.RandomState(SEED)
PICKS_DIR = r'C:\Research\ufc\picks\users'

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
def ai(o): return -o/(-o+100) if o < 0 else 100/(o+100)

# Load all users' picks for crowd consensus
state = json.load(open(r'C:\Research\ufc\picks\state.json'))
all_users = [u for u, v in state['users'].items() if v['status'] == 'done']

print("Building crowd consensus...", flush=True)
bout_crowd = defaultdict(lambda: {'total': 0, 'picks': defaultdict(int)})
for u in all_users:
    safe = u.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): continue
    with open(path, encoding='utf-8') as f:
        for p in csv.DictReader(f):
            fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
            fighters = tuple(sorted([fp_n, opp_n]))
            key = (normalize_event(p['event']), fighters[0], fighters[1])
            bout_crowd[key]['total'] += 1
            bout_crowd[key]['picks'][fp_n] += 1

# Load bfo_close_all for CONSENSUS de-vigged odds (NOT best-line)
close_all = {}
with open('bfo_close_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        f1 = normalize(r['fighter1_name']); f2 = normalize(r['fighter2_name'])
        date = r['event_date']
        # Consensus de-vigged
        dv1 = float(r['f1_devigged_prob']); dv2 = float(r['f2_devigged_prob'])
        # Consensus American (for ROI calc — this is consensus, not best-line)
        cons1 = float(r['f1_consensus_american']); cons2 = float(r['f2_consensus_american'])
        close_all[(f1, f2)] = {'dv1': dv1, 'dv2': dv2, 'cons1': cons1, 'cons2': cons2,
                               'f1': f1, 'f2': f2, 'date': date, 'event': r['event_name']}
        close_all[(f2, f1)] = {'dv1': dv2, 'dv2': dv1, 'cons1': cons2, 'cons2': cons1,
                               'f1': f2, 'f2': f1, 'date': date, 'event': r['event_name']}

# Load outcomes from ezoteryka_scored
outcomes = {}
with open('ezoteryka_scored.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        parts = r['bout'].split(' vs ')
        if len(parts) != 2: continue
        if r['result'] == 'win': winner = normalize(r['picked_fighter'])
        else: winner = normalize(parts[1]) if normalize(r['picked_fighter']) == normalize(parts[0]) else normalize(parts[0])
        outcomes[(normalize(parts[0]), normalize(parts[1]))] = winner
        outcomes[(normalize(parts[1]), normalize(parts[0]))] = winner

# Build fight-level dataset: for each fight in close_all, determine crowd fav, card position, outcome
# Card position: use Ezoteryka's pick order as proxy
event_bout_idx = defaultdict(int)
with open(os.path.join(PICKS_DIR, 'Ezoteryka.csv'), encoding='utf-8') as f:
    ezo_picks = list(csv.DictReader(f))

bout_positions = {}
event_idx = defaultdict(int)
for p in ezo_picks:
    ev_n = normalize_event(p['event'])
    fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
    fighters = tuple(sorted([fp_n, opp_n]))
    pos = event_idx[ev_n]
    event_idx[ev_n] += 1
    bout_positions[(ev_n, fighters[0], fighters[1])] = pos

print("Building fight-level dataset...", flush=True)

fights = []
for (f1, f2), odds in close_all.items():
    if f1 > f2: continue  # avoid duplicates
    fighters = tuple(sorted([f1, f2]))
    winner = outcomes.get((f1, f2))
    if winner is None: continue

    # Crowd consensus
    crowd_key = None
    for ev_n in set(normalize_event(p['event']) for p in ezo_picks):
        bc = bout_crowd.get((ev_n, fighters[0], fighters[1]))
        if bc and bc['total'] >= 50:
            crowd_key = (ev_n, fighters[0], fighters[1])
            break
    if not crowd_key: continue
    bc = bout_crowd[crowd_key]

    # Crowd favorite = fighter with more picks
    crowd_fav = max(bc['picks'].items(), key=lambda x: x[1])
    crowd_fav_name = crowd_fav[0]
    crowd_pct = crowd_fav[1] / bc['total']

    # Card position
    pos = bout_positions.get(crowd_key)
    if pos is None: continue
    card_pos = 'Main event' if pos == 0 else ('Main card' if pos < 5 else 'Prelims')

    # Consensus odds for the crowd-favorite fighter
    if crowd_fav_name == odds['f1']:
        cons_line = odds['cons1']; dv_prob = odds['dv1']
    elif crowd_fav_name == odds['f2']:
        cons_line = odds['cons2']; dv_prob = odds['dv2']
    else:
        # Name mismatch — try fuzzy
        if names_match(crowd_fav_name, odds['f1']):
            cons_line = odds['cons1']; dv_prob = odds['dv1']
        elif names_match(crowd_fav_name, odds['f2']):
            cons_line = odds['cons2']; dv_prob = odds['dv2']
        else:
            continue

    # Did crowd favorite win?
    crowd_fav_won = names_match(crowd_fav_name, winner)

    # ROI at consensus line (includes vig — this IS the realistic close)
    if cons_line > 0:
        dec = 1 + cons_line / 100
    else:
        dec = 1 + 100 / abs(cons_line)
    profit = (dec - 1) * 100 if crowd_fav_won else -100

    fights.append({
        'crowd_fav': crowd_fav_name, 'crowd_pct': crowd_pct,
        'card_pos': card_pos, 'cons_line': cons_line, 'dv_prob': dv_prob,
        'won': crowd_fav_won, 'profit': profit,
        'event': odds['event'], 'date': odds['date'],
    })

print(f"Fights with crowd+odds+outcome+position: {len(fights)}")
fights.sort(key=lambda f: f['date'])

# ═══════════════════════════════════════════════════════════════════
# PRELIM CROWD-FAVORITE ROI
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("PRELIM CROWD-FAVORITE ROI AT CONSENSUS CLOSING LINE")
print("(net of vig — consensus line includes the vig)")
print(f"{'='*80}")

def roi_analysis(subset, label):
    n = len(subset)
    if n == 0:
        print(f"\n  {label}: n=0"); return None
    total_profit = sum(f['profit'] for f in subset)
    roi = total_profit / (n * 100)
    wr = sum(f['won'] for f in subset) / n
    mean_dv = np.mean([f['dv_prob'] for f in subset])
    mean_line = np.mean([f['cons_line'] for f in subset])

    # Fight-clustered bootstrap
    events = list(set(f['event'] for f in subset))
    eb = defaultdict(list)
    for f in subset: eb[f['event']].append(f)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sp = sn = 0
        for e in se:
            for f in eb[e]: sp += f['profit']; sn += 1
        boot.append(sp / (sn * 100) if sn > 0 else 0)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))
    excl = ci[0] > 0

    print(f"\n  {label}:")
    print(f"    n={n}, WR={wr:.1%}, mean de-vig implied={mean_dv:.1%}, mean cons line={mean_line:+.0f}")
    print(f"    Profit: ${total_profit:+,.0f}, ROI={roi:+.1%} CI=[{ci[0]:+.1%},{ci[1]:+.1%}]")
    print(f"    CI excludes zero: {'YES' if excl else 'NO'}")
    return {'roi': roi, 'ci': ci, 'n': n, 'wr': wr, 'excl': excl}

# Main test
prelims = [f for f in fights if f['card_pos'] == 'Prelims']
main_events = [f for f in fights if f['card_pos'] == 'Main event']

prelim_result = roi_analysis(prelims, "PRELIM crowd-favorites (primary test)")
main_result = roi_analysis(main_events, "MAIN EVENT crowd-favorites (negative control)")
roi_analysis([f for f in fights if f['card_pos'] == 'Main card'], "MAIN CARD crowd-favorites (context)")
roi_analysis(fights, "ALL fights crowd-favorites (reference)")

# ═══════════════════════════════════════════════════════════════════
# SPLIT-HALF PERSISTENCE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("SPLIT-HALF PERSISTENCE (temporal)")
print(f"{'='*80}")

mid = len(prelims) // 2
h1 = prelims[:mid]; h2 = prelims[mid:]

h1_result = roi_analysis(h1, f"PRELIM half 1 (first {len(h1)} fights, {h1[0]['date'][:7]} to {h1[-1]['date'][:7]})")
h2_result = roi_analysis(h2, f"PRELIM half 2 (last {len(h2)} fights, {h2[0]['date'][:7]} to {h2[-1]['date'][:7]})")

if h1_result and h2_result:
    persists = h1_result['roi'] > 0 and h2_result['roi'] > 0
    print(f"\n  Both halves positive ROI: {'YES' if persists else 'NO'}")
    if not persists:
        print(f"  → Edge does NOT persist across temporal halves")

# ═══════════════════════════════════════════════════════════════════
# MULTIPLICITY
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("MULTIPLICITY ACKNOWLEDGMENT")
print(f"{'='*80}")

print(f"""
  This cell was selected from the crowd-vs-market analysis which tested:
  - 5 calibration buckets
  - 6 divergence cells (direction × fav/dog × card position)
  - 5 crowd-advantage pockets
  - 3 method contexts
  Total: ~19 implicit tests.

  At alpha=0.05 with 19 tests, expect ~1 false positive.
  Bonferroni threshold: 0.05/19 = {0.05/19:.4f}
""")

if prelim_result and prelim_result['excl']:
    # Compute p-value more precisely
    boot_prelim = []
    events = list(set(f['event'] for f in prelims))
    eb = defaultdict(list)
    for f in prelims: eb[f['event']].append(f)
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sp = sn = 0
        for e in se:
            for f in eb[e]: sp += f['profit']; sn += 1
        boot_prelim.append(sp / (sn * 100) if sn > 0 else 0)
    p_val = (np.array(boot_prelim) <= 0).mean()
    bonf_survives = p_val < 0.05/19

    print(f"  Prelim crowd-fav p-value: {p_val:.4f}")
    print(f"  Bonferroni-corrected (0.05/19={0.05/19:.4f}): {'SURVIVES' if bonf_survives else 'DOES NOT SURVIVE'}")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VERDICT")
print(f"{'='*80}")

conditions = []
if prelim_result:
    conditions.append(('CI excludes zero', prelim_result['excl']))
    conditions.append(('Survives Bonferroni', bonf_survives if prelim_result['excl'] else False))
    conditions.append(('Persists across halves', persists if h1_result and h2_result else False))

print(f"\n  Pre-committed conditions:")
for label, passed in conditions:
    print(f"    {label}: {'PASS' if passed else 'FAIL'}")

all_pass = all(p for _, p in conditions)
print(f"\n  All conditions met: {'YES' if all_pass else 'NO'}")
if all_pass:
    print(f"  → REAL POCKET: crowd prelim-favorite edge at consensus close survives")
    print(f"    correction and persistence. Worth forward paper-testing.")
else:
    failed = [l for l, p in conditions if not p]
    print(f"  → LAST NULL. Failed: {', '.join(failed)}.")
    print(f"    The crowd's prelim accuracy is priced by the consensus closing line.")
    print(f"    This was the final cell from a long search. File closed.")
