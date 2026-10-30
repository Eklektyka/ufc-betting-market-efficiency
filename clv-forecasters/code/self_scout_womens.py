#!/usr/bin/env python3
"""Self-scout: women's fights ranking vs the field."""
import csv, os, re, sys, unicodedata
import numpy as np
from collections import defaultdict
from scipy.stats import spearmanr

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
PICKS_DIR = r'C:\Research\ufc\picks\users'
AUTHOR = 'Ezoteryka'
DROP_DATE = '2025-08-09'
MIN_WOMEN = 15

rng = np.random.RandomState(SEED)

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

# Women fighters set
women_fighters = set()
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if 'women' in r.get('division', '').lower():
            women_fighters.add(normalize(r['fighter_name']))

# Bout table
event_bouts = defaultdict(list)
with open('ezoteryka_scored.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_bouts[normalize_event(r['card_key'])].append(r)

# Inversion fixes
INVERSIONS = {
    (normalize_event('UFC 326: Holloway vs. Oliveira 2'), 'sumudaerji'),
    (normalize_event('UFC Fight Night: Walker vs. Zhang'), 'sumudaerji'),
    (normalize_event('UFC Fight Night: Song vs. Figueiredo'), 'yadong song'),
}

# Load state
import json
state = json.load(open(r'C:\Research\ufc\picks\state.json'))
all_users = [u for u, v in state['users'].items() if v['status'] == 'done']

print(f"Loading {len(all_users)} users...", flush=True)

# Score all users on women's and men's fights
user_women = {}  # user -> list of {correct, p_fair, profit, event, canonical_date, fav_dog}
user_men = {}

for username in all_users:
    safe = username.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): continue
    with open(path, 'r', encoding='utf-8') as f:
        picks = list(csv.DictReader(f))

    w_picks = []; m_picks = []

    for p in picks:
        fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
        is_women = fp_n in women_fighters and opp_n in women_fighters
        correct = p['correct'] == 'YES'

        ck_n = normalize_event(p['event'])
        candidates = event_bouts.get(ck_n, [])
        if not candidates:
            for ek, rows in event_bouts.items():
                if ek in ck_n or ck_n in ek:
                    candidates = rows; break
        if not candidates: continue

        odds_row = None
        for row in candidates:
            parts = row['bout'].split(' vs ')
            if len(parts) != 2: continue
            fa_n, fb_n = normalize(parts[0]), normalize(parts[1])
            if (names_match(fp_n, fa_n) and names_match(opp_n, fb_n)) or \
               (names_match(fp_n, fb_n) and names_match(opp_n, fa_n)):
                odds_row = row; break
        if not odds_row: continue
        if odds_row['canonical_date'] == DROP_DATE: continue

        if names_match(fp_n, normalize(odds_row['picked_fighter'])):
            p_fair = float(odds_row['p_fair_picked'])
            best_line = int(odds_row['best_line'])
        else:
            p_fair = 1 - float(odds_row['p_fair_picked'])
            dec = 1 / p_fair if p_fair > 0 else 100
            best_line = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))

        # Apply inversions for Ezoteryka
        if username == AUTHOR:
            for inv_ck, inv_fn in INVERSIONS:
                if inv_ck == ck_n and names_match(inv_fn, fp_n):
                    p_fair = 1 - p_fair
                    dec = 1 / p_fair if p_fair > 0 else 100
                    best_line = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))
                    break

        dec_odds = american_to_decimal(best_line)
        profit = (dec_odds - 1) * 100 if correct else -100
        fav_dog = 'fav' if p_fair >= 0.5 else 'dog'

        entry = {
            'correct': correct, 'p_fair': p_fair, 'profit': profit,
            'event': p['event'], 'canonical_date': odds_row['canonical_date'],
            'fav_dog': fav_dog,
        }

        if is_women:
            w_picks.append(entry)
        else:
            m_picks.append(entry)

    if w_picks: user_women[username] = w_picks
    if m_picks: user_men[username] = m_picks

print(f"Users with women's picks: {len(user_women)}")
print(f"Users with >={MIN_WOMEN} women's picks: {sum(1 for v in user_women.values() if len(v) >= MIN_WOMEN)}")

# ═══════════════════════════════════════════════════════════════════
# 1. MY RANK ON WOMEN'S FIGHTS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"1. YOUR RANK ON WOMEN'S FIGHTS (acc-vs-implied)")
print(f"{'='*80}")

women_vs_implied = {}
for u, picks in user_women.items():
    if len(picks) < MIN_WOMEN: continue
    acc = sum(p['correct'] for p in picks) / len(picks)
    impl = sum(p['p_fair'] for p in picks) / len(picks)
    women_vs_implied[u] = {'vs': acc - impl, 'n': len(picks), 'acc': acc, 'impl': impl}

n_qualified = len(women_vs_implied)
print(f"\nUsers with >={MIN_WOMEN} women's picks: {n_qualified}")
print(f"(Threshold effect: >=10 → {sum(1 for v in user_women.values() if len(v) >= 10)}, "
      f">=20 → {sum(1 for v in user_women.values() if len(v) >= 20)}, "
      f">=30 → {sum(1 for v in user_women.values() if len(v) >= 30)})")

