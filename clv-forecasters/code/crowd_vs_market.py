#!/usr/bin/env python3
"""Crowd vs Market vs Me: calibration, divergence, edge analysis."""
import csv, json, os, re, sys, unicodedata, math
import numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
SEED = 67; N_BOOT = 5000
rng = np.random.RandomState(SEED)
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

# Load bout table + odds
event_bouts = defaultdict(list)
with open('ezoteryka_scored.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_bouts[normalize_event(r['card_key'])].append(r)

# Division map
division_map = {}
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        fa = normalize(r['fighter_name']); fb = normalize(r['fighter_name_opp'])
        div = r.get('division','').strip()
        if div: division_map[(fa,fb)] = div; division_map[(fb,fa)] = div

# Build crowd consensus from all users
state = json.load(open(r'C:\Research\ufc\picks\state.json'))
all_users = [u for u, v in state['users'].items() if v['status'] == 'done']

print("Building crowd consensus...", flush=True)
bout_crowd = defaultdict(lambda: {'total': 0, 'picks': defaultdict(int), 'methods': defaultdict(int)})

for u in all_users:
    safe = u.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): continue
    with open(path, encoding='utf-8') as f:
        for p in csv.DictReader(f):
            fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
            ev_n = normalize_event(p['event'])
            fighters = tuple(sorted([fp_n, opp_n]))
            key = (ev_n, fighters[0], fighters[1])
            bout_crowd[key]['total'] += 1
            bout_crowd[key]['picks'][fp_n] += 1

# Inversions for author
INVERSIONS = {
    (normalize_event('UFC 326: Holloway vs. Oliveira 2'), 'sumudaerji'),
    (normalize_event('UFC Fight Night: Walker vs. Zhang'), 'sumudaerji'),
    (normalize_event('UFC Fight Night: Song vs. Figueiredo'), 'yadong song'),
}

# Build fight-level dataset: crowd%, market%, outcome, my pick
print("Joining crowd + market + outcomes...", flush=True)

# Use Ezoteryka's picks as the bout list (523 bouts with odds)
with open(os.path.join(PICKS_DIR, 'Ezoteryka.csv'), encoding='utf-8') as f:
    my_picks = list(csv.DictReader(f))

fights = []
event_bout_idx = defaultdict(int)

for p in my_picks:
    ev = p['event']; bout_pos = event_bout_idx[ev]; event_bout_idx[ev] += 1
    fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
    ck_n = normalize_event(ev)

    candidates = event_bouts.get(ck_n, [])
    if not candidates:
        for ek, rows in event_bouts.items():
            if ek in ck_n or ck_n in ek: candidates = rows; break
    if not candidates: continue

    r = None
    for row in candidates:
        parts = row['bout'].split(' vs ')
        if len(parts) != 2: continue
        fa_n, fb_n = normalize(parts[0]), normalize(parts[1])
        if (names_match(fp_n, fa_n) and names_match(opp_n, fb_n)) or \
           (names_match(fp_n, fb_n) and names_match(opp_n, fa_n)):
            r = row; break
    if not r: continue

    # Market prob for fighter I picked
    if names_match(fp_n, normalize(r['picked_fighter'])):
        mkt_p = float(r['p_fair_picked'])
    else:
        mkt_p = 1 - float(r['p_fair_picked'])

    # Apply inversions
    for inv_ck, inv_fn in INVERSIONS:
        if inv_ck == ck_n and names_match(inv_fn, fp_n):
            mkt_p = 1 - mkt_p; break

    # Crowd consensus for fighter I picked
    fighters = tuple(sorted([fp_n, opp_n]))
    bc = bout_crowd.get((ck_n, fighters[0], fighters[1]))
    if not bc or bc['total'] < 50: continue
    crowd_for_me = bc['picks'].get(fp_n, 0) / bc['total']

    correct = p['correct'] == 'YES'
    actual_method = get_method_cat(p.get('actual_method', ''))
    card_pos = 'Main event' if bout_pos == 0 else ('Main card' if bout_pos < 5 else 'Prelims')

    fights.append({
        'fp': p['fighter_picked'], 'opp': p['opponent'], 'event': ev,
        'correct': correct, 'outcome': 1 if correct else 0,
        'mkt_p': mkt_p,  # market prob for my fighter
        'crowd_p': crowd_for_me,  # crowd % who picked my fighter
        'card_pos': card_pos, 'actual_method': actual_method,
        'fav_dog': 'fav' if mkt_p >= 0.5 else 'dog',
    })

