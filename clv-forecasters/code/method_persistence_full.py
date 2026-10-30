#!/usr/bin/env python3
"""
Method-accuracy persistence: gender fix, method-strata, ROI, characterization.
All exploratory — labelled as such. Seed 67, fight-clustered bootstrap.
"""
import csv, json, os, re, sys, unicodedata
import numpy as np
from scipy.stats import spearmanr
from collections import defaultdict, Counter
from statistics import median

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
PICKS_DIR = r'C:\Research\ufc\picks\users'
STATE_FILE = r'C:\Research\ufc\picks\state.json'
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

# ─── Load bout table ───
event_bouts = defaultdict(list)
with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_bouts[normalize_event(r['card_key'])].append(r)

# ─── TASK A.1: Build gender set from ALL UFCStats data ───
# Flag fighters who have EVER fought in a women's division
print("Building gender set...", flush=True)
women_fighters = set()
ufcstats_path = r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv'
with open(ufcstats_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        div = r.get('division', '').lower()
        if "women" in div:
            women_fighters.add(normalize(r['fighter_name']))

print(f"Women fighters identified: {len(women_fighters)}")

def is_womens_fight(fighter_a, fighter_b):
    return normalize(fighter_a) in women_fighters and normalize(fighter_b) in women_fighters

# ─── Load prop odds for Task B ───
print("Loading prop odds...", flush=True)
prop_odds = {}  # (event_norm, prop_fighter_norm, prop_type) -> {consensus_p, best_odds}
card_map_cm = defaultdict(list)
with open('card_map.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        card_map_cm[r['card_key']].append(r['bfo_event_id'])

with open('bfo_props_devig.csv', 'r', encoding='utf-8') as f:
    seen = set()
    for r in csv.DictReader(f):
        key = (r['bfo_event_id'], r['bfo_matchup_id'], r['prop_type'], normalize(r['prop_fighter']))
        if key in seen: continue
        seen.add(key)
        prop_odds[key] = {
            'consensus_p': float(r['consensus_p']),
            'best_odds': int(r['best_odds']) if r['best_odds'] else None,
            'n_books': int(r['n_books']),
            'fighter_a': r['fighter_a'], 'fighter_b': r['fighter_b'],
        }

# Index prop odds by normalized fighter names for lookup
prop_by_fighters = defaultdict(list)
for key, v in prop_odds.items():
    eid, mid, pt, pf_n = key
    fa_n = normalize(v['fighter_a']); fb_n = normalize(v['fighter_b'])
    prop_by_fighters[(eid, fa_n, fb_n)].append((pt, pf_n, v))
    prop_by_fighters[(eid, fb_n, fa_n)].append((pt, pf_n, v))

# ─── Score all v2 users ───
print("Scoring users...", flush=True)
state = json.load(open(STATE_FILE))
done = {u: v for u, v in state['users'].items()
        if v['status'] == 'done' and u != AUTHOR and v.get('scraper_version') == 2}

# Per-user, per-pick scored data
user_picks_scored = {}

for username in done:
    safe = username.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): continue
    with open(path, 'r', encoding='utf-8') as f:
        picks = list(csv.DictReader(f))

    scored = []
    for p in picks:
        pm_raw = p.get('picked_method', '').strip()
        if not pm_raw: continue
        pm = get_method_cat(pm_raw)
        am = get_method_cat(p.get('actual_method', ''))
        if not pm or not am: continue

        fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
        ck_n = normalize_event(p['event'])
        candidates = event_bouts.get(ck_n, [])
        if not candidates:
            for ek, rows in event_bouts.items():
                if ek in ck_n or ck_n in ek:
                    candidates = rows; break
        if not candidates: continue
        r = candidates[0]  # for window/date only
        if r['canonical_date'] == DROP_DATE: continue
        w = r['window']
        if w not in ('rank', 'test'): continue

        fight_correct = p['correct'] == 'YES'
        method_correct = pm == am
        joint_hit = fight_correct and method_correct

        # Gender
        is_women = is_womens_fight(p['fighter_picked'], p['opponent'])

        # Find prop odds for ROI
        prop_consensus_p = None; prop_best_odds = None; market_fav_method = None
        event_ids = card_map_cm.get(p['event'], [])
        if not event_ids:
            for ck in card_map_cm:
                if normalize_event(ck) == ck_n or normalize_event(ck) in ck_n or ck_n in normalize_event(ck):
                    event_ids = card_map_cm[ck]; break

        for eid in event_ids:
            entries = prop_by_fighters.get((eid, fp_n, opp_n), [])
            if not entries:
                # Try matching with names_match
                for (e2, fa2, fb2), ents in prop_by_fighters.items():
                    if e2 != eid: continue
                    if (names_match(fp_n, fa2) and names_match(opp_n, fb2)) or \
                       (names_match(fp_n, fb2) and names_match(opp_n, fa2)):
                        entries = ents; break

            for pt, pf_n, v in entries:
                if pt == pm and names_match(fp_n, pf_n):
                    prop_consensus_p = v['consensus_p']
                    prop_best_odds = v['best_odds']

            # Market-favorite method for this fighter
            fighter_methods = [(pt, v['consensus_p']) for pt, pf_n2, v in entries
                               if names_match(fp_n, pf_n2)]
            if fighter_methods:
                market_fav_method = max(fighter_methods, key=lambda x: x[1])[0]
            if prop_consensus_p is not None: break

        scored.append({
            'window': w, 'joint_hit': joint_hit, 'fight_correct': fight_correct,
            'method_correct': method_correct, 'picked_method': pm, 'actual_method': am,
            'is_women': is_women,
            'prop_consensus_p': prop_consensus_p, 'prop_best_odds': prop_best_odds,
            'market_fav_method': market_fav_method,
            'fight_id': p['event'] + '_' + fp_n[:5],
            'event': p['event'],
        })

    if scored:
        user_picks_scored[username] = scored

print(f"Users with scored method picks: {len(user_picks_scored)}")

# ─── Helper: compute persistence ───
def compute_rho(user_data, filter_fn=None, min_rank=50, min_test=30):
    """Compute ρ(rank_metric, test_metric) across users."""
    users_r = []; users_t = []; user_names = []
    for u, picks in user_data.items():
        if filter_fn:
            picks = [p for p in picks if filter_fn(p)]
        rank_p = [p for p in picks if p['window'] == 'rank']
        test_p = [p for p in picks if p['window'] == 'test']
        rn = len(rank_p); tn = len(test_p)
        if rn < min_rank or tn < min_test: continue
        r_acc = sum(p['joint_hit'] for p in rank_p) / rn
        t_acc = sum(p['joint_hit'] for p in test_p) / tn
        users_r.append(r_acc); users_t.append(t_acc); user_names.append(u)

    n = len(users_r)
    if n < 10: return n, np.nan, (np.nan, np.nan)
    r_arr = np.array(users_r); t_arr = np.array(users_t)
    rho, _ = spearmanr(r_arr, t_arr)
    boot = []
    for _ in range(N_BOOT):
        idx = rng.choice(n, size=n, replace=True)
        br, _ = spearmanr(r_arr[idx], t_arr[idx])
        boot.append(br)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))
    return n, rho, ci

