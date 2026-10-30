#!/usr/bin/env python3
"""
Exploratory: KO-method × card-position ROI for top-decile persistent KO-callers.
Non-pre-registered. Seed 67, fight-clustered bootstrap.
"""
import csv, json, os, re, sys, unicodedata
import numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
PICKS_DIR = r'C:\Research\ufc\picks\users'
AUTHOR = 'Ezoteryka'
DROP_DATE = '2025-08-09'

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
def normalize(name):
    return re.sub(r'[^\w\s]', '', strip_accents(name).strip().lower()).strip()
def normalize_event(name):
    return re.sub(r'\s+\d{1}$', '', normalize(name))
def last_name(name):
    parts = normalize(name).split()
    return parts[-1] if parts else ''
def names_match(a, b):
    na, nb = normalize(a), normalize(b)
    if na == nb: return True
    la, lb = last_name(a), last_name(b)
    if la == lb and len(na) > 0 and len(nb) > 0 and na[0] == nb[0]: return True
    if len(na) > 4 and len(nb) > 4 and (na in nb or nb in na): return True
    return False
def american_to_decimal(odds):
    odds = int(odds)
    return 1 + odds / 100 if odds > 0 else 1 + 100 / abs(odds)
def get_method_cat(s):
    s = s.strip().lower()
    if 'ko' in s or 'tko' in s: return 'ko_tko'
    if 'submission' in s or 'sub' in s: return 'submission'
    if 'decision' in s or 'dec' in s: return 'decision'
    return None

rng = np.random.RandomState(SEED)

# Load bout table
event_bouts = defaultdict(list)
with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_bouts[normalize_event(r['card_key'])].append(r)

# Load prop odds
card_map_cm = defaultdict(list)
with open('card_map.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        card_map_cm[r['card_key']].append(r['bfo_event_id'])

prop_by_fighters = defaultdict(list)
with open('bfo_props_devig.csv', 'r', encoding='utf-8') as f:
    seen = set()
    for r in csv.DictReader(f):
        key = (r['bfo_event_id'], r['bfo_matchup_id'], r['prop_type'], normalize(r['prop_fighter']))
        if key in seen: continue
        seen.add(key)
        eid = r['bfo_event_id']
        fa_n = normalize(r['fighter_a']); fb_n = normalize(r['fighter_b'])
        entry = (r['prop_type'], normalize(r['prop_fighter']), {
            'consensus_p': float(r['consensus_p']),
            'best_odds': int(r['best_odds']) if r['best_odds'] else None,
        })
        prop_by_fighters[(eid, fa_n, fb_n)].append(entry)
        prop_by_fighters[(eid, fb_n, fa_n)].append(entry)

# Load users
state = json.load(open(r'C:\Research\ufc\picks\state.json'))
done = {u: v for u, v in state['users'].items()
        if v['status'] == 'done' and u != AUTHOR and v.get('scraper_version') == 2}

print(f"Scoring {len(done)} v2 users, KO/TKO calls only...", flush=True)

# Score each user's KO calls with card position
user_ko_picks = {}

for username in done:
    safe = username.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): continue
    with open(path, 'r', encoding='utf-8') as f:
        picks = list(csv.DictReader(f))

    ko_picks = []
    event_bout_idx = defaultdict(int)  # track position within event

    for p in picks:
        ev = p['event']
        bout_pos = event_bout_idx[ev]
        event_bout_idx[ev] += 1

        pm_raw = p.get('picked_method', '').strip()
        if not pm_raw: continue
        pm = get_method_cat(pm_raw)
        if pm != 'ko_tko': continue

        am = get_method_cat(p.get('actual_method', ''))
        if not am: continue

        fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
        ck_n = normalize_event(ev)
        candidates = event_bouts.get(ck_n, [])
        if not candidates:
            for ek, rows in event_bouts.items():
                if ek in ck_n or ck_n in ek:
                    candidates = rows; break
        if not candidates: continue
        r = candidates[0]
        if r['canonical_date'] == DROP_DATE: continue
        w = r['window']
        if w not in ('rank', 'test'): continue

        fight_correct = p['correct'] == 'YES'
        method_correct = am == 'ko_tko'
        joint_hit = fight_correct and method_correct

        # Card position: bout_pos 0-4 = main card, 5+ = prelims
        is_main = bout_pos < 5

        # Find prop odds
        prop_best_odds = None
        event_ids = card_map_cm.get(ev, [])
        if not event_ids:
            for ck in card_map_cm:
                if normalize_event(ck) == ck_n or normalize_event(ck) in ck_n or ck_n in normalize_event(ck):
                    event_ids = card_map_cm[ck]; break

        for eid in event_ids:
            entries = prop_by_fighters.get((eid, fp_n, opp_n), [])
            if not entries:
                for (e2, fa2, fb2), ents in prop_by_fighters.items():
                    if e2 != eid: continue
                    if (names_match(fp_n, fa2) and names_match(opp_n, fb2)) or \
                       (names_match(fp_n, fb2) and names_match(opp_n, fa2)):
                        entries = ents; break
            for pt, pf_n, v in entries:
                if pt == 'ko_tko' and names_match(fp_n, pf_n):
                    prop_best_odds = v['best_odds']
                    break
            if prop_best_odds is not None: break

        ko_picks.append({
            'window': w, 'joint_hit': joint_hit,
            'prop_best_odds': prop_best_odds,
            'is_main': is_main, 'event': ev,
        })

    if ko_picks:
        user_ko_picks[username] = ko_picks

