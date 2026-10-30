#!/usr/bin/env python3
"""DWCS vs main-roster efficiency test."""
import csv, os, re, sys, unicodedata, math
import numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
SEED = 67; N_BOOT = 5000
rng = np.random.RandomState(SEED)

def normalize(name):
    s = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()
def ai(o): return -o/(-o+100) if o < 0 else 100/(o+100)
def shin_obj(z, pis, beta):
    return sum((math.sqrt(z**2+4*(1-z)*pi**2/beta)-z)/(2*(1-z)) for pi in pis) - 1
def shin_p(z, pis, beta):
    return [(math.sqrt(z**2+4*(1-z)*pi**2/beta)-z)/(2*(1-z)) for pi in pis]
def brentq(f, a, b, tol=1e-10):
    fa, fb = f(a), f(b)
    if fa*fb > 0: return None
    for _ in range(200):
        c=(a+b)/2; fc=f(c)
        if abs(fc)<tol: return c
        if fa*fc<0: b=c
        else: a=c
    return (a+b)/2
def dv(oa, ob):
    ia=ai(oa); ib=ai(ob); beta=ia+ib
    if beta<=1: return ia/beta, ib/beta
    z=brentq(lambda z: shin_obj(z,[ia,ib],beta), 1e-12, 0.999)
    if z is None: return ia/beta, ib/beta
    return shin_p(z,[ia,ib],beta)
def american_to_decimal(o):
    return 1+o/100 if o > 0 else 1+100/abs(o)

# Outcomes from UFCStats
outcomes = {}
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['result'] == 'W':
            fa = normalize(r['fighter_name']); fb = normalize(r['fighter_name_opp'])
            outcomes[(fa, fb)] = fa; outcomes[(fb, fa)] = fa

# Load historical odds and classify DWCS vs main
dwcs_kw = ['contender', 'dwcs', 'dana white']
hist_path = r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_devigged.csv'
fights_raw = defaultdict(list)
with open(hist_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['fighter_close_lo'] and r['fighter_close_hi'] and r['opponent_close_lo'] and r['opponent_close_hi']:
            try:
                float(r['fighter_close_lo']); float(r['fighter_close_hi'])
                fights_raw[r['fight_id']].append(r)
            except: pass

fights = []
for fid, rows in fights_raw.items():
    if len(rows) != 2: continue
    r1 = rows[0]
    lo_a = float(r1['fighter_close_lo']); hi_a = float(r1['fighter_close_hi'])
    lo_b = float(r1['opponent_close_lo']); hi_b = float(r1['opponent_close_hi'])
    mid_a = (lo_a+hi_a)/2; mid_b = (lo_b+hi_b)/2
    if mid_a < 0 and mid_b < 0: continue
    if mid_a == 0 or mid_b == 0: continue

    pa, pb = dv(mid_a, mid_b)
    fa = normalize(r1['fighter_name']); fb = normalize(r1['opponent_name'])
    date = r1.get('date', '')
    if not date: continue
    event = r1.get('event_name', '')

    winner = outcomes.get((fa, fb))
    if winner is None: continue

    is_dwcs = any(k in event.lower() for k in dwcs_kw)
    fav_p = max(pa, pb)
    fav_won = (winner == fa and pa >= pb) or (winner == fb and pb >= pa)

    # Best line for the fav (most generous = close_hi)
    if pa >= pb:
        fav_best = hi_a
    else:
        fav_best = hi_b

    year = int(date[:4])

    fights.append({
        'is_dwcs': is_dwcs, 'fav_p': fav_p, 'fav_won': fav_won,
        'fav_best': fav_best, 'year': year, 'event': event, 'date': date,
    })

dwcs = [f for f in fights if f['is_dwcs']]
main = [f for f in fights if not f['is_dwcs']]
print(f"DWCS fights with odds+outcomes: {len(dwcs)}")
print(f"Main UFC fights: {len(main)}")
print(f"DWCS year range: {min(f['year'] for f in dwcs)}-{max(f['year'] for f in dwcs)}")

def analyze(subset, label):
    n = len(subset)
    if n == 0: print(f"\n  {label}: n=0"); return None
    fw = sum(f['fav_won'] for f in subset)
    wr = fw / n
    impl = np.mean([f['fav_p'] for f in subset])
    edge = wr - impl

    events = list(set(f['event'] for f in subset))
    eb = defaultdict(list)
    for f in subset: eb[f['event']].append(f)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sw = si = sn = 0
        for e in se:
            for f in eb[e]: sn += 1; sw += f['fav_won']; si += f['fav_p']
        if sn > 0: boot.append(sw/sn - si/sn)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))
    excl = ci[0] > 0

    print(f"\n  {label} (n={n}):")
    print(f"    Fav win rate: {wr:.1%} ({fw}/{n})")
    print(f"    Implied:      {impl:.1%}")
    print(f"    Edge:         {edge:+.1%}pp CI=[{ci[0]:+.1%},{ci[1]:+.1%}] excl_0={'YES' if excl else 'NO'}")
    return {'n': n, 'edge': edge, 'ci': ci, 'wr': wr, 'impl': impl}

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("1. FAVORITE EFFICIENCY: DWCS vs MAIN UFC")
print(f"{'='*70}")

