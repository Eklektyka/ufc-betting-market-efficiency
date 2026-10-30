#!/usr/bin/env python3
"""Ezoteryka vs peer benchmark: separate MY leaks from everyone's leaks."""
import csv, os, re, sys, unicodedata
import numpy as np
from collections import defaultdict, Counter
from statistics import median

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67
rng = np.random.RandomState(SEED)
PICKS_DIR = r'C:\Research\ufc\picks\users'
AUTHOR = 'Ezoteryka'

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
def normalize(name):
    return re.sub(r'[^\w\s]', '', strip_accents(name).strip().lower()).strip()
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

# Odds table
event_bouts = defaultdict(list)
with open('ezoteryka_scored.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_bouts[normalize_event(r['card_key'])].append(r)

# Division
division_map = {}
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        fa = normalize(r['fighter_name']); fb = normalize(r['fighter_name_opp'])
        div = r.get('division','').strip().upper().replace(' BOUT','').replace('UFC ','')
        if div:
            division_map[(fa,fb)] = div; division_map[(fb,fa)] = div

# Inversions for Ezoteryka
INVERSIONS = {
    (normalize_event('UFC 326: Holloway vs. Oliveira 2'), 'sumudaerji'),
    (normalize_event('UFC Fight Night: Walker vs. Zhang'), 'sumudaerji'),
    (normalize_event('UFC Fight Night: Song vs. Figueiredo'), 'yadong song'),
}

# Load all users
import json
state = json.load(open(r'C:\Research\ufc\picks\state.json'))
all_users = [u for u, v in state['users'].items() if v['status'] == 'done']

DROP_DATE = '2025-08-09'

def score_user(username):
    safe = username.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f:
        picks = list(csv.DictReader(f))

    scored = []
    event_idx = defaultdict(int)
    for p in picks:
        ev = p['event']; bout_pos = event_idx[ev]; event_idx[ev] += 1
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
        if not r or r['canonical_date'] == DROP_DATE: continue

        if names_match(fp_n, normalize(r['picked_fighter'])):
            p_fair = float(r['p_fair_picked'])
        else:
            p_fair = 1 - float(r['p_fair_picked'])

        # Apply inversions for author
        if username == AUTHOR:
            for inv_ck, inv_fn in INVERSIONS:
                if inv_ck == ck_n and names_match(inv_fn, fp_n):
                    p_fair = 1 - p_fair; break

        correct = p['correct'] == 'YES'
        div = division_map.get((fp_n, opp_n), division_map.get((opp_n, fp_n), ''))
        card_pos = 'Main event' if bout_pos == 0 else ('Main card' if bout_pos < 5 else 'Prelims')
        pm = get_method_cat(p.get('picked_method','')) if p.get('picked_method') else None

        scored.append({
            'correct': correct, 'p_fair': p_fair, 'division': div,
            'card_pos': card_pos, 'picked_method': pm,
            'event': ev, 'date': r['canonical_date'],
        })
    return scored

print("Scoring all users...", flush=True)
user_scored = {}
for u in all_users:
    s = score_user(u)
    if s and len(s) >= 200:
        user_scored[u] = s

print(f"Users with >=200 scored picks: {len(user_scored)}")
my = user_scored.get(AUTHOR)
if not my:
    print("Author not found!"); sys.exit(1)

def vs_implied(picks):
    if not picks: return None
    acc = sum(p['correct'] for p in picks) / len(picks)
    impl = sum(p['p_fair'] for p in picks) / len(picks)
    return acc - impl

def percentile_of(my_val, all_vals):
    return sum(1 for v in all_vals if v <= my_val) / len(all_vals) * 100

# ═══════════════════════════════════════════════════════════════════
# 1. OVERALL
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("1. OVERALL: my percentile among all users")
print(f"{'='*80}")

all_vi = {u: vs_implied(s) for u, s in user_scored.items()}
my_vi = all_vi[AUTHOR]
pctile = percentile_of(my_vi, list(all_vi.values()))
vals = np.array(list(all_vi.values()))
print(f"\n  Me: {my_vi:+.1%}pp vs implied (n={len(my)})")
print(f"  Peers: mean={vals.mean():+.1%}, median={np.median(vals):+.1%}, SD={vals.std():.1%}")
print(f"  My percentile: {pctile:.0f}th")

# ═══════════════════════════════════════════════════════════════════
# 2. BY DIVISION
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("2. BY DIVISION: my leak or everyone's?")
print(f"{'='*80}")

# Collect divisions with enough data
div_counts = Counter(p['division'] for p in my if p['division'])
target_divs = [d for d, c in div_counts.items() if c >= 10]

print(f"\n  {'Division':<30} {'My n':>5} {'My vs_impl':>10} {'Peer mean':>10} {'My pctile':>10} {'Verdict'}")
print("  " + "-" * 78)

div_results = []
for div in sorted(target_divs, key=lambda d: vs_implied([p for p in my if p['division']==d]) or 0):
    my_div = [p for p in my if p['division'] == div]
    my_div_vi = vs_implied(my_div)

    # Peer distribution on same division
    peer_vis = []
    for u, s in user_scored.items():
        if u == AUTHOR: continue
        u_div = [p for p in s if p['division'] == div]
        if len(u_div) >= 5:
            peer_vis.append(vs_implied(u_div))

    if len(peer_vis) < 10: continue
    peer_mean = np.mean(peer_vis)
    my_pctile = percentile_of(my_div_vi, peer_vis)

    # Verdict
    if my_pctile < 25 and peer_mean > -0.02:
        verdict = "MY LEAK"
    elif peer_mean < -0.03:
        verdict = "hard div"
    elif my_pctile > 75:
        verdict = "my edge"
    else:
        verdict = "average"

    flag = ' <25' if len(my_div) < 25 else ''
    print(f"  {div[:29]:<30} {len(my_div):>5} {my_div_vi:>+9.1%} {peer_mean:>+9.1%} {my_pctile:>9.0f}th {verdict}{flag}")
    div_results.append({'div': div, 'my_vi': my_div_vi, 'peer_mean': peer_mean,
                        'pctile': my_pctile, 'n': len(my_div)})

# ═══════════════════════════════════════════════════════════════════
# 3. METHOD CALLING
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("3. METHOD CALLING: am I uniquely sub-blind or is everyone?")
print(f"{'='*80}")

# My method call rates
my_methods = [p for p in my if p['picked_method']]
if my_methods:
    my_rates = Counter(p['picked_method'] for p in my_methods)
    my_total = len(my_methods)

    # Peer call rates (v2 users only)
    peer_sub_rates = []
    peer_ko_rates = []
    peer_dec_rates = []
    for u, s in user_scored.items():
        if u == AUTHOR: continue
        u_methods = [p for p in s if p['picked_method']]
        if len(u_methods) < 50: continue
        ut = len(u_methods)
        peer_sub_rates.append(sum(1 for p in u_methods if p['picked_method']=='Submission') / ut)
        peer_ko_rates.append(sum(1 for p in u_methods if p['picked_method']=='KO/TKO') / ut)
        peer_dec_rates.append(sum(1 for p in u_methods if p['picked_method']=='Decision') / ut)

    print(f"\n  Method call rates:")
    print(f"  {'Method':<15} {'My rate':>8} {'Peer mean':>10} {'Peer SD':>8} {'My pctile':>10}")
    for method, my_ct, peer_rates in [
        ('KO/TKO', my_rates.get('KO/TKO',0), peer_ko_rates),
        ('Submission', my_rates.get('Submission',0), peer_sub_rates),
        ('Decision', my_rates.get('Decision',0), peer_dec_rates),
    ]:
        my_rate = my_ct / my_total
        if peer_rates:
            pmean = np.mean(peer_rates); psd = np.std(peer_rates)
            pctile = percentile_of(my_rate, peer_rates)
            print(f"  {method:<15} {my_rate:>7.0%} {pmean:>9.0%} {psd:>7.0%} {pctile:>9.0f}th")
        else:
            print(f"  {method:<15} {my_rate:>7.0%}    (no peers with method data)")

    # Sub accuracy vs peers
    my_sub_acc = vs_implied([p for p in my_methods if p['picked_method']=='Submission'])
    peer_sub_accs = []
    for u, s in user_scored.items():
        if u == AUTHOR: continue
        u_sub = [p for p in s if p.get('picked_method')=='Submission']
        if len(u_sub) >= 10:
            peer_sub_accs.append(vs_implied(u_sub))

    if my_sub_acc is not None and peer_sub_accs:
        print(f"\n  Submission-pick accuracy-vs-implied:")
        print(f"    Me: {my_sub_acc:+.1%}pp, peers: mean={np.mean(peer_sub_accs):+.1%}, "
              f"pctile={percentile_of(my_sub_acc, peer_sub_accs):.0f}th")
        if np.mean(peer_sub_accs) < -0.03:
            print(f"    NOTE: Everyone under-performs on sub calls (peer mean {np.mean(peer_sub_accs):+.1%}pp).")
            print(f"    Sub-blindness is UNIVERSAL, not just yours. But it's still an absolute")
            print(f"    bias you can exploit by calling more subs (the market is correct, you aren't).")
else:
    print("  No method data available")

# ═══════════════════════════════════════════════════════════════════
# 4. MAIN EVENTS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("4. MAIN EVENTS: mine or universal?")
print(f"{'='*80}")

my_main = [p for p in my if p['card_pos'] == 'Main event']
my_main_vi = vs_implied(my_main)

peer_main_vis = []
for u, s in user_scored.items():
    if u == AUTHOR: continue
    u_main = [p for p in s if p['card_pos'] == 'Main event']
    if len(u_main) >= 10:
        peer_main_vis.append(vs_implied(u_main))

if peer_main_vis:
    pctile = percentile_of(my_main_vi, peer_main_vis)
    print(f"\n  Me: {my_main_vi:+.1%}pp (n={len(my_main)})")
    print(f"  Peers: mean={np.mean(peer_main_vis):+.1%}pp, SD={np.std(peer_main_vis):.1%}")
    print(f"  My percentile: {pctile:.0f}th")
    if np.mean(peer_main_vis) < -0.02:
        print(f"  → EVERYONE underperforms on main events — it's a hard position, not your leak")
    elif pctile < 25:
        print(f"  → YOUR LEAK specifically — peers do fine on main events")
    else:
        print(f"  → Average — neither a leak nor an edge")

# ═══════════════════════════════════════════════════════════════════
# 5. PERSISTENCE GATE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("5. PERSISTENCE GATE: do my division/method ranks persist across halves?")
print(f"{'='*80}")

# Split my picks by date
my_sorted = sorted(my, key=lambda p: p['date'])
mid = len(my_sorted) // 2
h1 = my_sorted[:mid]; h2 = my_sorted[mid:]

# Division persistence
h1_div_vi = {}; h2_div_vi = {}
for div in target_divs:
    d1 = [p for p in h1 if p['division'] == div]
    d2 = [p for p in h2 if p['division'] == div]
    if len(d1) >= 5 and len(d2) >= 5:
        h1_div_vi[div] = vs_implied(d1)
        h2_div_vi[div] = vs_implied(d2)

common = sorted(set(h1_div_vi.keys()) & set(h2_div_vi.keys()))
if len(common) >= 5:
    from scipy.stats import spearmanr
    r1 = [h1_div_vi[d] for d in common]
    r2 = [h2_div_vi[d] for d in common]
    rho, p = spearmanr(r1, r2)
    print(f"\n  Division split-half persistence:")
    print(f"    Divisions with data in both halves: {len(common)}")
    print(f"    Spearman rho: {rho:+.3f} (p={p:.3f})")
    if rho > 0.3 and p < 0.05:
        print(f"    → PERSISTENT: my division-level performance is real, not noise")
    else:
        print(f"    → NOT PERSISTENT: my division ranks don't carry across halves")
        print(f"    Division-level 'leaks' and 'edges' are likely noise")

    print(f"\n    Per-division half-split:")
    print(f"    {'Division':<25} {'H1':>8} {'H2':>8} {'Consistent':>10}")
    for d in common:
        consistent = 'yes' if np.sign(h1_div_vi[d]) == np.sign(h2_div_vi[d]) else 'FLIP'
        print(f"    {d[:24]:<25} {h1_div_vi[d]:>+7.1%} {h2_div_vi[d]:>+7.1%} {consistent:>10}")
else:
    print(f"\n  Too few divisions with data in both halves ({len(common)})")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VERDICT: MY LEAKS vs EVERYONE'S LEAKS")
print(f"{'='*80}")
print(f"""
MULTIPLICITY WARNING: {len(target_divs)} divisions + 3 methods + 1 card position
= {len(target_divs)+4} cells tested. Expect ~{(len(target_divs)+4)*0.05:.0f} extreme ranks by chance
at p=0.05. Only trust ranks that ALSO pass the persistence gate.
""")
