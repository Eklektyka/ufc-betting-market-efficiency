#!/usr/bin/env python3
"""
Persistence across splits: methods, gender, fav/dog.
Uses the same scoring pipeline as the main study.
Seed 67, 5000 bootstrap draws, fight-clustered.
"""
import csv, json, os, re, sys, unicodedata
import numpy as np
from scipy.stats import spearmanr
from collections import defaultdict
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

# ─── Load bout table with metadata ───
event_bouts = defaultdict(list)
all_bouts = []
with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_bouts[normalize_event(r['card_key'])].append(r)
        all_bouts.append(r)

# ─── Load division data from ufcstats ───
division_by_bout = {}  # (normalized fighter_a, normalized fighter_b) -> division
ufcstats_path = r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv'
with open(ufcstats_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        fa = normalize(r['fighter_name'])
        fb = normalize(r['fighter_name_opp'])
        div = r.get('division', '').strip()
        if div:
            division_by_bout[(fa, fb)] = div
            division_by_bout[(fb, fa)] = div

def is_womens(div):
    return "women" in div.lower() if div else False

def get_method_cat(method_str):
    m = method_str.strip().lower()
    if 'ko' in m or 'tko' in m: return 'ko_tko'
    if 'submission' in m: return 'submission'
    if 'decision' in m: return 'decision'
    return None

# ─── Score all users ───
state = json.load(open(STATE_FILE))
done = {u: v for u, v in state['users'].items() if v['status'] == 'done' and u != AUTHOR}

print(f"Scoring {len(done)} users...", flush=True)

user_splits = {}  # user -> {split_name -> {rank_clv, test_clv, rank_n, test_n}}

for username in done:
    safe = username.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): continue

    with open(path, 'r', encoding='utf-8') as f:
        picks = list(csv.DictReader(f))

    splits = defaultdict(lambda: {'rank_clv': [], 'test_clv': []})

    for p in picks:
        fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
        ck_n = normalize_event(p['event'])
        candidates = event_bouts.get(ck_n, [])
        if not candidates:
            for ek, rows in event_bouts.items():
                if ek in ck_n or ck_n in ek:
                    candidates = rows; break
        r = None
        for row in candidates:
            parts = row['bout'].split(' vs ')
            if len(parts) != 2: continue
            fa_n, fb_n = normalize(parts[0]), normalize(parts[1])
            if (names_match(fp_n, fa_n) and names_match(opp_n, fb_n)) or \
               (names_match(fp_n, fb_n) and names_match(opp_n, fa_n)):
                r = row; break
        if not r: continue
        if r['canonical_date'] == DROP_DATE: continue

        ezo_picked_n = normalize(r['picked_fighter'])
        if names_match(fp_n, ezo_picked_n):
            p_fair = float(r['p_fair_picked'])
        else:
            p_fair = 1 - float(r['p_fair_picked'])

        is_correct = p['correct'] == 'YES'
        clv = (1 if is_correct else 0) - p_fair
        w = r['window']

        # All picks
        if w in ('rank', 'test'):
            splits['all'][f'{w}_clv'].append(clv)

        # 1. Method split (by actual outcome method)
        actual_method = p.get('actual_method', '')
        method_cat = get_method_cat(actual_method)
        if method_cat and w in ('rank', 'test'):
            splits[f'method_{method_cat}'][f'{w}_clv'].append(clv)

        # 2. Gender split
        parts = r['bout'].split(' vs ')
        if len(parts) == 2:
            div = division_by_bout.get((normalize(parts[0]), normalize(parts[1])), '')
            gender = 'women' if is_womens(div) else 'men'
            if w in ('rank', 'test'):
                splits[f'gender_{gender}'][f'{w}_clv'].append(clv)

        # 3. Fav/dog split
        fav_dog = r['fav_dog']
        if w in ('rank', 'test'):
            splits[f'favdog_{fav_dog}'][f'{w}_clv'].append(clv)

    # Compute per-user per-split stats
    user_data = {}
    for split_name, data in splits.items():
        rc = data['rank_clv']; tc = data['test_clv']
        rn = len(rc); tn = len(tc)
        if rn > 0 and tn > 0:
            user_data[split_name] = {
                'rank_clv': sum(rc) / rn, 'test_clv': sum(tc) / tn,
                'rank_n': rn, 'test_n': tn,
            }
    user_splits[username] = user_data

# ─── Compute persistence (rho) per split ───
print("\n" + "=" * 80)
print("PERSISTENCE ACROSS SPLITS")
print(f"Seed {SEED}, {N_BOOT} bootstrap draws, fight-clustered")
print("=" * 80)

rng = np.random.RandomState(SEED)

split_names = ['all', 'method_ko_tko', 'method_submission', 'method_decision',
               'gender_men', 'gender_women', 'favdog_fav', 'favdog_dog']