d_res = analyze(dwcs, "DWCS favorites")
m_res = analyze(main, "Main UFC favorites")

if d_res and m_res:
    diff = d_res['edge'] - m_res['edge']
    # Bootstrap difference
    d_events = list(set(f['event'] for f in dwcs))
    m_events = list(set(f['event'] for f in main))
    d_eb = defaultdict(list); m_eb = defaultdict(list)
    for f in dwcs: d_eb[f['event']].append(f)
    for f in main: m_eb[f['event']].append(f)
    boot_diff = []
    for _ in range(N_BOOT):
        sd = rng.choice(d_events, size=len(d_events), replace=True)
        dw = di = dn = 0
        for e in sd:
            for f in d_eb[e]: dn+=1; dw+=f['fav_won']; di+=f['fav_p']
        d_val = (dw/dn - di/dn) if dn else 0
        sm = rng.choice(m_events, size=len(m_events), replace=True)
        mw = mi = mn = 0
        for e in sm:
            for f in m_eb[e]: mn+=1; mw+=f['fav_won']; mi+=f['fav_p']
        m_val = (mw/mn - mi/mn) if mn else 0
        boot_diff.append(d_val - m_val)
    diff_ci = (np.percentile(boot_diff, 2.5), np.percentile(boot_diff, 97.5))

    print(f"\n  DIFFERENCE (DWCS − main): {diff:+.1%}pp CI=[{diff_ci[0]:+.1%},{diff_ci[1]:+.1%}]")
    print(f"  CI excludes zero: {'YES' if diff_ci[0] > 0 else 'NO'}")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("2. FAVORITE-LONGSHOT BY BUCKET (DWCS)")
print(f"{'='*70}")

for lo, hi, label in [(0.50, 0.65, '50-65%'), (0.65, 0.80, '65-80%'), (0.80, 1.01, '80%+')]:
    sub = [f for f in dwcs if lo <= f['fav_p'] < hi]
    if len(sub) >= 10:
        wr = sum(f['fav_won'] for f in sub) / len(sub)
        impl = np.mean([f['fav_p'] for f in sub])
        print(f"  {label}: n={len(sub)}, WR={wr:.0%}, impl={impl:.0%}, edge={wr-impl:+.1%}pp")
    else:
        print(f"  {label}: n={len(sub)} (too few)")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("3. PROFITABILITY AT CLOSE")
print(f"{'='*70}")

for label, subset in [("DWCS fav", [f for f in dwcs]),
                       ("DWCS dog", dwcs)]:
    bets = []
    for f in subset:
        if label == "DWCS dog":
            # Bet the dog: profit if fav LOSES
            best = f['fav_best']  # this is fav's line; dog's line is the complement
            # We don't have the dog's best line directly; approximate
            # Dog profit = (dec_dog - 1) * 100 if dog wins, -100 if fav wins
            # Can't compute without dog's line. Use fav's line to infer.
            continue  # skip dog for now
        best = f['fav_best']
        if best == 0: continue
        dec = american_to_decimal(best)
        profit = (dec - 1) * 100 if f['fav_won'] else -100
        bets.append({'profit': profit, 'event': f['event']})

    if not bets: continue
    total = sum(b['profit'] for b in bets)
    roi = total / (len(bets) * 100)
    events = list(set(b['event'] for b in bets))
    eb2 = defaultdict(list)
    for b in bets: eb2[b['event']].append(b)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sp = sn = 0
        for e in se:
            for b in eb2[e]: sp += b['profit']; sn += 1
        boot.append(sp / (sn * 100) if sn > 0 else 0)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))

    print(f"\n  {label}: n={len(bets)}, ROI={roi:+.1%} CI=[{ci[0]:+.1%},{ci[1]:+.1%}]")
    print(f"  CI excludes zero: {'YES' if ci[0] > 0 else 'NO'}")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("4. TIME TREND")
print(f"{'='*70}")

for period, fn in [('2017-2019', lambda y: 2017<=y<=2019),
                    ('2020-2021', lambda y: 2020<=y<=2021),
                    ('2022-2024', lambda y: 2022<=y<=2024)]:
    sub = [f for f in dwcs if fn(f['year'])]
    if len(sub) >= 15:
        wr = sum(f['fav_won'] for f in sub) / len(sub)
        impl = np.mean([f['fav_p'] for f in sub])
        print(f"  {period}: n={len(sub)}, WR={wr:.0%}, impl={impl:.0%}, edge={wr-impl:+.1%}pp")
    else:
        print(f"  {period}: n={len(sub)} (thin)")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("VERDICT")
print(f"{'='*70}")
