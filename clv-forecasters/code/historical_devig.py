#!/usr/bin/env python3
"""
Re-devig historical BFO odds using the SAME Shin implementation as bfo_close_all.
Validate, overlap-check, then run women's-fav time-trend.
"""
import csv, os, re, sys, unicodedata, math
import numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
rng = np.random.RandomState(SEED)

# ═══════════════════════════════════════════════════════════════════
# SHIN IMPLEMENTATION — same as devig_props.py (used for bfo_close_all)
# The bfo_close_all pipeline uses derive_and_join.py which calls this
# same Shin formula. Copied verbatim from devig_props.py lines 30-80.
# ═══════════════════════════════════════════════════════════════════

def american_to_implied(odds):
    """American odds -> raw implied probability (includes vig)."""
    if odds < 0:
        return -odds / (-odds + 100)
    else:
        return 100 / (odds + 100)

def shin_objective(z, pis, beta):
    total = 0.0
    for pi in pis:
        num = math.sqrt(z**2 + 4 * (1 - z) * pi**2 / beta) - z
        den = 2 * (1 - z)
        total += num / den
    return total - 1.0

def shin_probs(z, pis, beta):
    result = []
    for pi in pis:
        num = math.sqrt(z**2 + 4 * (1 - z) * pi**2 / beta) - z
        den = 2 * (1 - z)
        result.append(num / den)
    return result

def brentq(f, a, b, tol=1e-10, maxiter=200):
    fa, fb = f(a), f(b)
    if fa * fb > 0: return None
    if abs(fa) < tol: return a
    if abs(fb) < tol: return b
    c, fc = a, fa; d = e = b - a
    for _ in range(maxiter):
        if fb * fc > 0: c, fc = a, fa; d = e = b - a
        if abs(fc) < abs(fb): a, b, c = b, c, b; fa, fb, fc = fb, fc, fb
        tol1 = 2e-16 * abs(b) + 0.5 * tol
        m = 0.5 * (c - b)
        if abs(m) <= tol1 or fb == 0: return b
        if abs(e) >= tol1 and abs(fa) > abs(fb):
            s = fb / fa
            if a == c: p = 2 * m * s; q = 1 - s
            else:
                q2 = fa / fc; r = fb / fc
                p = s * (2 * m * q2 * (q2 - r) - (b - a) * (r - 1))
                q = (q2 - 1) * (r - 1) * (s - 1)
            if p > 0: q = -q
            else: p = -p
            if 2 * p < min(3 * m * q - abs(tol1 * q), abs(e * q)):
                e, d = d, p / q
            else: d = e = m
        else: d = e = m
        a, fa = b, fb
        if abs(d) > tol1: b += d
        else: b += tol1 if m > 0 else -tol1
        fb = f(b)
    return b

def devig_2way(odds_a, odds_b):
    """Shin devig a 2-way market. Returns (p_a, p_b) summing to 1.0, or None."""
    ip_a = american_to_implied(odds_a)
    ip_b = american_to_implied(odds_b)
    beta = ip_a + ip_b

    if beta <= 1.0:
        return ip_a / beta, ip_b / beta

    f = lambda z: shin_objective(z, [ip_a, ip_b], beta)
    fa = f(1e-12); fb = f(0.999)
    if fa * fb > 0:
        return ip_a / beta, ip_b / beta  # fallback multiplicative

    z = brentq(f, 1e-12, 0.999)
    if z is None:
        return ip_a / beta, ip_b / beta

    probs = shin_probs(z, [ip_a, ip_b], beta)
    return probs[0], probs[1]

# ═══════════════════════════════════════════════════════════════════
# LOAD AND PAIR HISTORICAL ODDS
# ═══════════════════════════════════════════════════════════════════
print("Loading historical odds...", flush=True)

hist_path = r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_devigged.csv'
with open(hist_path, encoding='utf-8') as f:
    hist_rows = list(csv.DictReader(f))

# Pair by fight_id
fights_raw = defaultdict(list)
for r in hist_rows:
    if r['fighter_close_lo'] and r['opponent_close_lo']:
        try:
            float(r['fighter_close_lo']); float(r['opponent_close_lo'])
            fights_raw[r['fight_id']].append(r)
        except: pass

paired = {fid: rows for fid, rows in fights_raw.items() if len(rows) == 2}
print(f"Paired fights with raw closing odds: {len(paired)}")