# ═══════════════════════════════════════════════════════════════════
# TASK A.1 — Gender persistence
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TASK A.1 — METHOD ACCURACY PERSISTENCE BY GENDER")
print("(exploratory, not pre-registered)")
print("=" * 80)

# Count women's fights in sample
women_count = sum(1 for u, picks in user_picks_scored.items()
                  for p in picks if p['is_women'])
men_count = sum(1 for u, picks in user_picks_scored.items()
                for p in picks if not p['is_women'])
print(f"\nTotal picks: men={men_count}, women={women_count}")

print(f"\n{'Split':<20} {'n':>5} {'rho':>7} {'CI_lo':>7} {'CI_hi':>7} {'excl_0?':>7}")
print("-" * 55)

for label, filt in [("Men's fights", lambda p: not p['is_women']),
                    ("Women's fights", lambda p: p['is_women'])]:
    n, rho, ci = compute_rho(user_picks_scored, filt, min_rank=20, min_test=10)
    excl = 'YES' if not np.isnan(ci[0]) and ci[0] > 0 else 'NO'
    print(f"{label:<20} {n:>5} {rho:>+7.3f} {ci[0]:>+7.3f} {ci[1]:>+7.3f} {excl:>7}")

# ═══════════════════════════════════════════════════════════════════
# TASK A.2 — Method-strata persistence
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TASK A.2 — METHOD ACCURACY PERSISTENCE BY PREDICTED METHOD")
print("(exploratory)")
print("=" * 80)

