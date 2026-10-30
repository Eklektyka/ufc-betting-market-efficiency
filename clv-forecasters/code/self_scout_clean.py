#!/usr/bin/env python3
"""Self-scout v2: clean odds (3 inversions fixed), before/after, gender deep-dive."""
import csv, os, re, sys, unicodedata
import numpy as np
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000

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
    if 'ko' in s or 'tko' in s: return 'KO/TKO'
    if 'submission' in s: return 'Submission'
    if 'decision' in s: return 'Decision'
    return None

rng = np.random.RandomState(SEED)

# ─── INVERSIONS TO FIX ───
# Key: (normalize(card_key), normalize(picked_fighter)) → swap odds
INVERSIONS = {
    # Sumudaerji vs Aguilar, UFC 326
    (normalize_event('UFC 326: Holloway vs. Oliveira 2'), 'sumudaerji'): True,
    # Sumudaerji vs Borjas, Walker vs Zhang
    (normalize_event('UFC Fight Night: Walker vs. Zhang'), 'sumudaerji'): True,
    # Song vs Figueiredo
    (normalize_event('UFC Fight Night: Song vs. Figueiredo'), 'yadong song'): True,
}

# ─── Load picks + odds ───
event_bouts = defaultdict(list)
with open('ezoteryka_scored.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_bouts[normalize_event(r['card_key'])].append(r)

with open(r'C:\Research\ufc\picks\users\Ezoteryka.csv', encoding='utf-8') as f:
    picks = list(csv.DictReader(f))

# Women fighters
women_fighters = set()
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if 'women' in r.get('division', '').lower():
            women_fighters.add(normalize(r['fighter_name']))

def score_picks(apply_fixes):
    """Score all picks. If apply_fixes, swap odds on the 3 inversions."""
    scored = []
    event_bout_idx = defaultdict(int)

    for p in picks:
        ev = p['event']
        bout_pos = event_bout_idx[ev]
        event_bout_idx[ev] += 1

        fp = p['fighter_picked']; opp = p['opponent']
        fp_n = normalize(fp); opp_n = normalize(opp)
        correct = p['correct'] == 'YES'

        ck_n = normalize_event(ev)
        candidates = event_bouts.get(ck_n, [])
        if not candidates:
            for ek, rows in event_bouts.items():
                if ek in ck_n or ck_n in ek:
                    candidates = rows; break

        odds_row = None
        for row in candidates:
            parts = row['bout'].split(' vs ')
            if len(parts) != 2: continue
            fa_n, fb_n = normalize(parts[0]), normalize(parts[1])
            if (names_match(fp_n, fa_n) and names_match(opp_n, fb_n)) or \
               (names_match(fp_n, fb_n) and names_match(opp_n, fa_n)):
                odds_row = row; break

        p_fair = None; best_line = None; profit = None
        if odds_row:
            if names_match(fp_n, normalize(odds_row['picked_fighter'])):
                p_fair = float(odds_row['p_fair_picked'])
                best_line = int(odds_row['best_line'])
            else:
                p_fair = 1 - float(odds_row['p_fair_picked'])
                dec = 1 / p_fair if p_fair > 0 else 100
                best_line = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))

            # Apply inversion fix
            if apply_fixes:
                key = (ck_n, fp_n)
                # Check if any inversion key matches
                for inv_key in INVERSIONS:
                    if inv_key[0] == ck_n and names_match(inv_key[1], fp_n):
                        # Swap: my pick was joined as dog but is actually fav (or vice versa)
                        p_fair = 1 - p_fair
                        dec = 1 / p_fair if p_fair > 0 else 100
                        best_line = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))
                        break

            dec_odds = american_to_decimal(best_line)
            profit = (dec_odds - 1) * 100 if correct else -100

        fav_dog = None; prob_bucket = None
        if p_fair is not None:
            fav_dog = 'fav' if p_fair >= 0.5 else 'dog'
            if p_fair >= 0.70: prob_bucket = 'Heavy fav (>70%)'
            elif p_fair >= 0.55: prob_bucket = 'Mod fav (55-70%)'
            elif p_fair >= 0.45: prob_bucket = 'Coinflip (45-55%)'
            else: prob_bucket = 'Dog (<45%)'

        is_women = normalize(fp) in women_fighters and normalize(opp) in women_fighters

        scored.append({
            'event': ev, 'fighter_picked': fp, 'opponent': opp,
            'correct': correct, 'p_fair': p_fair, 'best_line': best_line,
            'profit': profit, 'fav_dog': fav_dog, 'prob_bucket': prob_bucket,
            'is_women': is_women, 'bout_pos': bout_pos,
        })
    return scored

dirty = score_picks(False)
clean = score_picks(True)