print(f"Fights with crowd+market+outcome: {len(fights)}")

# ═══════════════════════════════════════════════════════════════════
# 1. AGGREGATE CALIBRATION
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("1. CALIBRATION: crowd vs market")
print(f"{'='*80}")

# For calibration, need to compare prediction (crowd or market) to outcome
# at the FIGHT level, not at my-pick level
# Convert my-pick-level to fight level: prob of fighter_a winning
# Since I have crowd_p and mkt_p for "my fighter", I need to be careful
# But for calibration bins, the direction doesn't matter — we can bin
# by the HIGHER of the two (the favorite's prob)

cal_buckets = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.01)]

print(f"\n  {'Bucket':<12} {'n':>4} | {'Crowd pred':>11} {'Crowd hit':>10} {'Crowd err':>10} | {'Mkt pred':>9} {'Mkt hit':>8} {'Mkt err':>9}")
print("  " + "-" * 85)

crowd_total_err = 0; mkt_total_err = 0; n_total = 0

for lo, hi in cal_buckets:
    # Bin by MARKET prob of the favorite (my pick's mkt_p if fav, else 1-mkt_p)
    sub = [f for f in fights if lo <= max(f['mkt_p'], 1-f['mkt_p']) < hi]
    if not sub: continue

    # For each fight: crowd_p and mkt_p are for "my fighter"
    # Outcome = 1 if my fighter won
    # But for calibration, we want favorite-side
    cal_fights = []
    for f in sub:
        if f['mkt_p'] >= 0.5:
            # I picked the favorite
            cal_fights.append({'crowd': f['crowd_p'], 'mkt': f['mkt_p'], 'outcome': f['outcome']})
        else:
            # I picked the dog — flip to fav perspective
            cal_fights.append({'crowd': 1-f['crowd_p'], 'mkt': 1-f['mkt_p'], 'outcome': 1-f['outcome']})

    n = len(cal_fights)
    crowd_pred = np.mean([c['crowd'] for c in cal_fights])
    mkt_pred = np.mean([c['mkt'] for c in cal_fights])
    hit_rate = np.mean([c['outcome'] for c in cal_fights])
    crowd_err = abs(crowd_pred - hit_rate)
    mkt_err = abs(mkt_pred - hit_rate)

    crowd_total_err += crowd_err * n; mkt_total_err += mkt_err * n; n_total += n

    better = 'CROWD' if crowd_err < mkt_err else 'MKT' if mkt_err < crowd_err else 'TIE'
    print(f"  {lo:.0%}-{hi:.0%}       {n:>4} | {crowd_pred:>10.1%} {hit_rate:>9.1%} {crowd_err:>9.1%} | "
          f"{mkt_pred:>8.1%} {hit_rate:>7.1%} {mkt_err:>8.1%}  {better}")

print(f"\n  Overall calibration error: Crowd={crowd_total_err/n_total:.1%}, Market={mkt_total_err/n_total:.1%}")

# Brier scores
crowd_brier = np.mean([(f['crowd_p'] - f['outcome'])**2 for f in fights])
mkt_brier = np.mean([(f['mkt_p'] - f['outcome'])**2 for f in fights])
print(f"  Brier score: Crowd={crowd_brier:.4f}, Market={mkt_brier:.4f} ({'Market wins' if mkt_brier < crowd_brier else 'Crowd wins'})")

# ═══════════════════════════════════════════════════════════════════
# 2. DIVERGENCE CELLS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("2. DIVERGENCE: where crowd disagrees most with market, who's right?")
print(f"{'='*80}")