print(f"Users with KO picks: {len(user_ko_picks)}")

# Rank users by rank-window KO joint accuracy
user_rank_ko_acc = {}
for u, picks in user_ko_picks.items():
    rank_p = [p for p in picks if p['window'] == 'rank']
    if len(rank_p) >= 20:
        user_rank_ko_acc[u] = sum(p['joint_hit'] for p in rank_p) / len(rank_p)

sorted_users = sorted(user_rank_ko_acc.items(), key=lambda x: -x[1])
d = max(1, len(sorted_users) // 10)
top_decile = set(u for u, _ in sorted_users[:d])

print(f"Users ranked by KO accuracy: {len(sorted_users)}, decile: {d}")
print(f"Top-decile mean rank KO acc: {np.mean([user_rank_ko_acc[u] for u in top_decile]):.3f}")

# ─── ROI computation ───
def compute_roi(users_set, filter_fn, label):
    bets = []
    for u in users_set:
        for p in user_ko_picks.get(u, []):
            if p['window'] != 'test': continue
            if not filter_fn(p): continue
            if p['prop_best_odds'] is None: continue
            dec = american_to_decimal(p['prop_best_odds'])
            profit = (dec - 1) * 100 if p['joint_hit'] else -100
            bets.append({'profit': profit, 'event': p['event']})

    n = len(bets)
    if n == 0:
        return n, np.nan, (np.nan, np.nan), np.nan

    total = sum(b['profit'] for b in bets)
    roi = total / (n * 100)

    # Fight-clustered bootstrap null
    events = list(set(b['event'] for b in bets))
    eb = defaultdict(list)
    for b in bets: eb[b['event']].append(b)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sp = sn = 0
        for e in se:
            for b in eb[e]: sp += b['profit']; sn += 1
        boot.append(sp / (sn * 100) if sn > 0 else 0)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))
    null_p = (np.array(boot) >= roi).mean()  # one-sided

    return n, roi, ci, null_p

# ─── Results ───
print("\n" + "=" * 80)
print("KO/TKO METHOD-PROP ROI × CARD POSITION")
print("Exploratory, non-pre-registered. CI excludes zero = signal; else = null.")
print("=" * 80)

all_users = set(user_rank_ko_acc.keys())
filters = [
    ('ALL cards', lambda p: True),
    ('MAIN CARD (1-5)', lambda p: p['is_main']),
    ('PRELIMS (6+)', lambda p: not p['is_main']),
]

print(f"\n{'':>30} | {'TOP DECILE':>40} | {'ALL USERS':>40}")
print(f"{'Cell':<30} | {'n':>5} {'ROI':>7} {'CI_lo':>7} {'CI_hi':>7} {'<150?':>5} | "
      f"{'n':>5} {'ROI':>7} {'CI_lo':>7} {'CI_hi':>7} {'<150?':>5}")
print("-" * 105)

for label, filt in filters:
    n_top, roi_top, ci_top, _ = compute_roi(top_decile, filt, f'Top {label}')
    n_all, roi_all, ci_all, _ = compute_roi(all_users, filt, f'All {label}')

    flag_top = 'FLAG' if n_top < 150 else ''
    flag_all = 'FLAG' if n_all < 150 else ''

    def fmt(roi, ci):
        if np.isnan(roi): return '   —      —      —  '
        return f'{roi:>+6.1%} {ci[0]:>+6.1%} {ci[1]:>+6.1%}'

    print(f"{label:<30} | {n_top:>5} {fmt(roi_top, ci_top)} {flag_top:>5} | "
          f"{n_all:>5} {fmt(roi_all, ci_all)} {flag_all:>5}")

# Interpretation
print(f"\n{'='*80}")
print("INTERPRETATION")
print(f"{'='*80}")
for label, filt in filters:
    n_top, roi_top, ci_top, _ = compute_roi(top_decile, filt, '')
    if n_top < 150:
        print(f"  {label}, top decile: n={n_top} < 150 → UNDERPOWERED, do not interpret")
    elif ci_top[0] > 0:
        print(f"  {label}, top decile: CI excludes zero → SIGNAL (exploratory)")
    else:
        print(f"  {label}, top decile: CI includes zero → NULL")