print(f"\n{'Split':<25} {'n_users':>7} {'rho':>7} {'CI_lo':>7} {'CI_hi':>7} {'med_rank_n':>10} {'med_test_n':>10}")
print("-" * 80)

for split in split_names:
    # Collect users with enough data in this split
    users_r = []; users_t = []
    for u, data in user_splits.items():
        if split not in data: continue
        d = data[split]
        # Require ≥30 picks in each window for the split
        min_n = 30 if split != 'all' else 150
        min_t = 15 if split != 'all' else 80
        if d['rank_n'] >= min_n and d['test_n'] >= min_t:
            users_r.append(d['rank_clv'])
            users_t.append(d['test_clv'])

    n = len(users_r)
    if n < 10:
        print(f"{split:<25} {n:>7}   (too few)")
        continue

    r_arr = np.array(users_r); t_arr = np.array(users_t)
    rho, _ = spearmanr(r_arr, t_arr)

    # Bootstrap CI
    boot_rhos = []
    for _ in range(N_BOOT):
        idx = rng.choice(n, size=n, replace=True)
        br, _ = spearmanr(r_arr[idx], t_arr[idx])
        boot_rhos.append(br)
    ci = (np.percentile(boot_rhos, 2.5), np.percentile(boot_rhos, 97.5))

    # Median picks per user in this split
    all_rn = [data[split]['rank_n'] for u, data in user_splits.items() if split in data and data[split]['rank_n'] >= (30 if split != 'all' else 150)]
    all_tn = [data[split]['test_n'] for u, data in user_splits.items() if split in data and data[split]['test_n'] >= (15 if split != 'all' else 80)]

    print(f"{split:<25} {n:>7} {rho:>+7.3f} {ci[0]:>+7.3f} {ci[1]:>+7.3f} "
          f"{median(all_rn):>10.0f} {median(all_tn):>10.0f}")

# ─── Method-specific persistence: did user pick the right method? ───
print("\n" + "=" * 80)
print("METHOD ACCURACY PERSISTENCE (picked_method vs actual_method)")
print("=" * 80)

# For v2 users with method data: does rank-window method accuracy predict test-window?
user_method_acc = {}
for username in done:
    sv = done[username].get('scraper_version', 1)
    if sv != 2: continue
    safe = username.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): continue

    with open(path, 'r', encoding='utf-8') as f:
        picks = list(csv.DictReader(f))

    rank_hits = 0; rank_total = 0; test_hits = 0; test_total = 0

    for p in picks:
        pm = p.get('picked_method', '').strip()
        if not pm: continue
        am = p.get('actual_method', '')
        pm_cat = get_method_cat(pm)
        am_cat = get_method_cat(am)
        if not pm_cat or not am_cat: continue

        # Need window assignment
        ck_n = normalize_event(p['event'])
        candidates = event_bouts.get(ck_n, [])
        if not candidates:
            for ek, rows in event_bouts.items():
                if ek in ck_n or ck_n in ek:
                    candidates = rows; break
        if not candidates: continue
        w = candidates[0]['window']  # approximate
        if candidates[0]['canonical_date'] == DROP_DATE: continue

        # Joint correct: right fighter AND right method
        is_fight_correct = p['correct'] == 'YES'
        is_method_correct = pm_cat == am_cat
        joint = is_fight_correct and is_method_correct

        if w == 'rank':
            rank_total += 1
            if joint: rank_hits += 1
        elif w == 'test':
            test_total += 1
            if joint: test_hits += 1

    if rank_total >= 50 and test_total >= 30:
        user_method_acc[username] = {
            'rank_acc': rank_hits / rank_total,
            'test_acc': test_hits / test_total,
            'rank_n': rank_total, 'test_n': test_total,
        }

n_m = len(user_method_acc)
if n_m >= 10:
    r_acc = np.array([v['rank_acc'] for v in user_method_acc.values()])
    t_acc = np.array([v['test_acc'] for v in user_method_acc.values()])
    rho_m, _ = spearmanr(r_acc, t_acc)

    boot_m = []
    for _ in range(N_BOOT):
        idx = rng.choice(n_m, size=n_m, replace=True)
        br, _ = spearmanr(r_acc[idx], t_acc[idx])
        boot_m.append(br)
    ci_m = (np.percentile(boot_m, 2.5), np.percentile(boot_m, 97.5))

    print(f"\nMethod accuracy persistence (v2 users, joint fighter+method):")
    print(f"  n={n_m}, rho={rho_m:+.3f} CI=[{ci_m[0]:+.3f},{ci_m[1]:+.3f}]")
    print(f"  Mean rank_acc={r_acc.mean():.3f}, test_acc={t_acc.mean():.3f}")
else:
    print(f"\n  Only {n_m} v2 users with enough method data — too few")