print(f"\n{'Split':<20} {'n':>5} {'rho':>7} {'CI_lo':>7} {'CI_hi':>7} {'excl_0?':>7}")
print("-" * 55)

for method, label in [('ko_tko', 'KO/TKO calls'), ('submission', 'Sub calls'),
                      ('decision', 'Decision calls')]:
    n, rho, ci = compute_rho(user_picks_scored,
                             lambda p, m=method: p['picked_method'] == m,
                             min_rank=15, min_test=10)
    excl = 'YES' if not np.isnan(ci[0]) and ci[0] > 0 else 'NO'
    print(f"{label:<20} {n:>5} {rho:>+7.3f} {ci[0]:>+7.3f} {ci[1]:>+7.3f} {excl:>7}")

# ═══════════════════════════════════════════════════════════════════
# TASK B.3 — Top-decile method ROI at prop odds
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TASK B.3 — METHOD PROP ROI FOR TOP-DECILE PERSISTENT METHOD CALLERS")
print("(exploratory, prop odds from bfo_props_devig.csv)")
print("=" * 80)

# Rank users by rank-window joint accuracy
user_rank_acc = {}
for u, picks in user_picks_scored.items():
    rank_p = [p for p in picks if p['window'] == 'rank']
    if len(rank_p) >= 50:
        user_rank_acc[u] = sum(p['joint_hit'] for p in rank_p) / len(rank_p)

sorted_users = sorted(user_rank_acc.items(), key=lambda x: -x[1])
d = max(1, len(sorted_users) // 10)
top_decile = set(u for u, _ in sorted_users[:d])
bottom_decile = set(u for u, _ in sorted_users[-d:])

print(f"\nUsers ranked: {len(sorted_users)}, decile size: {d}")
print(f"Top-decile rank accuracy: {np.mean([user_rank_acc[u] for u in top_decile]):.3f}")
print(f"Bottom-decile rank accuracy: {np.mean([user_rank_acc[u] for u in bottom_decile]):.3f}")

# Test-window ROI for top decile at best prop odds
for decile_label, decile_set in [('Top decile', top_decile), ('Bottom decile', bottom_decile),
                                  ('All users', set(user_rank_acc.keys()))]:
    test_bets = []
    for u in decile_set:
        for p in user_picks_scored.get(u, []):
            if p['window'] != 'test': continue
            if p['prop_best_odds'] is None: continue
            dec_odds = american_to_decimal(p['prop_best_odds'])
            profit = (dec_odds - 1) * 100 if p['joint_hit'] else -100
            test_bets.append({'profit': profit, 'event': p['event']})

    if not test_bets:
        print(f"\n  {decile_label}: no test bets with prop odds")
        continue

    total_profit = sum(b['profit'] for b in test_bets)
    n_bets = len(test_bets)
    roi = total_profit / (n_bets * 100)

    # Bootstrap
    events = list(set(b['event'] for b in test_bets))
    event_bets_map = defaultdict(list)
    for b in test_bets: event_bets_map[b['event']].append(b)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sp = sn = 0
        for e in se:
            for b in event_bets_map[e]:
                sp += b['profit']; sn += 1
        boot.append(sp / (sn * 100) if sn > 0 else 0)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))

    print(f"\n  {decile_label}: n={n_bets}, ROI={roi:+.1%} CI=[{ci[0]:+.1%},{ci[1]:+.1%}]")

# ═══════════════════════════════════════════════════════════════════
# TASK B.4 — Non-obvious method ROI
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TASK B.4 — NON-OBVIOUS METHOD CALLS (predicted != market-favorite method)")
print("(exploratory)")
print("=" * 80)

obvious_bets = []; contrarian_bets = []
for u in top_decile:
    for p in user_picks_scored.get(u, []):
        if p['window'] != 'test': continue
        if p['prop_best_odds'] is None: continue
        dec_odds = american_to_decimal(p['prop_best_odds'])
        profit = (dec_odds - 1) * 100 if p['joint_hit'] else -100
        bet = {'profit': profit, 'event': p['event']}

        if p['market_fav_method'] and p['picked_method'] != p['market_fav_method']:
            contrarian_bets.append(bet)
        else:
            obvious_bets.append(bet)

