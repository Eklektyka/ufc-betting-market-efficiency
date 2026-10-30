#!/usr/bin/env python3
"""
Women's-fav time trend: uniform midpoint de-vig across all eras.
Then separate profitability test at best-line.
"""
import csv, os, re, sys, unicodedata, math
import numpy as np
from collections import defaultdict
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
rng = np.random.RandomState(SEED)

def normalize(name):
    s = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()
def american_to_implied(o):
    return -o/(-o+100) if o < 0 else 100/(o+100)
def american_to_decimal(o):
    return 1+o/100 if o > 0 else 1+100/abs(o)

def shin_objective(z, pis, beta):
    return sum((math.sqrt(z**2+4*(1-z)*pi**2/beta)-z)/(2*(1-z)) for pi in pis) - 1
def shin_probs(z, pis, beta):
    return [(math.sqrt(z**2+4*(1-z)*pi**2/beta)-z)/(2*(1-z)) for pi in pis]
def brentq(f, a, b, tol=1e-10):
    fa, fb = f(a), f(b)
    if fa*fb > 0: return None
    for _ in range(200):
        c=(a+b)/2; fc=f(c)
        if abs(fc)<tol: return c
        if fa*fc<0: b=c; fb=fc
        else: a=c; fa=fc
    return (a+b)/2

def devig_2way(oa, ob):
    ia=american_to_implied(oa); ib=american_to_implied(ob)
    beta=ia+ib
    if beta<=1: return ia/beta, ib/beta
    z=brentq(lambda z: shin_objective(z,[ia,ib],beta), 1e-12, 0.999)
    if z is None: return ia/beta, ib/beta
    return shin_probs(z,[ia,ib],beta)

# Women fighters
women_fighters = set()
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if 'women' in r.get('division','').lower():
            women_fighters.add(normalize(r['fighter_name']))

# Outcomes
outcomes = {}
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['result']=='W':
            fa=normalize(r['fighter_name']); fb=normalize(r['fighter_name_opp'])
            outcomes[(fa,fb)]=fa; outcomes[(fb,fa)]=fa