ranked = sorted(women_vs_implied.items(), key=lambda x: -x[1]['vs'])
my_rank = next((i + 1 for i, (u, _) in enumerate(ranked) if u == AUTHOR), None)
my_data = women_vs_implied.get(AUTHOR)
all_vs = np.array([v['vs'] for v in women_vs_implied.values()])

if my_rank and my_data:
    pctile = 100 * (1 - my_rank / n_qualified)
    print(f"\nYOU: rank {my_rank}/{n_qualified} (top {100 - pctile:.0f}th percentile)")
    print(f"  acc-vs-implied = {my_data['vs']:+.1%} (n={my_data['n']})")
    print(f"\nDistribution of acc-vs-implied on women's fights:")
    print(f"  Top 5:    {np.percentile(all_vs, 95):+.1%}")
    print(f"  Top 25:   {np.percentile(all_vs, 75):+.1%}")
    print(f"  Median:   {np.median(all_vs):+.1%}")
    print(f"  Bottom 25:{np.percentile(all_vs, 25):+.1%}")
    print(f"  Bottom 5: {np.percentile(all_vs, 5):+.1%}")
    print(f"  Mean:     {all_vs.mean():+.1%} (SD={all_vs.std():.1%})")

    # Histogram
    bins = np.arange(-0.20, 0.21, 0.02)
    hist, _ = np.histogram(all_vs, bins=bins)
    print(f"\n  Histogram:")
    for i, h in enumerate(hist):
        me = ' ← YOU' if bins[i] <= my_data['vs'] < bins[i + 1] else ''
        bar = '█' * min(h, 40)
        print(f"    [{bins[i]:+.0%},{bins[i+1]:+.0%}) {h:>3} {bar}{me}")

    # Top 10
    print(f"\n  Top 10:")
    print(f"  {'User':<25} {'n':>4} {'vs_impl':>8} {'acc':>6} {'impl':>6}")
    for i, (u, d) in enumerate(ranked[:10]):
        tag = ' ← YOU' if u == AUTHOR else ''
        print(f"  {u[:24]:<25} {d['n']:>4} {d['vs']:>+7.1%} {d['acc']:>5.1%} {d['impl']:>5.1%}{tag}")

# ═══════════════════════════════════════════════════════════════════
# 2. PERSISTENCE: WOMEN'S SKILL ACROSS USERS (split-half)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"2. IS WOMEN'S SKILL REAL? (split-half persistence)")
print(f"{'='*80}")

early_vs = []; late_vs = []
for u, picks in user_women.items():
    if len(picks) < MIN_WOMEN: continue
    # Sort by date, split in half
    sorted_p = sorted(picks, key=lambda p: p['canonical_date'])
    mid = len(sorted_p) // 2
    early = sorted_p[:mid]; late = sorted_p[mid:]
    if len(early) < 5 or len(late) < 5: continue
    e_acc = sum(p['correct'] for p in early) / len(early)
    e_impl = sum(p['p_fair'] for p in early) / len(early)
    l_acc = sum(p['correct'] for p in late) / len(late)
    l_impl = sum(p['p_fair'] for p in late) / len(late)
    early_vs.append(e_acc - e_impl)
    late_vs.append(l_acc - l_impl)

if len(early_vs) >= 10:
    rho, _ = spearmanr(early_vs, late_vs)
    boot = []
    for _ in range(N_BOOT):
        idx = rng.choice(len(early_vs), size=len(early_vs), replace=True)
        br, _ = spearmanr(np.array(early_vs)[idx], np.array(late_vs)[idx])
        boot.append(br)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))
    excl = 'YES' if ci[0] > 0 else 'NO'
    print(f"\n  Split-half ρ: {rho:+.3f} CI=[{ci[0]:+.3f},{ci[1]:+.3f}] (n={len(early_vs)} users)")
    print(f"  CI excludes zero: {excl}")
    if excl == 'YES':
        print(f"  → Women's-fight skill is a REAL separable trait across users")
    else:
        print(f"  → Cannot confirm persistence — high performers may be variance")

# ═══════════════════════════════════════════════════════════════════
# 3. IS IT ME OR THE MARKET? (women's favs specifically)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"3. IS IT YOU OR THE MARKET? (women's favorites underpriced?)")
print(f"{'='*80}")

users_wfav_vs = []
for u, picks in user_women.items():
    if len(picks) < MIN_WOMEN: continue
    fav_picks = [p for p in picks if p['fav_dog'] == 'fav']
    if len(fav_picks) < 10: continue
    acc = sum(p['correct'] for p in fav_picks) / len(fav_picks)
    impl = sum(p['p_fair'] for p in fav_picks) / len(fav_picks)
    users_wfav_vs.append({'user': u, 'vs': acc - impl, 'n': len(fav_picks)})