def compute_cell(data, filter_fn=None, label=''):
    sub = [s for s in data if s['p_fair'] is not None and (filter_fn is None or filter_fn(s))]
    n = len(sub)
    if n == 0: return {'n': 0, 'acc': 0, 'impl': 0, 'vs': 0, 'roi': 0, 'profit': 0}
    c = sum(s['correct'] for s in sub)
    acc = c / n
    impl = sum(s['p_fair'] for s in sub) / n
    vs = acc - impl
    profit = sum(s['profit'] for s in sub)
    roi = profit / (n * 100)
    return {'n': n, 'acc': acc, 'impl': impl, 'vs': vs, 'roi': roi, 'profit': profit}

def boot_roi(data, filter_fn=None):
    sub = [s for s in data if s['p_fair'] is not None and (filter_fn is None or filter_fn(s))]
    if len(sub) < 5: return (np.nan, np.nan)
    events = list(set(s['event'] for s in sub))
    eb = defaultdict(list)
    for s in sub: eb[s['event']].append(s)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sp = sn = 0
        for e in se:
            for s in eb[e]: sp += s['profit']; sn += 1
        boot.append(sp / (sn * 100) if sn > 0 else 0)
    return (np.percentile(boot, 2.5), np.percentile(boot, 97.5))

def fmt(c, ci=None):
    flag = ' <25' if c['n'] < 25 else ''
    ci_s = f" [{ci[0]:+.1%},{ci[1]:+.1%}]" if ci and not np.isnan(ci[0]) else ''
    return f"n={c['n']:>3} acc={c['acc']:>5.1%} impl={c['impl']:>5.1%} vs={c['vs']:>+5.1%} ROI={c['roi']:>+5.1%}{ci_s}{flag}"

def before_after(label, filt=None):
    d = compute_cell(dirty, filt)
    c = compute_cell(clean, filt)
    ci = boot_roi(clean, filt)
    print(f"  {label:<25} DIRTY: {fmt(d)}")
    print(f"  {'':<25} CLEAN: {fmt(c, ci)}")
    delta_roi = c['roi'] - d['roi'] if d['n'] > 0 and c['n'] > 0 else 0
    if abs(delta_roi) > 0.005:
        print(f"  {'':<25} Δ ROI = {delta_roi:+.1%}")
    print()
    return c, ci

# ═══════════════════════════════════════════════════════════════════
print("=" * 90)
print("EZOTERYKA SELF-SCOUT — CLEAN ODDS (3 inversions fixed)")
print("Best-line convention: best-of-field closing American odds across sportsbooks")
print("(line-shopped; real fill would be worse on average)")
print("=" * 90)

# 1. OVERALL
print(f"\n{'─'*90}")
print("1. OVERALL")
print(f"{'─'*90}\n")
before_after("Overall")

# 2. FAV/DOG
print(f"{'─'*90}")
print("2. FAVORITE vs UNDERDOG")
print(f"{'─'*90}\n")
before_after("Favorites", lambda s: s['fav_dog'] == 'fav')
before_after("Underdogs", lambda s: s['fav_dog'] == 'dog')

# 3. PROB BUCKETS (calibration)
print(f"{'─'*90}")
print("3. CALIBRATION BY IMPLIED-PROB BUCKET")
print(f"{'─'*90}\n")
for bucket in ['Heavy fav (>70%)', 'Mod fav (55-70%)', 'Coinflip (45-55%)', 'Dog (<45%)']:
    before_after(bucket, lambda s, b=bucket: s['prob_bucket'] == b)

# 4. GENDER
print(f"{'─'*90}")
print("4. MEN'S vs WOMEN'S")
print(f"{'─'*90}\n")
men_c, men_ci = before_after("Men's", lambda s: not s['is_women'])
wom_c, wom_ci = before_after("Women's", lambda s: s['is_women'])

# Boot CI on accuracy-vs-implied for women's
wom_sub = [s for s in clean if s['p_fair'] is not None and s['is_women']]
if len(wom_sub) >= 5:
    events = list(set(s['event'] for s in wom_sub))
    eb = defaultdict(list)
    for s in wom_sub: eb[s['event']].append(s)
    boot_vs = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sc = si = sn = 0
        for e in se:
            for s in eb[e]:
                sn += 1; sc += s['correct']; si += s['p_fair']
        if sn > 0:
            boot_vs.append(sc/sn - si/sn)
    ci_vs = (np.percentile(boot_vs, 2.5), np.percentile(boot_vs, 97.5))
    print(f"  Women's acc-vs-implied CI: [{ci_vs[0]:+.1%}, {ci_vs[1]:+.1%}] — {'excl 0' if ci_vs[0] > 0 else 'includes 0'}")

# 5. LEAVE-ONE-OUT on women's
print(f"\n{'─'*90}")
print("5. WOMEN'S LEAVE-ONE-OUT (remove single biggest payout)")
print(f"{'─'*90}\n")

