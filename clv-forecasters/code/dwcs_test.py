#!/usr/bin/env python3
"""DWCS efficiency test with Sherdog outcomes."""
import csv, re, sys, unicodedata, math
import numpy as np
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')
import os; os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
rng = np.random.RandomState(SEED)

def normalize(name):
    s = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()
def last_name(n):
    parts = normalize(n).split()
    return parts[-1] if parts else ''
def names_match(a, b):
    na, nb = normalize(a), normalize(b)
    if na == nb: return True
    la, lb = last_name(a), last_name(b)
    if la == lb and na and nb and na[0] == nb[0]: return True
    if len(na) > 4 and len(nb) > 4 and (na in nb or nb in na): return True
    return False
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

# Load Sherdog DWCS results
with open('dwcs_sherdog_results.csv', encoding='utf-8') as f:
    sherdog = list(csv.DictReader(f))
print(f"Sherdog DWCS results: {len(sherdog)}")

# Load BFO DWCS odds
dwcs_kw = ['contender', 'dwcs', 'dana white']
hist_path = r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_devigged.csv'
# Use bfo_odds_raw (not devigged — DWCS fighters have no UFCStats ID)
raw_path = r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_raw.csv'
fights_raw = defaultdict(list)
with open(raw_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if not any(k in r.get('event_name','').lower() for k in dwcs_kw): continue
        if r['fighter_close_lo'] and r['opponent_close_lo']:
            try:
                float(r['fighter_close_lo']); float(r['opponent_close_lo'])
                # Use fighter_name + opponent_name as a pseudo fight_id
                fid = r['event_bfo_id'] + '_' + r['fighter_name']
                fights_raw[fid].append(r)
            except: pass

# Devig DWCS odds — each row in raw is one fighter, with opponent odds inline
odds_lookup = {}
seen_pairs = set()
with open(raw_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if not any(k in r.get('event_name','').lower() for k in dwcs_kw): continue
        if not r['fighter_close_lo'] or not r['opponent_close_lo']: continue
        try:
            lo_a = float(r['fighter_close_lo']); lo_b = float(r['opponent_close_lo'])
        except: continue
        fa = normalize(r['fighter_name']); fb = normalize(r['opponent_name'])
        pair = tuple(sorted([fa, fb]))
        if pair in seen_pairs: continue
        seen_pairs.add(pair)
        hi_a = float(r.get('fighter_close_hi', lo_a))
        hi_b = float(r.get('opponent_close_hi', lo_b))
        mid_a = (lo_a + hi_a) / 2; mid_b = (lo_b + hi_b) / 2
        if mid_a<0 and mid_b<0: continue
        if mid_a==0 or mid_b==0: continue
        pa, pb = dv(mid_a, mid_b)
        odds_lookup[(fa, fb)] = (pa, pb)
        odds_lookup[(fb, fa)] = (pb, pa)

print(f"DWCS fights with odds: {len(odds_lookup)//2}")

# Join
joined = []
for s in sherdog:
    wn = normalize(s['winner']); ln = normalize(s['loser'])
    odds = odds_lookup.get((wn, ln))
    if not odds:
        for (k1, k2), v in odds_lookup.items():
            if names_match(wn, k1) and names_match(ln, k2):
                odds = v; break
    if not odds: continue
    winner_p = odds[0]
    fav_p = max(odds[0], odds[1])
    fav_won = winner_p >= 0.5
    joined.append({'fav_p': fav_p, 'fav_won': fav_won, 'event': s['event']})

print(f"Joined (odds+outcome): {len(joined)}")

# Main UFC comparison
outcomes = {}
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['result'] == 'W':
            fa=normalize(r['fighter_name']); fb=normalize(r['fighter_name_opp'])
            outcomes[(fa,fb)]=fa; outcomes[(fb,fa)]=fa

main_raw = defaultdict(list)
with open(hist_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if any(k in r.get('event_name','').lower() for k in dwcs_kw): continue
        if not r.get('event_name','').lower().startswith('ufc'): continue
        if r['fighter_close_lo'] and r['opponent_close_lo']:
            try: float(r['fighter_close_lo']); main_raw[r['fight_id']].append(r)
            except: pass

main_joined = []
for fid, rows in main_raw.items():
    if len(rows) != 2: continue
    r1 = rows[0]
    lo_a=float(r1['fighter_close_lo']); hi_a=float(r1['fighter_close_hi'])
    lo_b=float(r1['opponent_close_lo']); hi_b=float(r1['opponent_close_hi'])
    mid_a=(lo_a+hi_a)/2; mid_b=(lo_b+hi_b)/2
    if mid_a<0 and mid_b<0: continue
    if mid_a==0 or mid_b==0: continue
    pa, pb = dv(mid_a, mid_b)
    fa=normalize(r1['fighter_name']); fb=normalize(r1['opponent_name'])
    winner = outcomes.get((fa,fb))
    if not winner: continue
    fav_p = max(pa, pb)
    fav_won = (winner==fa and pa>=pb) or (winner==fb and pb>=pa)
    main_joined.append({'fav_p': fav_p, 'fav_won': fav_won, 'event': r1.get('event_name','')})

print(f"Main UFC: {len(main_joined)}")

# Analysis
def analyze(subset, label):
    n = len(subset)
    if n == 0: return None
    fw = sum(f['fav_won'] for f in subset)
    wr = fw/n; impl = np.mean([f['fav_p'] for f in subset]); edge = wr - impl
    events = list(set(f['event'] for f in subset))
    eb = defaultdict(list)
    for f in subset: eb[f['event']].append(f)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sw=si=sn=0
        for e in se:
            for f in eb[e]: sn+=1; sw+=f['fav_won']; si+=f['fav_p']
        if sn>0: boot.append(sw/sn - si/sn)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))
    excl = 'YES' if ci[0] > 0 else 'NO'
    print(f"\n  {label} (n={n}):")
    print(f"    Fav win rate: {wr:.1%} ({fw}/{n})")
    print(f"    Implied:      {impl:.1%}")
    print(f"    Edge:         {edge:+.1%}pp CI=[{ci[0]:+.1%},{ci[1]:+.1%}] excl_0={excl}")
    return {'edge': edge, 'ci': ci}

print(f"\n{'='*70}")
print("DWCS vs MAIN UFC: FAVORITE EFFICIENCY")
print(f"{'='*70}")

d = analyze(joined, "DWCS favorites")
m = analyze(main_joined, "Main UFC favorites")

if d and m:
    diff = d['edge'] - m['edge']
    print(f"\n  DIFFERENCE (DWCS - main): {diff:+.1%}pp")

# Buckets
print(f"\n  DWCS by implied-prob bucket:")
for lo, hi, label in [(0.50, 0.65, '50-65%'), (0.65, 0.80, '65-80%'), (0.80, 1.01, '80%+')]:
    sub = [f for f in joined if lo <= f['fav_p'] < hi]
    if len(sub) >= 5:
        wr = sum(f['fav_won'] for f in sub)/len(sub)
        impl = np.mean([f['fav_p'] for f in sub])
        print(f"    {label}: n={len(sub)}, WR={wr:.0%}, impl={impl:.0%}, edge={wr-impl:+.1%}pp")

print(f"\n{'='*70}")
print("VERDICT")
print(f"{'='*70}")
if d:
    if d['ci'][0] > 0:
        print(f"\n  DWCS favorites are underpriced (edge {d['edge']:+.1%}pp, CI excl 0).")
    else:
        print(f"\n  DWCS favorite edge ({d['edge']:+.1%}pp) does not exclude zero.")
        print(f"  No detectable inefficiency vs main UFC.")