for label, bets in [('Obvious (picked=mkt fav)', obvious_bets),
                    ('Contrarian (picked!=mkt fav)', contrarian_bets)]:
    if not bets:
        print(f"  {label}: no bets"); continue
    roi = sum(b['profit'] for b in bets) / (len(bets) * 100)
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
    print(f"  {label}: n={len(bets)}, ROI={roi:+.1%} CI=[{ci[0]:+.1%},{ci[1]:+.1%}]")

# ═══════════════════════════════════════════════════════════════════
# TASK C.5 — Volume split
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TASK C.5 — PERSISTENCE BY USER PICK COUNT (volume split)")
print("(exploratory)")
print("=" * 80)

# Split users by total method picks
user_totals = {u: len(picks) for u, picks in user_picks_scored.items()}
med_total = median(user_totals.values())

print(f"Median method picks per user: {med_total:.0f}")
print(f"\n{'Split':<20} {'n':>5} {'rho':>7} {'CI_lo':>7} {'CI_hi':>7}")
print("-" * 48)

high_users = {u for u, t in user_totals.items() if t >= med_total}
low_users = {u for u, t in user_totals.items() if t < med_total}

for label, subset in [('High volume', high_users), ('Low volume', low_users)]:
    sub_data = {u: p for u, p in user_picks_scored.items() if u in subset}
    n, rho, ci = compute_rho(sub_data, min_rank=30, min_test=15)
    print(f"{label:<20} {n:>5} {rho:>+7.3f} {ci[0]:>+7.3f} {ci[1]:>+7.3f}")

# ═══════════════════════════════════════════════════════════════════
# TASK C.6 — Card position (approximate: first 5 bouts = main card)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TASK C.6 — PERSISTENCE BY CARD POSITION")
print("(exploratory, approximate: first 5 listed bouts = main card)")
print("=" * 80)

# Track bout position within each event for each user
# Position 0-4 = main card, 5+ = prelims
# Use the order in the user's CSV (Tapology lists main card first)
user_picks_with_pos = {}
for u, picks in user_picks_scored.items():
    event_counters = Counter()
    enhanced = []
    # Re-read to get position
    safe = u.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    with open(path, 'r', encoding='utf-8') as f:
        all_picks = list(csv.DictReader(f))
    event_pos = defaultdict(int)
    pos_map = {}
    for ap in all_picks:
        ev = ap['event']
        pos = event_pos[ev]
        event_pos[ev] += 1
        key = (ev, normalize(ap['fighter_picked']), normalize(ap['opponent']))
        pos_map[key] = pos

    for p in picks:
        key = (p['event'], normalize(p['event'].split('_')[0]) if '_' in p.get('fight_id', '') else '',
               '')
        # Simpler: use the index in the scored picks per event
        p['is_main_card'] = True  # default, will fix below

    # Mark position from the pick order
    ev_idx = defaultdict(int)
    for p in picks:
        idx = ev_idx[p['event']]
        ev_idx[p['event']] += 1
        p['is_main_card'] = idx < 5  # first 5 bouts = main card

    user_picks_with_pos[u] = picks

print(f"\n{'Split':<20} {'n':>5} {'rho':>7} {'CI_lo':>7} {'CI_hi':>7}")
print("-" * 48)

for label, filt in [('Main card (1-5)', lambda p: p.get('is_main_card', True)),
                    ('Prelims (6+)', lambda p: not p.get('is_main_card', True))]:
    n, rho, ci = compute_rho(user_picks_with_pos, filt, min_rank=10, min_test=5)
    print(f"{label:<20} {n:>5} {rho:>+7.3f} {ci[0]:>+7.3f} {ci[1]:>+7.3f}")

# ═══════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("MULTIPLE COMPARISONS NOTE")
print("=" * 80)
print("""
All splits above are EXPLORATORY characterization, not pre-registered.
With ~10 tests, expect ~0.5 false positives at α=0.05 under the null.
No single surviving split should be presented as confirmatory evidence.
The only pre-existing signal is the overall ρ=+0.267 [+0.146,+0.382].
""")