wom_picks = [s for s in clean if s['p_fair'] is not None and s['is_women']]
if wom_picks:
    # Find biggest payout
    best_pick = max(wom_picks, key=lambda s: s['profit'])
    print(f"  Biggest women's payout: {best_pick['fighter_picked']} vs {best_pick['opponent']}")
    print(f"    profit=${best_pick['profit']:+.0f}, line={best_pick['best_line']:+d}, p_fair={best_pick['p_fair']:.1%}")
    print()

    full_roi = sum(s['profit'] for s in wom_picks) / (len(wom_picks) * 100)
    loo_picks = [s for s in wom_picks if s is not best_pick]
    loo_roi = sum(s['profit'] for s in loo_picks) / (len(loo_picks) * 100)
    loo_acc = sum(s['correct'] for s in loo_picks) / len(loo_picks)
    loo_impl = sum(s['p_fair'] for s in loo_picks) / len(loo_picks)

    print(f"  Full women's:  n={len(wom_picks)}, ROI={full_roi:+.1%}")
    print(f"  Without best:  n={len(loo_picks)}, ROI={loo_roi:+.1%}, acc={loo_acc:.1%}, vs_impl={loo_acc - loo_impl:+.1%}")
    print(f"  ROI change:    {loo_roi - full_roi:+.1%}")
    if abs(loo_roi - full_roi) > 0.05:
        print(f"  → Large swing — the edge is partially driven by that one pick")
    else:
        print(f"  → Stable — the edge doesn't depend on a single pick")

# 6. WITHIN WOMEN'S
print(f"\n{'─'*90}")
print("6. WITHIN WOMEN'S (anecdotal, tiny cells)")
print(f"{'─'*90}\n")

for label, filt in [("Women's fav", lambda s: s['is_women'] and s['fav_dog'] == 'fav'),
                    ("Women's dog", lambda s: s['is_women'] and s['fav_dog'] == 'dog')]:
    c = compute_cell(clean, filt)
    flag = ' <25' if c['n'] < 25 else ''
    print(f"  {label:<25} n={c['n']:>3} acc={c['acc']:>5.1%} impl={c['impl']:>5.1%} vs={c['vs']:>+5.1%} ROI={c['roi']:>+5.1%}{flag}")

print()
# Women's calibration
wom_by_bucket = defaultdict(list)
for s in clean:
    if s['p_fair'] is None or not s['is_women']: continue
    if s['p_fair'] >= 0.65: wom_by_bucket['Fav ≥65%'].append(s)
    elif s['p_fair'] >= 0.50: wom_by_bucket['Fav 50-65%'].append(s)
    else: wom_by_bucket['Dog <50%'].append(s)

print(f"  Women's calibration:")
print(f"  {'Bucket':<20} {'n':>4} {'My hit':>7} {'Implied':>8} {'Diff':>7}")
for b in ['Fav ≥65%', 'Fav 50-65%', 'Dog <50%']:
    sub = wom_by_bucket[b]
    if not sub: continue
    hit = sum(s['correct'] for s in sub) / len(sub)
    imp = sum(s['p_fair'] for s in sub) / len(sub)
    flag = ' <25' if len(sub) < 25 else ''
    print(f"  {b:<20} {len(sub):>4} {hit:>6.0%} {imp:>7.0%} {hit-imp:>+6.1%}{flag}")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*90}")
print("PLAIN-ENGLISH READ")
print(f"{'='*90}")
print("""
What survived the cleanup vs what was contamination:
""")

d_overall = compute_cell(dirty)
c_overall = compute_cell(clean)
print(f"OVERALL: ROI moved from {d_overall['roi']:+.1%} to {c_overall['roi']:+.1%} (Δ={c_overall['roi']-d_overall['roi']:+.1%}).")
print(f"  The 3 inversions were all in your dog bucket, so:")

d_dog = compute_cell(dirty, lambda s: s['fav_dog'] == 'dog')
c_dog = compute_cell(clean, lambda s: s['fav_dog'] == 'dog')
d_fav = compute_cell(dirty, lambda s: s['fav_dog'] == 'fav')
c_fav = compute_cell(clean, lambda s: s['fav_dog'] == 'fav')

print(f"  - Dog ROI: {d_dog['roi']:+.1%} → {c_dog['roi']:+.1%} (Δ={c_dog['roi']-d_dog['roi']:+.1%})")
print(f"  - Fav ROI: {d_fav['roi']:+.1%} → {c_fav['roi']:+.1%} (Δ={c_fav['roi']-d_fav['roi']:+.1%})")

d_wom = compute_cell(dirty, lambda s: s['is_women'])
c_wom = compute_cell(clean, lambda s: s['is_women'])
print(f"\nWOMEN'S EDGE: ROI {d_wom['roi']:+.1%} → {c_wom['roi']:+.1%} (Δ={c_wom['roi']-d_wom['roi']:+.1%}).")
print(f"  vs-implied: {d_wom['vs']:+.1%} → {c_wom['vs']:+.1%}")
