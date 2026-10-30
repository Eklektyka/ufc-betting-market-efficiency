#!/usr/bin/env python3
"""Check H1 consistency between 10% batch and new batch."""
import csv, json, re, unicodedata, os, sys
import numpy as np
from scipy.stats import spearmanr
from collections import defaultdict, Counter
from statistics import median

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
PICKS_DIR = r'C:\Research\ufc\picks\users'
AUTHOR = 'Ezoteryka'

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

# Load bout table
event_bouts = defaultdict(list)
all_bouts = []
with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_bouts[normalize_event(r['card_key'])].append(r)
        all_bouts.append(r)

# Fight arrays for bootstrap
bout_to_fidx = {}; fight_pfair_a = []
for b in all_bouts:
    bk = (b['card_key'], b['bout'])
    if bk in bout_to_fidx: continue
    parts = b['bout'].split(' vs ')
    if len(parts) != 2: continue
    fidx = len(fight_pfair_a)
    p_ezo = float(b['p_fair_picked']); ezo_f = normalize(b['picked_fighter'])
    p_a = p_ezo if names_match(ezo_f, normalize(parts[0])) else 1 - p_ezo
    fight_pfair_a.append(p_a)
    bout_to_fidx[bk] = fidx
fight_pfair_a = np.array(fight_pfair_a)
n_fights = len(fight_pfair_a)

def score_user(username):
    safe = username.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): return None, 0, 0
    with open(path, 'r', encoding='utf-8') as f:
        picks = list(csv.DictReader(f))
    scored = []; unmatched = 0
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
        if not r: unmatched += 1; continue
        ezo_picked_n = normalize(r['picked_fighter'])
        if names_match(fp_n, ezo_picked_n):
            best_line = int(r['best_line']); p_fair = float(r['p_fair_picked'])
        else:
            p_fair = 1 - float(r['p_fair_picked'])
            dec = 1 / p_fair if p_fair > 0 else 100
            best_line = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))
        is_correct = p['correct'] == 'YES'
        clv = (1 if is_correct else 0) - p_fair
        scored.append({
            'card_key': r['card_key'], 'bout': r['bout'],
            'fighter_picked': p['fighter_picked'], 'correct': is_correct,
            'p_fair': p_fair, 'clv': clv, 'window': r['window'],
            'best_line': best_line,
        })
    return scored, unmatched, len(picks)


def compute_h1(user_list, label):
    user_scored = {}
    for u in user_list:
        scored, unm, total = score_user(u)
        if scored and len(scored) >= 200:
            user_scored[u] = scored

    eligible = {}
    for u, scored in user_scored.items():
        rank_s = [s for s in scored if s['window'] == 'rank']
        test_s = [s for s in scored if s['window'] == 'test']
        rn = len(rank_s); tn = len(test_s)
        if rn >= 50 and tn >= 30:
            eligible[u] = {
                'rank_clv': sum(s['clv'] for s in rank_s) / rn,
                'test_clv': sum(s['clv'] for s in test_s) / tn,
                'rank_n': rn, 'test_n': tn, 'total_n': len(scored),
            }

    n_elig = len(eligible)
    if n_elig < 5:
        print(f'  {label}: only {n_elig} eligible, skipping')
        return None, user_scored

    rank_clvs = np.array([s['rank_clv'] for s in eligible.values()])
    test_clvs = np.array([s['test_clv'] for s in eligible.values()])
    rho_obs, _ = spearmanr(rank_clvs, test_clvs)
    se = 1 / np.sqrt(n_elig - 3)
    ci_lo = rho_obs - 1.96 * se; ci_hi = rho_obs + 1.96 * se

    # Bootstrap
    rng = np.random.RandomState(SEED)
    user_picks_arr = {}
    for u in eligible:
        pd = []
        for s in user_scored[u]:
            bk = (s['card_key'], s['bout'])
            fidx = bout_to_fidx.get(bk)
            if fidx is None: continue
            parts = s['bout'].split(' vs ')
            if len(parts) != 2: continue
            picked_a = 1 if names_match(normalize(s['fighter_picked']), normalize(parts[0])) else 0
            pd.append((fidx, picked_a, s['p_fair'], s['window']))
        user_picks_arr[u] = pd

    null_rho = []
    for _ in range(N_BOOT):
        sim = rng.random(n_fights) < fight_pfair_a
        sr = []; st = []
        for u in eligible:
            rs = ts = 0; rn = tn = 0
            for fidx, pa, pf, w in user_picks_arr[u]:
                correct = (pa == 1 and sim[fidx]) or (pa == 0 and not sim[fidx])
                clv_v = (1 if correct else 0) - pf
                if w == 'rank': rs += clv_v; rn += 1
                elif w == 'test': ts += clv_v; tn += 1
            sr.append(rs/rn if rn else 0); st.append(ts/tn if tn else 0)
        sr = np.array(sr); st = np.array(st)
        r, _ = spearmanr(sr, st); null_rho.append(r)
    null_rho = np.array(null_rho)

    print(f'  {label}:')
    print(f'    n_eligible={n_elig}, rho={rho_obs:+.4f}, CI=[{ci_lo:+.4f}, {ci_hi:+.4f}]')
    print(f'    null_mean={null_rho.mean():+.4f}, null_SD={null_rho.std():.4f}, '
          f'null_95th={np.percentile(null_rho, 95):+.4f}, pctile={((null_rho < rho_obs).mean()*100):.1f}%')
    return eligible, user_scored