# Divergence = crowd_p - mkt_p (for my fighter)
divs = np.array([f['crowd_p'] - f['mkt_p'] for f in fights])
print(f"\n  Crowd-market divergence: mean={divs.mean():+.1%}, SD={divs.std():.1%}, "
      f"|div|>5pp: {(np.abs(divs) > 0.05).sum()}, |div|>10pp: {(np.abs(divs) > 0.10).sum()}")

# Who's right when they disagree?
print(f"\n  When crowd and market disagree by >5pp:")
print(f"  {'Cell':<30} {'n':>4} {'Crowd closer':>13} {'Mkt closer':>11} {'Winner'}")
print("  " + "-" * 65)

for label, filt in [
    ('Crowd says MORE (>5pp)', lambda f: f['crowd_p'] - f['mkt_p'] > 0.05),
    ('Crowd says LESS (<-5pp)', lambda f: f['crowd_p'] - f['mkt_p'] < -0.05),
    ('Heavy fav (mkt>70%)', lambda f: f['mkt_p'] > 0.7 and abs(f['crowd_p']-f['mkt_p']) > 0.05),
    ('Dog pick (mkt<45%)', lambda f: f['mkt_p'] < 0.45 and abs(f['crowd_p']-f['mkt_p']) > 0.05),
    ('Main events', lambda f: f['card_pos'] == 'Main event'),
    ('Prelims', lambda f: f['card_pos'] == 'Prelims'),
]:
    sub = [f for f in fights if filt(f)]
    if len(sub) < 10: continue
    crowd_closer = sum(1 for f in sub if abs(f['crowd_p'] - f['outcome']) < abs(f['mkt_p'] - f['outcome']))
    mkt_closer = sum(1 for f in sub if abs(f['mkt_p'] - f['outcome']) < abs(f['crowd_p'] - f['outcome']))
    winner = 'CROWD' if crowd_closer > mkt_closer else 'MKT'
    print(f"  {label:<30} {len(sub):>4} {crowd_closer:>13} {mkt_closer:>11} {winner}")

# Method context
print(f"\n  By actual method (when crowd-market diverge >5pp):")
for method in ['KO/TKO', 'Submission', 'Decision']:
    sub = [f for f in fights if f['actual_method'] == method and abs(f['crowd_p']-f['mkt_p']) > 0.05]
    if len(sub) < 5: continue
    crowd_closer = sum(1 for f in sub if abs(f['crowd_p']-f['outcome']) < abs(f['mkt_p']-f['outcome']))
    mkt_closer = sum(1 for f in sub if abs(f['mkt_p']-f['outcome']) < abs(f['crowd_p']-f['outcome']))
    print(f"    {method:<15} n={len(sub):>3}  crowd_closer={crowd_closer}  mkt_closer={mkt_closer}")

# ═══════════════════════════════════════════════════════════════════
# 3. ANY CROWD EDGE?
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("3. IS THERE ANY POCKET WHERE CROWD BEATS MARKET?")
print(f"{'='*80}")

# For each fight, crowd_error = |crowd_p - outcome|, mkt_error = |mkt_p - outcome|
# crowd_advantage = mkt_error - crowd_error (positive = crowd wins)
advantages = [abs(f['mkt_p'] - f['outcome']) - abs(f['crowd_p'] - f['outcome']) for f in fights]
mean_adv = np.mean(advantages)

# Bootstrap CI
events = list(set(f['event'] for f in fights))
eb = defaultdict(list)
for i, f in enumerate(fights): eb[f['event']].append(advantages[i])
boot = []
for _ in range(N_BOOT):
    se = rng.choice(events, size=len(events), replace=True)
    ba = []
    for e in se: ba.extend(eb[e])
    boot.append(np.mean(ba))
ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))

print(f"\n  Mean crowd advantage (mkt_err - crowd_err): {mean_adv:+.4f}")
print(f"  CI: [{ci[0]:+.4f}, {ci[1]:+.4f}]")
print(f"  CI excludes zero: {'YES — crowd has edge' if ci[0] > 0 else 'NO — market dominates' if ci[1] < 0 else 'INCLUDES ZERO'}")