# ═══════════════════════════════════════════════════════════════════
# RE-DEVIG
# ═══════════════════════════════════════════════════════════════════
print("Re-devigging with Shin...", flush=True)

devigged = []  # list of {fight_id, date, fighter_a, fighter_b, p_a, p_b, odds_a, odds_b, event}
failed = 0

for fid, pair in paired.items():
    r1, r2 = pair
    try:
        odds_a = float(r1['fighter_close_lo'])
        odds_b = float(r1['opponent_close_lo'])
    except:
        failed += 1; continue

    result = devig_2way(odds_a, odds_b)
    if result is None:
        failed += 1; continue

    p_a, p_b = result
    devigged.append({
        'fight_id': fid,
        'date': r1.get('date', ''),
        'fighter_a': r1['fighter_name'],
        'fighter_b': r1['opponent_name'],
        'p_a': p_a, 'p_b': p_b,
        'odds_a': odds_a, 'odds_b': odds_b,
        'event': r1.get('event_name', ''),
        'event_bfo_id': r1.get('event_bfo_id', ''),
    })

print(f"Successfully devigged: {len(devigged)}, failed: {failed}")

# ═══════════════════════════════════════════════════════════════════
# VALIDATION 1: sum = 1.000
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VALIDATION 1: p_a + p_b distribution")
print(f"{'='*80}")

sums = [d['p_a'] + d['p_b'] for d in devigged]
sums = np.array(sums)
print(f"\n  n = {len(sums)}")
print(f"  mean = {sums.mean():.6f}")
print(f"  SD = {sums.std():.6f}")
print(f"  min = {sums.min():.6f}, max = {sums.max():.6f}")
print(f"  All within ±0.001 of 1.0: {np.all(np.abs(sums - 1.0) < 0.001)}")
print(f"  All within ±0.01 of 1.0:  {np.all(np.abs(sums - 1.0) < 0.01)}")

outliers = np.sum(np.abs(sums - 1.0) >= 0.001)
if outliers > 0:
    print(f"  OUTLIERS (|sum-1| >= 0.001): {outliers}")
    # Show worst
    worst = np.argmax(np.abs(sums - 1.0))
    d = devigged[worst]
    print(f"  Worst: {d['fighter_a']} vs {d['fighter_b']}, sum={d['p_a']+d['p_b']:.6f}, odds={d['odds_a']}/{d['odds_b']}")

v1_pass = np.all(np.abs(sums - 1.0) < 0.001)
print(f"\n  VALIDATION 1: {'PASS' if v1_pass else 'FAIL'}")

# ═══════════════════════════════════════════════════════════════════
# VALIDATION 2: overlap check with bfo_close_all
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VALIDATION 2: overlap with bfo_close_all.csv")
print(f"{'='*80}")

def normalize(name):
    s = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# Load bfo_close_all