def batch_diagnostics(user_list, user_scored_dict, label, state):
    print(f'\n  --- {label} diagnostics ---')
    scored_users = [u for u in user_list if u in user_scored_dict and user_scored_dict[u]]
    n = len(scored_users)
    if n == 0:
        print('    No scored users'); return

    picks_per_user = [len(user_scored_dict[u]) for u in scored_users]
    rank_per_user = [sum(1 for s in user_scored_dict[u] if s['window'] == 'rank') for u in scored_users]
    test_per_user = [sum(1 for s in user_scored_dict[u] if s['window'] == 'test') for u in scored_users]
    match_rates = []
    for u in scored_users:
        safe = u.replace(' ', '_').replace('/', '_')
        path = os.path.join(PICKS_DIR, f'{safe}.csv')
        with open(path, 'r', encoding='utf-8') as f:
            total = sum(1 for _ in csv.DictReader(f))
        scored_n = len(user_scored_dict[u])
        match_rates.append(scored_n / total if total else 0)

    versions = Counter()
    for u in scored_users:
        sv = state['users'].get(u, {})
        versions[sv.get('scraper_version', 1)] += 1

    # Events per user
    events_per_user = [len(set(s['card_key'] for s in user_scored_dict[u])) for u in scored_users]

    # CLV stats
    clvs = [sum(s['clv'] for s in user_scored_dict[u]) / len(user_scored_dict[u]) for u in scored_users]
    rois = [sum(s.get('profit', ((american_to_decimal(s['best_line'])-1)*100 if s['correct'] else -100))
            for s in user_scored_dict[u]) / (len(user_scored_dict[u])*100) for u in scored_users]

    print(f'    Users: {n}')
    print(f'    Scraper versions: {dict(versions)}')
    print(f'    Picks/user: min={min(picks_per_user)}, med={median(picks_per_user):.0f}, max={max(picks_per_user)}')
    print(f'    Rank picks/user: min={min(rank_per_user)}, med={median(rank_per_user):.0f}, max={max(rank_per_user)}')
    print(f'    Test picks/user: min={min(test_per_user)}, med={median(test_per_user):.0f}, max={max(test_per_user)}')
    print(f'    Events/user: min={min(events_per_user)}, med={median(events_per_user):.0f}, max={max(events_per_user)}')
    print(f'    Match rate: min={min(match_rates):.1%}, med={median(match_rates):.1%}, max={max(match_rates):.1%}')
    print(f'    Mean CLV: {np.mean(clvs):+.4f} (SD={np.std(clvs):.4f})')
    print(f'    Mean ROI: {np.mean(rois):+.1%}')


# ─── Main ───
state = json.load(open(r'C:\Research\ufc\picks\state.json'))
done = {u: v for u, v in state['users'].items() if v['status'] == 'done' and u != AUTHOR}

v1_users = [u for u, v in done.items() if 'scraper_version' not in v]
v2_users = [u for u, v in done.items() if v.get('scraper_version') == 2]

batch_10pct = v1_users + v2_users[:11]
batch_new = v2_users[11:]

print(f'Batch sizes: 10pct={len(batch_10pct)}, new={len(batch_new)}, total={len(done)}')
print()

# CHECK 1
print('=' * 70)
print('CHECK 1: Reproduce H1 on 10% batch (expect rho ~+0.154)')
print('=' * 70)
elig_10, scored_10 = compute_h1(batch_10pct, '10% batch')

print()
print('=' * 70)
print('CHECK 2: H1 on new batch only')
print('=' * 70)
elig_new, scored_new = compute_h1(batch_new, 'new batch')

print()
print('=' * 70)
print('CHECK 3: Batch diagnostics comparison')
print('=' * 70)
batch_diagnostics(batch_10pct, scored_10, '10% batch', state)
batch_diagnostics(batch_new, scored_new, 'new batch', state)
