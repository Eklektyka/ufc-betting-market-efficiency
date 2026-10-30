#!/usr/bin/env python3
"""Multiple comparisons check on women's-favorite 7-block analysis."""
import csv, os, re, sys, unicodedata, math
import numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 10000
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

women_fighters = set()
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if 'women' in r.get('division','').lower():
            women_fighters.add(normalize(r['fighter_name']))

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

# Build women's fights from midpoint de-vig
fights_raw = defaultdict(list)
with open(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_devigged.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['fighter_close_lo'] and r['fighter_close_hi'] and r['opponent_close_lo'] and r['opponent_close_hi']:
            try:
                float(r['fighter_close_lo']); float(r['fighter_close_hi'])
                float(r['opponent_close_lo']); float(r['opponent_close_hi'])
                fights_raw[r['fight_id']].append(r)
            except: pass

women_fights = []
for fid, rows in fights_raw.items():
    if len(rows) != 2: continue
    r1 = rows[0]
    lo_a=float(r1['fighter_close_lo']); hi_a=float(r1['fighter_close_hi'])
    lo_b=float(r1['opponent_close_lo']); hi_b=float(r1['opponent_close_hi'])
    mid_a=(lo_a+hi_a)/2; mid_b=(lo_b+hi_b)/2
    if mid_a<0 and mid_b<0: continue
    if mid_a==0 or mid_b==0: continue
    pa, pb = dv(mid_a, mid_b)
    date = r1.get('date','')
    if not date: continue
    fa=normalize(r1['fighter_name']); fb=normalize(r1['opponent_name'])
    if not (fa in women_fighters and fb in women_fighters): continue
    winner = outcomes.get((fa,fb))
    if winner is None: continue
    fav_p = max(pa, pb)
    fav_won = (winner==fa and pa>=pb) or (winner==fb and pb>=pa)
    year = int(date[:4])
    women_fights.append({'year': year, 'fav_p': fav_p, 'fav_won': fav_won})

print(f"Women's fights: {len(women_fights)}")

blocks = [
    ('2007-2012', lambda y: 2007<=y<=2012),
    ('2013-2015', lambda y: 2013<=y<=2015),
    ('2016-2018', lambda y: 2016<=y<=2018),
    ('2019-2021', lambda y: 2019<=y<=2021),
    ('2022-2023', lambda y: 2022<=y<=2023),
    ('2024', lambda y: y==2024),
    ('2025-2026', lambda y: y>=2025),
]

print(f"\n{'='*70}")
print("MULTIPLE COMPARISONS: 7 blocks, women's-fav edge > 0")
print(f"Null: each fight outcome ~ Bernoulli(fav_p). {N_BOOT} draws, seed {SEED}.")
print(f"{'='*70}")

results = []
for bl, fn in blocks:
    sub = [f for f in women_fights if fn(f['year'])]
    n = len(sub)
    if n == 0:
        results.append((bl, n, np.nan, np.nan))
        continue

    fav_ps = np.array([f['fav_p'] for f in sub])
    obs_wr = sum(f['fav_won'] for f in sub) / n
    obs_edge = obs_wr - fav_ps.mean()

    # Null distribution
    null_edges = []
    for _ in range(N_BOOT):
        sim_wins = rng.random(n) < fav_ps
        null_edges.append(sim_wins.mean() - fav_ps.mean())
    null_edges = np.array(null_edges)

    p_val = (null_edges >= obs_edge).mean()
    results.append((bl, n, obs_edge, p_val))

# Count non-empty blocks
non_empty = [(bl, n, e, p) for bl, n, e, p in results if n > 0]
n_tests = len(non_empty)
bonf = 0.05 / n_tests

print(f"\nTests: {n_tests}, Bonferroni threshold: {bonf:.4f} (0.05/{n_tests})")

print(f"\n{'Block':<12} {'n':>4} {'Edge':>8} {'p-value':>10} {'Raw<.05':>8} {'Bonf':>8}")
print("-" * 55)

p_values = []
for bl, n, edge, p in results:
    if n == 0:
        print(f"{bl:<12} {0:>4}      ---        ---      ---      ---")
        continue
    raw_sig = 'YES' if p < 0.05 else 'no'
    bonf_sig = 'YES' if p < bonf else 'no'
    print(f"{bl:<12} {n:>4} {edge:>+7.1%} {p:>10.4f} {raw_sig:>8} {bonf_sig:>8}")
    p_values.append((bl, p))

# Benjamini-Hochberg
print(f"\nBenjamini-Hochberg FDR (alpha=0.05):")
sorted_p = sorted(p_values, key=lambda x: x[1])
m = len(sorted_p)
max_pass_rank = 0
for rank, (bl, p) in enumerate(sorted_p, 1):
    bh_thr = 0.05 * rank / m
    passes = p <= bh_thr
    if passes: max_pass_rank = rank
    print(f"  rank {rank}: {bl:<12} p={p:.4f}  BH threshold={bh_thr:.4f}  {'PASS' if passes else 'fail'}")

bh_significant = set(bl for rank, (bl, p) in enumerate(sorted_p, 1) if rank <= max_pass_rank)

# Pooled reference
pooled_n = len(women_fights)
pooled_fav_ps = np.array([f['fav_p'] for f in women_fights])
pooled_wr = sum(f['fav_won'] for f in women_fights) / pooled_n
pooled_edge = pooled_wr - pooled_fav_ps.mean()
null_pooled = []
for _ in range(N_BOOT):
    sim = rng.random(pooled_n) < pooled_fav_ps
    null_pooled.append(sim.mean() - pooled_fav_ps.mean())
null_pooled = np.array(null_pooled)
ci_pooled = (np.percentile(null_pooled, 2.5), np.percentile(null_pooled, 97.5))
p_pooled = (null_pooled >= pooled_edge).mean()

print(f"\nPooled all-years (non-selected reference):")
print(f"  n={pooled_n}, edge={pooled_edge:+.1%}pp, "
      f"null CI=[{ci_pooled[0]:+.1%},{ci_pooled[1]:+.1%}], p={p_pooled:.3f}")

# Verdict
b2024 = next((r for r in results if r[0]=='2024'), None)
print(f"\n{'='*70}")
print("VERDICT")
print(f"{'='*70}")

if b2024:
    bl, n, edge, p = b2024
    bonf_survives = p < bonf
    bh_survives = '2024' in bh_significant

    print(f"\n  2024 block: n={n}, edge={edge:+.1%}pp, p={p:.4f}")
    print(f"  Bonferroni ({bonf:.4f}): {'SURVIVES' if bonf_survives else 'DOES NOT SURVIVE'}")
    print(f"  Benjamini-Hochberg FDR: {'SURVIVES' if bh_survives else 'DOES NOT SURVIVE'}")
    print(f"  Pooled all-years: {pooled_edge:+.1%}pp (p={p_pooled:.3f})")
    print()
    if bonf_survives:
        print("  The 2024 excursion IS distinguishable from a chance block under multiplicity.")
    else:
        print("  The 2024 excursion is NOT distinguishable from a chance block")
        print(f"  under multiplicity. The +{edge:.0%}pp in one of {n_tests} tested blocks is")
        print(f"  consistent with chance variation around a pooled null of {pooled_edge:+.1%}pp.")
