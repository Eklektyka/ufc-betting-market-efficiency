#!/usr/bin/env python3
"""
Women's-fav regime change test: blind changepoint + OOS freeze + pre-2024 ROI.
"""
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
    # Best-line info for profitability
    best_lo = min(lo_a, lo_b)  # most negative = tightest fav price
    best_hi = max(hi_a, hi_b)  # most positive = best dog price
    # For the favorite at best-line: use close_hi (most generous fav price)
    if pa >= pb:
        fav_best = hi_a  # best (most generous to backer) closing line for fav
    else:
        fav_best = hi_b

    women_fights.append({
        'year': year, 'date': date, 'fav_p': fav_p, 'fav_won': fav_won,
        'event': r1.get('event_name',''),
        'edge': (1 if fav_won else 0) - fav_p,  # per-fight edge
        'fav_best': fav_best,
    })

women_fights.sort(key=lambda x: x['date'])
print(f"Women's fights (2007-2026): {len(women_fights)}")
# Filter to 2013+ (WMMA era)
wf = [f for f in women_fights if f['year'] >= 2013]
print(f"Women's fights (2013-2026): {len(wf)}")

# ═══════════════════════════════════════════════════════════════════
# TEST 1: BLIND CHANGEPOINT DETECTION
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("TEST 1: BLIND CHANGEPOINT DETECTION")
print("CUSUM on half-year edge series, no prior on break location")
print(f"{'='*80}")

# Build half-year bins
from datetime import datetime
half_years = defaultdict(list)
for f in wf:
    dt = datetime.strptime(f['date'], '%Y-%m-%d')
    hy = f"{dt.year}H{'1' if dt.month <= 6 else '2'}"
    half_years[hy].append(f)

# Compute edge per half-year (only bins with >=5 fights)
hy_sorted = sorted(half_years.keys())
hy_edges = []
for hy in hy_sorted:
    fights = half_years[hy]
    if len(fights) < 5: continue
    wr = sum(f['fav_won'] for f in fights) / len(fights)
    impl = np.mean([f['fav_p'] for f in fights])
    edge = wr - impl
    hy_edges.append({'hy': hy, 'edge': edge, 'n': len(fights)})

print(f"\nHalf-year series ({len(hy_edges)} bins with n>=5):")
print(f"  {'Period':<8} {'n':>4} {'Edge':>8}")
for h in hy_edges:
    marker = ' <<<' if '2024' in h['hy'] else ''
    print(f"  {h['hy']:<8} {h['n']:>4} {h['edge']:>+7.1%}{marker}")

edges = np.array([h['edge'] for h in hy_edges])

# CUSUM: cumulative sum of (edge - mean_edge)
mean_edge = edges.mean()
cusum = np.cumsum(edges - mean_edge)

# Find the point of maximum absolute CUSUM = most likely changepoint
max_idx = np.argmax(np.abs(cusum))
max_hy = hy_edges[max_idx]['hy']

print(f"\n  Global mean edge: {mean_edge:+.1%}")
print(f"  CUSUM max deviation at: {max_hy} (index {max_idx}/{len(edges)-1})")
print(f"  CUSUM value at max: {cusum[max_idx]:+.3f}")

# Significance: bootstrap under null (permute edges)
null_max_cusum = []
for _ in range(N_BOOT):
    perm = rng.permutation(edges)
    cs = np.cumsum(perm - perm.mean())
    null_max_cusum.append(np.max(np.abs(cs)))

obs_max = np.max(np.abs(cusum))
p_cusum = (np.array(null_max_cusum) >= obs_max).mean()

print(f"  Max |CUSUM|: {obs_max:.3f}")
print(f"  Permutation p-value: {p_cusum:.4f}")
print(f"  Significant at 0.05: {'YES' if p_cusum < 0.05 else 'NO'}")

# Also try: binary segmentation (find the single best split)
print(f"\n  Binary segmentation (single best split):")
best_split = None; best_stat = 0
for k in range(2, len(edges)-2):
    left = edges[:k]; right = edges[k:]
    # Test statistic: difference in means, weighted by n
    stat = abs(left.mean() - right.mean()) * math.sqrt(len(left)*len(right)/len(edges))
    if stat > best_stat:
        best_stat = stat; best_split = k