with open('ezoteryka_scored.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        parts=r['bout'].split(' vs ')
        if len(parts)!=2: continue
        w=normalize(r['picked_fighter']) if r['result']=='win' else (normalize(parts[1]) if normalize(r['picked_fighter'])==normalize(parts[0]) else normalize(parts[0]))
        outcomes[(normalize(parts[0]),normalize(parts[1]))]=w
        outcomes[(normalize(parts[1]),normalize(parts[0]))]=w

# ═══════════════════════════════════════════════════════════════════
# LOAD + MIDPOINT DE-VIG ALL HISTORICAL FIGHTS
# ═══════════════════════════════════════════════════════════════════
print("Loading and de-vigging from midpoint(close_lo, close_hi)...", flush=True)

hist_path = r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_devigged.csv'
fights_raw = defaultdict(list)
with open(hist_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['fighter_close_lo'] and r['fighter_close_hi'] and r['opponent_close_lo'] and r['opponent_close_hi']:
            try:
                float(r['fighter_close_lo']); float(r['fighter_close_hi'])
                float(r['opponent_close_lo']); float(r['opponent_close_hi'])
                fights_raw[r['fight_id']].append(r)
            except: pass

devigged = []
bad_data = 0
for fid, rows in fights_raw.items():
    if len(rows) != 2: continue
    r1 = rows[0]
    lo_a = float(r1['fighter_close_lo']); hi_a = float(r1['fighter_close_hi'])
    lo_b = float(r1['opponent_close_lo']); hi_b = float(r1['opponent_close_hi'])

    # Midpoint in American odds
    mid_a = (lo_a + hi_a) / 2
    mid_b = (lo_b + hi_b) / 2

    # Sanity: both sides should not be negative (both favored = bad data)
    if mid_a < 0 and mid_b < 0:
        bad_data += 1; continue
    # Skip if either is exactly 0 (undefined)
    if mid_a == 0 or mid_b == 0:
        bad_data += 1; continue

    pa, pb = devig_2way(mid_a, mid_b)
    date = r1.get('date', '')
    if not date: continue

    fa = normalize(r1['fighter_name']); fb = normalize(r1['opponent_name'])
    is_women = fa in women_fighters and fb in women_fighters

    winner = outcomes.get((fa, fb))
    if winner is None: continue

    if pa >= pb:
        fav_p = pa; fav_won = (winner == fa)
    else:
        fav_p = pb; fav_won = (winner == fb)

    year = int(date[:4])

    devigged.append({
        'year': year, 'date': date, 'is_women': is_women,
        'fav_p': fav_p, 'fav_won': fav_won,
        'event': r1.get('event_name', ''),
        'fa': fa, 'fb': fb, 'mid_a': mid_a, 'mid_b': mid_b,
        'pa': pa, 'pb': pb,
    })

print(f"De-vigged (midpoint): {len(devigged)}, bad data skipped: {bad_data}")

# ═══════════════════════════════════════════════════════════════════
# OVERLAP CHECK vs bfo_close_all
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("OVERLAP CHECK: midpoint de-vig vs bfo_close_all consensus")
print(f"{'='*80}")

close_all = {}
with open('bfo_close_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        f1 = normalize(r['fighter1_name']); f2 = normalize(r['fighter2_name'])
        date = r['event_date']
        close_all[(date, f1, f2)] = float(r['f1_devigged_prob'])
        close_all[(date, f2, f1)] = float(r['f2_devigged_prob'])

diffs = []
for d in devigged:
    ref = close_all.get((d['date'], d['fa'], d['fb']))
    if ref is not None:
        diffs.append(abs(d['pa'] - ref))

diffs = np.array(diffs)
print(f"\n  Overlapping fights: {len(diffs)}")
print(f"  Mean |diff|:   {diffs.mean():.4f}")
print(f"  Median |diff|: {np.median(diffs):.4f}")
print(f"  Max |diff|:    {diffs.max():.4f}")
print(f"  All < 0.02:    {np.all(diffs < 0.02)}")
print(f"  All < 0.03:    {np.all(diffs < 0.03)}")
print(f"  > 0.03:        {np.sum(diffs > 0.03)}")

# Compare to the close_lo version (which had median 0.0077)
print(f"\n  (close_lo version had median=0.0077; midpoint should be tighter)")

# ═══════════════════════════════════════════════════════════════════
# EFFICIENCY TREND
# ═══════════════════════════════════════════════════════════════════
women_f = [d for d in devigged if d['is_women']]
men_f = [d for d in devigged if not d['is_women']]
print(f"\n  Women's fights: {len(women_f)}, Men's: {len(men_f)}")
print(f"  Year range: {min(d['year'] for d in devigged)} to {max(d['year'] for d in devigged)}")

def analyze_block(fights, label):
    n = len(fights)
    if n == 0: return None
    fw = sum(f['fav_won'] for f in fights)
    wr = fw / n
    impl = np.mean([f['fav_p'] for f in fights])
    edge = wr - impl
    events = list(set(f['event'] for f in fights))
    eb = defaultdict(list)
    for f in fights: eb[f['event']].append(f)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sw = si = sn = 0
        for e in se:
            for f in eb[e]: sn += 1; sw += f['fav_won']; si += f['fav_p']
        if sn > 0: boot.append(sw/sn - si/sn)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5)) if boot else (np.nan, np.nan)
    return {'n': n, 'wr': wr, 'impl': impl, 'edge': edge, 'ci': ci}

print(f"\n{'='*80}")
print("EFFICIENCY TREND: WOMEN'S vs MEN'S FAVORITE EDGE BY TIME BLOCK")
print("Price definition: midpoint(close_lo, close_hi), Shin de-vig, uniform all eras")
print(f"{'='*80}")

blocks = [
    ('2007-2012', lambda y: 2007<=y<=2012),
    ('2013-2015', lambda y: 2013<=y<=2015),
    ('2016-2018', lambda y: 2016<=y<=2018),
    ('2019-2021', lambda y: 2019<=y<=2021),
    ('2022-2023', lambda y: 2022<=y<=2023),
    ('2024', lambda y: y==2024),
    ('2025-2026', lambda y: y>=2025),
]

print(f"\n{'Block':<12} | {'WOMEN FAV':>55} | {'MEN FAV':>55}")
print(f"{'':>12} | {'n':>4} {'WR':>6} {'Impl':>6} {'Edge':>7} {'CI':>20} {'Flag':>5} | {'n':>5} {'WR':>6} {'Impl':>6} {'Edge':>7} {'CI':>20}")
print("-" * 145)

for bl, fn in blocks:
    w = analyze_block([f for f in women_f if fn(f['year'])], f'W {bl}')
    m = analyze_block([f for f in men_f if fn(f['year'])], f'M {bl}')

    if w and w['n'] > 0:
        ws = f"{w['n']:>4} {w['wr']:>5.0%} {w['impl']:>5.0%} {w['edge']:>+6.1%} [{w['ci'][0]:>+6.1%},{w['ci'][1]:>+6.1%}]"
        wf = ' <20' if w['n'] < 20 else ''
    else:
        ws = f"   0    —     —      —                    "; wf = ''

    if m and m['n'] > 0:
        ms = f"{m['n']:>5} {m['wr']:>5.0%} {m['impl']:>5.0%} {m['edge']:>+6.1%} [{m['ci'][0]:>+6.1%},{m['ci'][1]:>+6.1%}]"
    else:
        ms = f"     0    —     —      —"

    print(f"{bl:<12} | {ws}{wf:>5} | {ms}")

# ─── Miller-Nichols ───
print(f"\n{'='*80}")
print("MILLER-NICHOLS RECONCILIATION")
print(f"{'='*80}")

for label, fn in [
    ('2007-2019 (typical academic)', lambda y: 2007<=y<=2019),
    ('2013-2019 (WMMA era, pre-COVID)', lambda y: 2013<=y<=2019),
    ('2022-2026 (recent)', lambda y: y>=2022),
]:
    w = analyze_block([f for f in women_f if fn(f['year'])], f'W {label}')
    m = analyze_block([f for f in men_f if fn(f['year'])], f'M {label}')
    ws = f"n={w['n']}, edge={w['edge']:+.1%}pp CI=[{w['ci'][0]:+.1%},{w['ci'][1]:+.1%}]" if w and w['n']>0 else "n=0"
    ms = f"n={m['n']}, edge={m['edge']:+.1%}pp CI=[{m['ci'][0]:+.1%},{m['ci'][1]:+.1%}]" if m and m['n']>0 else "n=0"
    flag = ' <20' if w and w['n']<20 else ''
    print(f"\n  {label}:")
    print(f"    Women: {ws}{flag}")
    print(f"    Men:   {ms}")

# ─── Pooled ───
print(f"\n{'='*80}")
print("POOLED FULL SAMPLE")
print(f"{'='*80}")

for label, subset in [("Women's", women_f), ("Men's", men_f)]:
    r = analyze_block(subset, label)
    if r:
        excl = 'YES' if r['ci'][0]>0 else 'NO'
        print(f"  {label}: n={r['n']}, fav WR={r['wr']:.1%}, impl={r['impl']:.1%}, "
              f"edge={r['edge']:+.1%}pp CI=[{r['ci'][0]:+.1%},{r['ci'][1]:+.1%}] excl_0={excl}")

# ─── Trajectory verdict ───
print(f"\n{'='*80}")
print("TRAJECTORY VERDICT")
print(f"{'='*80}")

# ═══════════════════════════════════════════════════════════════════
# PROFITABILITY: best-line ROI (separate from efficiency)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("PROFITABILITY: WOMEN'S FAVORITE ROI AT BEST-LINE")
print("(separate from efficiency test above — this uses p_fair/best_line)")
print(f"{'='*80}")

# For profitability, use the RECENT sample where we have best-line data
# bfo_close_all has best_line_a, best_line_b, p_fair_a, p_fair_b
profit_fights = []
with open('bfo_close_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        f1 = normalize(r['fighter1_name']); f2 = normalize(r['fighter2_name'])
        is_women = f1 in women_fighters and f2 in women_fighters

        p_a = float(r['p_fair_a']); p_b = float(r['p_fair_b'])
        best_a = int(r['best_line_a']); best_b = int(r['best_line_b'])
        date = r['event_date']

        # Fav = higher p_fair
        if p_a >= p_b:
            fav_best = best_a; fav_p = p_a
        else:
            fav_best = best_b; fav_p = p_b

        winner = outcomes.get((f1, f2))
        if winner is None: continue

        if p_a >= p_b:
            fav_won = (winner == f1)
        else:
            fav_won = (winner == f2)

        dec = american_to_decimal(fav_best)
        profit = (dec - 1) * 100 if fav_won else -100

        profit_fights.append({
            'is_women': is_women, 'profit': profit, 'fav_won': fav_won,
            'fav_p': fav_p, 'fav_best': fav_best, 'event': r['event_name'],
            'date': date,
        })

for label, subset in [("Women's favs (best-line)", [f for f in profit_fights if f['is_women']]),
                       ("Men's favs (best-line)", [f for f in profit_fights if not f['is_women']])]:
    n = len(subset)
    if n == 0: continue
    total_profit = sum(f['profit'] for f in subset)
    roi = total_profit / (n * 100)
    wr = sum(f['fav_won'] for f in subset) / n
    mean_p = np.mean([f['fav_p'] for f in subset])
    mean_line = np.mean([f['fav_best'] for f in subset])

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
    excl = 'YES' if ci[0] > 0 else 'NO'

    print(f"\n  {label}:")
    print(f"    n={n}, WR={wr:.1%}, mean p_fair={mean_p:.1%}, mean best_line={mean_line:+.0f}")
    print(f"    Profit: ${total_profit:+,.0f}, ROI={roi:+.1%} CI=[{ci[0]:+.1%},{ci[1]:+.1%}] excl_0={excl}")