n_wfav = len(users_wfav_vs)
beat_implied = sum(1 for u in users_wfav_vs if u['vs'] > 0)
my_wfav = next((u for u in users_wfav_vs if u['user'] == AUTHOR), None)

print(f"\n  Users with >=10 women's fav picks: {n_wfav}")
print(f"  Users beating implied on women's favs: {beat_implied}/{n_wfav} ({beat_implied/n_wfav:.0%})")

if my_wfav:
    my_wfav_rank = sum(1 for u in users_wfav_vs if u['vs'] > my_wfav['vs']) + 1
    print(f"  Your position: {my_wfav_rank}/{n_wfav} ({my_wfav['vs']:+.1%}, n={my_wfav['n']})")

all_wfav_vs = np.array([u['vs'] for u in users_wfav_vs])
print(f"  Mean acc-vs-implied on women's favs: {all_wfav_vs.mean():+.1%} (SD={all_wfav_vs.std():.1%})")

if beat_implied / n_wfav > 0.6:
    print(f"  → MARKET MISPRICING: {beat_implied/n_wfav:.0%} of users beat implied on women's favs.")
    print(f"    Women's favorites appear systematically underpriced. Your edge is partially structural.")
else:
    print(f"  → Not a broad market issue. Your edge is more individual than structural.")

# ═══════════════════════════════════════════════════════════════════
# 4. MEN'S RANK FOR CONTRAST
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"4. YOUR RANK ON MEN'S FIGHTS (contrast)")
print(f"{'='*80}")

men_vs_implied = {}
for u, picks in user_men.items():
    if len(picks) < 100: continue
    acc = sum(p['correct'] for p in picks) / len(picks)
    impl = sum(p['p_fair'] for p in picks) / len(picks)
    men_vs_implied[u] = {'vs': acc - impl, 'n': len(picks)}

men_ranked = sorted(men_vs_implied.items(), key=lambda x: -x[1]['vs'])
my_men_rank = next((i + 1 for i, (u, _) in enumerate(men_ranked) if u == AUTHOR), None)
my_men = men_vs_implied.get(AUTHOR)
n_men = len(men_vs_implied)

if my_men_rank and my_men:
    men_pctile = 100 * (1 - my_men_rank / n_men)
    print(f"\n  Men's: rank {my_men_rank}/{n_men} (top {100 - men_pctile:.0f}th percentile)")
    print(f"  acc-vs-implied = {my_men['vs']:+.1%} (n={my_men['n']})")
    if my_rank:
        w_pctile = 100 * (1 - my_rank / n_qualified)
        print(f"\n  Comparison:")
        print(f"    Women's: top {100 - w_pctile:.0f}th percentile (of {n_qualified} users)")
        print(f"    Men's:   top {100 - men_pctile:.0f}th percentile (of {n_men} users)")
        if w_pctile > men_pctile + 15:
            print(f"    → You rank distinctly higher on women's fights")
        elif abs(w_pctile - men_pctile) < 15:
            print(f"    → Similar ranking — you're just generally good, not women's-specific")

# ═══════════════════════════════════════════════════════════════════
# BONUS: TOP-DECILE MONEYLINE ROI ON WOMEN'S FIGHTS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"BONUS: TOP-DECILE USERS' MONEYLINE ROI ON WOMEN'S FIGHTS")
print(f"(pre-committed null expectation)")
print(f"{'='*80}")

# Rank users by overall CLV (not women's-specific)
user_overall_clv = {}
for u in all_users:
    if u == AUTHOR: continue
    w = user_women.get(u, []) + user_men.get(u, [])
    if len(w) < 200: continue
    user_overall_clv[u] = sum(p['correct'] - p['p_fair'] for p in w) / len(w)

sorted_clv = sorted(user_overall_clv.items(), key=lambda x: -x[1])
d = max(1, len(sorted_clv) // 10)
top_decile = set(u for u, _ in sorted_clv[:d])

top_w_bets = []
for u in top_decile:
    for p in user_women.get(u, []):
        top_w_bets.append(p)

if len(top_w_bets) >= 20:
    roi = sum(b['profit'] for b in top_w_bets) / (len(top_w_bets) * 100)
    events = list(set(b['event'] for b in top_w_bets))
    eb = defaultdict(list)
    for b in top_w_bets: eb[b['event']].append(b)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sp = sn = 0
        for e in se:
            for b in eb[e]: sp += b['profit']; sn += 1
        boot.append(sp / (sn * 100) if sn > 0 else 0)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))
    excl = ci[0] > 0

    print(f"\n  Top-decile (by overall CLV) on women's fights:")
    print(f"  n={len(top_w_bets)}, ROI={roi:+.1%} CI=[{ci[0]:+.1%},{ci[1]:+.1%}]")
    print(f"  CI excludes zero: {'YES' if excl else 'NO'}")
    if not excl:
        print(f"  → NULL, as expected. Top-decile overall skill does not produce")
        print(f"    women's-fight profit — consistent with the main study null.")
else:
    print(f"\n  Too few bets ({len(top_w_bets)}) for top-decile women's ROI")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"PLAIN READ")
print(f"{'='*80}")