if best_split is not None:
    left_mean = edges[:best_split].mean()
    right_mean = edges[best_split:].mean()
    split_hy = hy_edges[best_split]['hy']
    print(f"  Best split at: {split_hy} (index {best_split})")
    print(f"  Left mean: {left_mean:+.1%} (n={best_split} bins)")
    print(f"  Right mean: {right_mean:+.1%} (n={len(edges)-best_split} bins)")
    print(f"  Difference: {right_mean - left_mean:+.1%}pp")

    # Significance
    null_stats = []
    for _ in range(N_BOOT):
        perm = rng.permutation(edges)
        bs = 0
        for k in range(2, len(perm)-2):
            l = perm[:k]; r = perm[k:]
            s = abs(l.mean()-r.mean()) * math.sqrt(len(l)*len(r)/len(perm))
            if s > bs: bs = s
        null_stats.append(bs)
    p_split = (np.array(null_stats) >= best_stat).mean()
    print(f"  Permutation p-value: {p_split:.4f}")
    print(f"  Significant at 0.05: {'YES' if p_split < 0.05 else 'NO'}")

    # Does the algorithm independently find 2024?
    finds_2024 = '2024' in split_hy or '2023H2' in split_hy
    print(f"\n  Algorithm independently flags ~2024: {'YES' if finds_2024 else 'NO'}")
    if not finds_2024:
        print(f"  (It found {split_hy} instead — the 2024 spike is not the dominant break)")

# ═══════════════════════════════════════════════════════════════════
# TEST 2: OUT-OF-SAMPLE FREEZE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("TEST 2: OUT-OF-SAMPLE FREEZE")
print(f"{'='*80}")

# My data cutoff: the latest date in the BFO devigged file
last_date = max(f['date'] for f in wf)
print(f"\n  Last fight in dataset: {last_date}")
print(f"  Data cutoff: {last_date}")
print(f"  Prediction frozen: 'women's favorites beat consensus by ~+9pp'")

# Check if any fights exist after cutoff
post_cutoff = [f for f in wf if f['date'] > last_date]
print(f"  Fights after cutoff: {len(post_cutoff)}")
if post_cutoff:
    wr = sum(f['fav_won'] for f in post_cutoff) / len(post_cutoff)
    impl = np.mean([f['fav_p'] for f in post_cutoff])
    print(f"  OOS result: WR={wr:.0%}, impl={impl:.0%}, edge={wr-impl:+.1%}pp (n={len(post_cutoff)})")
else:
    print(f"  No out-of-sample data yet. The freeze is prospective.")
    print(f"  As future UFC events with women's fights resolve, score them against")
    print(f"  the frozen +9pp prediction with an honest CI.")

# ═══════════════════════════════════════════════════════════════════
# TEST 3: PRE-2024 BEST-LINE ROI (coffin nail on line-shopping)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("TEST 3: PRE-2024 BEST-LINE ROI ON WOMEN'S FAVORITES")
print(f"{'='*80}")

pre2024 = [f for f in wf if f['year'] < 2024]
print(f"\n  Women's-fav fights 2013-2023: {len(pre2024)}")

# ROI at best-line (close_hi for the fav)
roi_bets = []
for f in pre2024:
    best = f['fav_best']
    if best is None or best == 0: continue
    dec = american_to_decimal(best)
    profit = (dec - 1) * 100 if f['fav_won'] else -100
    roi_bets.append({'profit': profit, 'event': f['event']})

if roi_bets:
    total = sum(b['profit'] for b in roi_bets)
    n = len(roi_bets)
    roi = total / (n * 100)

    events = list(set(b['event'] for b in roi_bets))
    eb = defaultdict(list)
    for b in roi_bets: eb[b['event']].append(b)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sp = sn = 0
        for e in se:
            for b in eb[e]: sp += b['profit']; sn += 1
        boot.append(sp / (sn * 100) if sn > 0 else 0)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))

    print(f"  n={n}, ROI={roi:+.1%} CI=[{ci[0]:+.1%},{ci[1]:+.1%}]")
    print(f"  CI excludes zero: {'YES' if ci[0] > 0 else 'NO'}")
    print(f"  Profit: ${total:+,.0f}")

    # Mean best-line
    mean_line = np.mean([f['fav_best'] for f in pre2024 if f['fav_best']])
    print(f"  Mean fav best-line: {mean_line:+.0f} American")
else:
    print("  No bets (missing best-line data)")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VERDICT")
print(f"{'='*80}")