# Check specific pockets
for label, filt in [
    ('Main events only', lambda f: f['card_pos'] == 'Main event'),
    ('Prelims only', lambda f: f['card_pos'] == 'Prelims'),
    ('Heavy favs (>75%)', lambda f: max(f['mkt_p'], 1-f['mkt_p']) > 0.75),
    ('Coinflips (45-55%)', lambda f: 0.45 <= f['mkt_p'] <= 0.55),
    ('Dogs (<40%)', lambda f: f['mkt_p'] < 0.40),
]:
    sub_adv = [abs(f['mkt_p']-f['outcome'])-abs(f['crowd_p']-f['outcome']) for f in fights if filt(f)]
    if len(sub_adv) < 15: continue
    m = np.mean(sub_adv)
    print(f"    {label:<25} n={len(sub_adv):>3} crowd_adv={m:+.4f} {'*crowd*' if m > 0.01 else 'market'}")

# ═══════════════════════════════════════════════════════════════════
# 4. ME vs CROWD vs MARKET
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("4. ME vs CROWD vs MARKET (three-way)")
print(f"{'='*80}")

# My pick = 1/0 (correct or not)
# Crowd prediction = crowd_p (prob of my fighter)
# Market prediction = mkt_p (prob of my fighter)

my_brier = np.mean([(1 - f['outcome'])**2 if True else (0 - f['outcome'])**2 for f in fights])
# Actually: my implicit prediction is always 1 for my fighter, so
# my_brier = mean((1 - outcome)^2) = mean of 0 if correct, 1 if wrong = 1 - accuracy
my_acc = np.mean([f['outcome'] for f in fights])
my_brier_proper = 1 - my_acc  # simplified since my "prob" is always 1

print(f"\n  Overall accuracy: Me={my_acc:.1%}, Crowd={np.mean([f['crowd_p'] for f in fights]):.1%} (mean consensus)")
print(f"  Brier: Crowd={crowd_brier:.4f}, Market={mkt_brier:.4f}")

# When I DISAGREE with crowd (I'm on the minority side)
disagree_crowd = [f for f in fights if f['crowd_p'] < 0.5]  # crowd favored my opponent
agree_crowd = [f for f in fights if f['crowd_p'] >= 0.5]  # crowd agreed with me

print(f"\n  When I AGREE with crowd (crowd >= 50% for my fighter): n={len(agree_crowd)}")
print(f"    My accuracy: {np.mean([f['outcome'] for f in agree_crowd]):.1%}")
print(f"  When I DISAGREE with crowd (crowd < 50% for my fighter): n={len(disagree_crowd)}")
if disagree_crowd:
    print(f"    My accuracy: {np.mean([f['outcome'] for f in disagree_crowd]):.1%}")
    print(f"    → When I go against the crowd, I win {np.mean([f['outcome'] for f in disagree_crowd]):.0%} of the time")

# When crowd DISAGREES with market
crowd_overmarket = [f for f in fights if f['crowd_p'] > f['mkt_p'] + 0.05]
crowd_undermarket = [f for f in fights if f['crowd_p'] < f['mkt_p'] - 0.05]

print(f"\n  When crowd likes my fighter MORE than market (+5pp):")
if crowd_overmarket:
    print(f"    n={len(crowd_overmarket)}, my accuracy: {np.mean([f['outcome'] for f in crowd_overmarket]):.1%}, "
          f"mkt implied: {np.mean([f['mkt_p'] for f in crowd_overmarket]):.1%}")
print(f"  When crowd likes my fighter LESS than market (-5pp):")
if crowd_undermarket:
    print(f"    n={len(crowd_undermarket)}, my accuracy: {np.mean([f['outcome'] for f in crowd_undermarket]):.1%}, "
          f"mkt implied: {np.mean([f['mkt_p'] for f in crowd_undermarket]):.1%}")

# Am I better when I'm contrarian?
if disagree_crowd:
    dc_acc = np.mean([f['outcome'] for f in disagree_crowd])
    ac_acc = np.mean([f['outcome'] for f in agree_crowd])
    print(f"\n  Contrarian accuracy: {dc_acc:.1%} (n={len(disagree_crowd)}) "
          f"vs consensus accuracy: {ac_acc:.1%} (n={len(agree_crowd)})")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VERDICT")
print(f"{'='*80}")