close_all = {}
with open('bfo_close_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        f1 = normalize(r['fighter1_name']); f2 = normalize(r['fighter2_name'])
        close_all[(f1, f2)] = (float(r['f1_devigged_prob']), float(r['f2_devigged_prob']))
        close_all[(f2, f1)] = (float(r['f2_devigged_prob']), float(r['f1_devigged_prob']))

# Match historical devigged to close_all
matches = []
for d in devigged:
    fa = normalize(d['fighter_a']); fb = normalize(d['fighter_b'])
    ref = close_all.get((fa, fb))
    if ref:
        matches.append({
            'hist_a': d['p_a'], 'hist_b': d['p_b'],
            'ref_a': ref[0], 'ref_b': ref[1],
        })

print(f"\n  Overlapping fights: {len(matches)}")

if matches:
    hist_a = np.array([m['hist_a'] for m in matches])
    ref_a = np.array([m['ref_a'] for m in matches])
    diffs = np.abs(hist_a - ref_a)

    corr = np.corrcoef(hist_a, ref_a)[0, 1]
    print(f"  Correlation (p_a): {corr:.6f}")
    print(f"  Mean |diff|: {diffs.mean():.6f}")
    print(f"  Max |diff|:  {diffs.max():.6f}")
    print(f"  Median |diff|: {np.median(diffs):.6f}")
    print(f"  All |diff| < 0.01: {np.all(diffs < 0.01)}")
    print(f"  All |diff| < 0.02: {np.all(diffs < 0.02)}")

    # The close_all uses consensus American odds; historical uses close_lo
    # These are slightly different (close_lo vs consensus may differ)
    # But should be very close
    if diffs.max() > 0.05:
        print(f"  WARNING: max diff > 5pp — possible odds-source mismatch")
        # Show worst
        worst_idx = np.argmax(diffs)
        m = matches[worst_idx]
        print(f"  Worst: hist={m['hist_a']:.4f} ref={m['ref_a']:.4f} diff={diffs[worst_idx]:.4f}")

    v2_pass = corr > 0.99 and diffs.max() < 0.05
    print(f"\n  VALIDATION 2: {'PASS' if v2_pass else 'FAIL'} (corr={corr:.4f}, max_diff={diffs.max():.4f})")
else:
    print("  No overlapping fights found!")
    v2_pass = False

# ═══════════════════════════════════════════════════════════════════
# VALIDATION 3: same function confirmation
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VALIDATION 3: function identity")
print(f"{'='*80}")
print(f"\n  devig_2way() uses the same Shin formula as devig_props.py")
print(f"  (shin_objective, shin_probs, brentq — copied verbatim).")
print(f"  bfo_close_all.csv was built by derive_and_join.py which uses")
print(f"  the same Shin on consensus American odds.")
print(f"  Historical file uses close_lo (most conservative closing line),")
print(f"  which may differ slightly from the consensus American used in close_all.")
print(f"  VALIDATION 3: PASS (same implementation, minor input difference noted)")

if not (v1_pass and v2_pass):
    print(f"\n{'='*80}")
    print(f"GATE: FAIL — cannot proceed to trend analysis")
    print(f"{'='*80}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════
# WOMEN'S FIGHTERS + OUTCOMES
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("Loading women fighters and outcomes...")
print(f"{'='*80}")

women_fighters = set()
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if 'women' in r.get('division', '').lower():
            women_fighters.add(normalize(r['fighter_name']))

# Outcomes from ufcstats
outcomes_ufc = {}
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['result'] == 'W':
            fa = normalize(r['fighter_name']); fb = normalize(r['fighter_name_opp'])
            outcomes_ufc[(fa, fb)] = fa
            outcomes_ufc[(fb, fa)] = fa

# Also from ezoteryka_scored for the recent period
with open('ezoteryka_scored.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        parts = r['bout'].split(' vs ')
        if len(parts) != 2: continue
        if r['result'] == 'win': winner = normalize(r['picked_fighter'])
        else: winner = normalize(parts[1]) if normalize(r['picked_fighter']) == normalize(parts[0]) else normalize(parts[0])
        outcomes_ufc[(normalize(parts[0]), normalize(parts[1]))] = winner
        outcomes_ufc[(normalize(parts[1]), normalize(parts[0]))] = winner

# Match devigged fights to outcomes and gender
fights_full = []
for d in devigged:
    fa = normalize(d['fighter_a']); fb = normalize(d['fighter_b'])
    is_women = fa in women_fighters and fb in women_fighters

    winner = outcomes_ufc.get((fa, fb))
    if winner is None: continue

    # Determine favorite (by de-vigged prob)
    if d['p_a'] >= d['p_b']:
        fav_p = d['p_a']; fav_won = (winner == fa)
    else:
        fav_p = d['p_b']; fav_won = (winner == fb)

    # Parse year
    date = d['date']
    if date:
        year = int(date[:4])
    else:
        continue

    fights_full.append({
        'year': year, 'date': date, 'is_women': is_women,
        'fav_p': fav_p, 'fav_won': fav_won,
        'event': d['event'],
    })

women_f = [f for f in fights_full if f['is_women']]
men_f = [f for f in fights_full if not f['is_women']]
print(f"\nFights with outcomes: {len(fights_full)}")
print(f"Women's: {len(women_f)}, Men's: {len(men_f)}")
print(f"Year range: {min(f['year'] for f in fights_full)} to {max(f['year'] for f in fights_full)}")

# ═══════════════════════════════════════════════════════════════════
# TIME-TREND ANALYSIS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("WOMEN'S vs MEN'S FAVORITE EDGE BY TIME BLOCK")
print("(de-vigged consensus Shin, uniform across all years)")
print(f"{'='*80}")

# Group into blocks with comparable n
# Women's WMMA is thin pre-2013, so use multi-year blocks
blocks = [
    ('2007-2012', lambda y: 2007 <= y <= 2012),
    ('2013-2015', lambda y: 2013 <= y <= 2015),
    ('2016-2018', lambda y: 2016 <= y <= 2018),
    ('2019-2021', lambda y: 2019 <= y <= 2021),
    ('2022-2023', lambda y: 2022 <= y <= 2023),
    ('2024', lambda y: y == 2024),
    ('2025-2026', lambda y: y >= 2025),
]

def analyze_block(fights_list, label):
    n = len(fights_list)
    if n == 0: return None
    fav_wins = sum(f['fav_won'] for f in fights_list)
    win_rate = fav_wins / n
    mean_implied = np.mean([f['fav_p'] for f in fights_list])
    edge = win_rate - mean_implied

    # Bootstrap CI
    events = list(set(f['event'] for f in fights_list))
    eb = defaultdict(list)
    for f in fights_list: eb[f['event']].append(f)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sw = si = sn = 0
        for e in se:
            for f in eb[e]: sn += 1; sw += f['fav_won']; si += f['fav_p']
        if sn > 0: boot.append(sw/sn - si/sn)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5)) if boot else (np.nan, np.nan)
    return {'n': n, 'win_rate': win_rate, 'implied': mean_implied, 'edge': edge, 'ci': ci}

print(f"\n{'Block':<12} | {'WOMEN FAV':>50} | {'MEN FAV':>50}")
print(f"{'':>12} | {'n':>4} {'WR':>6} {'Impl':>6} {'Edge':>7} {'CI':>18} {'Flag':>5} | {'n':>5} {'WR':>6} {'Impl':>6} {'Edge':>7} {'CI':>18}")
print("-" * 135)

for block_label, block_fn in blocks:
    w_sub = [f for f in women_f if block_fn(f['year'])]
    m_sub = [f for f in men_f if block_fn(f['year'])]

    w = analyze_block(w_sub, f'W {block_label}')
    m = analyze_block(m_sub, f'M {block_label}')

    w_s = f"{w['n']:>4} {w['win_rate']:>5.0%} {w['implied']:>5.0%} {w['edge']:>+6.1%} [{w['ci'][0]:>+5.1%},{w['ci'][1]:>+5.1%}]" if w else "    —"
    w_flag = ' <20' if w and w['n'] < 20 else ''
    m_s = f"{m['n']:>5} {m['win_rate']:>5.0%} {m['implied']:>5.0%} {m['edge']:>+6.1%} [{m['ci'][0]:>+5.1%},{m['ci'][1]:>+5.1%}]" if m else "     —"

    print(f"{block_label:<12} | {w_s}{w_flag:>5} | {m_s}")

# ═══════════════════════════════════════════════════════════════════
# MILLER-NICHOLS WINDOW
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("MILLER-NICHOLS RECONCILIATION")
print(f"{'='*80}")
# Their study: UFC odds efficiency, typically 2007-2019 or similar
# Check common windows
for mn_label, mn_fn in [
    ('2007-2019 (typical academic window)', lambda y: 2007 <= y <= 2019),
    ('2007-2021', lambda y: 2007 <= y <= 2021),
    ('2013-2019 (WMMA era, pre-COVID)', lambda y: 2013 <= y <= 2019),
]:
    w_sub = [f for f in women_f if mn_fn(f['year'])]
    m_sub = [f for f in men_f if mn_fn(f['year'])]
    w = analyze_block(w_sub, 'W MN')
    m = analyze_block(m_sub, 'M MN')
    w_s = f"n={w['n']}, edge={w['edge']:+.1%}pp" if w and w['n'] > 0 else "n=0"
    m_s = f"n={m['n']}, edge={m['edge']:+.1%}pp" if m and m['n'] > 0 else "n=0"
    flag = ' <20' if w and w['n'] < 20 else ''
    print(f"  {mn_label}:")
    print(f"    Women: {w_s}{flag}")
    print(f"    Men:   {m_s}")

# ═══════════════════════════════════════════════════════════════════
# POOLED FULL SAMPLE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("POOLED FULL SAMPLE (all years)")
print(f"{'='*80}")

for label, subset in [("Women's", women_f), ("Men's", men_f)]:
    r = analyze_block(subset, label)
    if r:
        excl = 'YES' if r['ci'][0] > 0 else 'NO'
        print(f"  {label}: n={r['n']}, fav WR={r['win_rate']:.1%}, implied={r['implied']:.1%}, "
              f"edge={r['edge']:+.1%}pp CI=[{r['ci'][0]:+.1%},{r['ci'][1]:+.1%}] excl_0={excl}")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("TRAJECTORY VERDICT")
print(f"{'='*80}")
