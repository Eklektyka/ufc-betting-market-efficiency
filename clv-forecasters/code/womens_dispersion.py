#!/usr/bin/env python3
"""
Women's-fight cross-book dispersion and per-book staleness.
Two-part: (A) historical close_lo/close_hi spread, (B) per-book on recent data.
"""
import csv, os, re, sys, unicodedata, math
import numpy as np
from collections import defaultdict
from scipy.stats import spearmanr

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
rng = np.random.RandomState(SEED)

def normalize(name):
    s = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()
def ai(o): return -o/(-o+100) if o < 0 else 100/(o+100)

women_fighters = set()
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if 'women' in r.get('division','').lower():
            women_fighters.add(normalize(r['fighter_name']))

# ═══════════════════════════════════════════════════════════════════
# PART 1: HISTORICAL DISPERSION (close_hi - close_lo)
# ═══════════════════════════════════════════════════════════════════
print("=" * 80)
print("PART 1: CROSS-BOOK DISPERSION (close_hi − close_lo, 2007-2026)")
print("=" * 80)

hist_path = r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_devigged.csv'
fights_raw = defaultdict(list)
with open(hist_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['fighter_close_lo'] and r['fighter_close_hi']:
            fights_raw[r['fight_id']].append(r)

dispersions = []
for fid, rows in fights_raw.items():
    if len(rows) != 2: continue
    r1 = rows[0]
    fa = normalize(r1['fighter_name']); fb = normalize(r1['opponent_name'])
    is_women = fa in women_fighters and fb in women_fighters
    date = r1.get('date','')
    if not date: continue

    lo_a = float(r1['fighter_close_lo']); hi_a = float(r1['fighter_close_hi'])
    lo_b = float(r1['opponent_close_lo']); hi_b = float(r1['opponent_close_hi'])

    # Implied prob spread for the favorite
    mid_a = (lo_a+hi_a)/2; mid_b = (lo_b+hi_b)/2
    if mid_a == 0 or mid_b == 0: continue
    if mid_a < 0 and mid_b < 0: continue

    # Favorite = higher implied
    ip_lo_a = ai(lo_a); ip_hi_a = ai(hi_a)
    ip_lo_b = ai(lo_b); ip_hi_b = ai(hi_b)

    # For the favorite: the spread in implied prob across books
    # close_lo gives highest implied (tightest price), close_hi gives lowest (widest price)
    # Actually for favorites (negative American): more negative = higher implied
    # close_lo is the most negative = highest implied, close_hi is least negative = lowest implied
    # So spread = ip_lo - ip_hi (positive if lo is tighter)

    # Determine favorite by midpoint
    fav_is_a = ai(mid_a) > ai(mid_b)
    if fav_is_a:
        fav_lo = lo_a; fav_hi = hi_a; fav_mid = mid_a
    else:
        fav_lo = lo_b; fav_hi = hi_b; fav_mid = mid_b

    # Spread in implied prob for the favorite
    ip_fav_lo = ai(fav_lo)  # from close_lo
    ip_fav_hi = ai(fav_hi)  # from close_hi
    spread_ip = abs(ip_fav_lo - ip_fav_hi)

    # Favorite strength (midpoint implied)
    fav_strength = ai(fav_mid)

    # N books approximation: if lo != hi, at least 2 books; spread magnitude suggests more
    n_books_approx = 2 if lo_a != hi_a else 1

    dispersions.append({
        'is_women': is_women, 'spread_ip': spread_ip,
        'fav_strength': fav_strength, 'n_books': n_books_approx,
        'year': int(date[:4]),
    })

w_disp = [d['spread_ip'] for d in dispersions if d['is_women']]
m_disp = [d['spread_ip'] for d in dispersions if not d['is_women']]

print(f"\nFights: women={len(w_disp)}, men={len(m_disp)}")
print(f"\nFavorite implied-prob spread (|close_hi − close_lo| in implied prob):")
print(f"  {'':>15} {'n':>5} {'mean':>7} {'median':>7} {'SD':>7} {'p75':>7}")
print(f"  {'Women':>15} {len(w_disp):>5} {np.mean(w_disp):>6.1%} {np.median(w_disp):>6.1%} {np.std(w_disp):>6.1%} {np.percentile(w_disp,75):>6.1%}")
print(f"  {'Men':>15} {len(m_disp):>5} {np.mean(m_disp):>6.1%} {np.median(m_disp):>6.1%} {np.std(m_disp):>6.1%} {np.percentile(m_disp,75):>6.1%}")
print(f"  Ratio (W/M):  {np.mean(w_disp)/np.mean(m_disp):.2f}x")

# Bootstrap CI on the difference
boot_diffs = []
for _ in range(N_BOOT):
    sw = rng.choice(w_disp, size=len(w_disp), replace=True)
    sm = rng.choice(m_disp, size=len(m_disp), replace=True)
    boot_diffs.append(sw.mean() - sm.mean())
ci = (np.percentile(boot_diffs, 2.5), np.percentile(boot_diffs, 97.5))
print(f"  Difference (W−M): {np.mean(w_disp)-np.mean(m_disp):+.1%}pp CI=[{ci[0]:+.1%},{ci[1]:+.1%}]")
print(f"  CI excludes zero: {'YES' if ci[0] > 0 else 'NO'}")

# Control for fav_strength
print(f"\n  Controlling for favorite strength:")
# Simple: split by fav_strength buckets, compare within
for lo, hi, label in [(0.5, 0.6, '50-60%'), (0.6, 0.7, '60-70%'), (0.7, 0.8, '70-80%'), (0.8, 1.0, '80%+')]:
    w = [d['spread_ip'] for d in dispersions if d['is_women'] and lo <= d['fav_strength'] < hi]
    m = [d['spread_ip'] for d in dispersions if not d['is_women'] and lo <= d['fav_strength'] < hi]
    if len(w) >= 5 and len(m) >= 5:
        print(f"    {label}: W={np.mean(w):.1%} (n={len(w)}) vs M={np.mean(m):.1%} (n={len(m)}) "
              f"ratio={np.mean(w)/np.mean(m):.2f}x")

# ═══════════════════════════════════════════════════════════════════
# PART 2: PER-BOOK STALENESS (recent data with book-level odds)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("PART 2: PER-BOOK STALENESS (Aug 2025 – Aug 2026, per-book closing odds)")
print(f"{'='*80}")

# Load per-book odds from rank + fill + ext files
per_book = defaultdict(list)  # (event_id, matchup_id, fighter_side) -> [(book, odds)]
for fname in ['bfo_odds_rank.csv', 'bfo_odds_fill_2025.csv', 'bfo_odds_ext_2026.csv']:
    with open(fname, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            book = r['book']
            if book in ('Kalshi', 'Polymarket'): continue
            if r.get('is_book') == '0': continue
            key = (r['bfo_event_id'], r['bfo_matchup_id'], r['fighter_side'])
            per_book[key].append({
                'book': book, 'odds': int(r['odds_american']),
                'fighter': r['fighter_name'], 'event_id': r['bfo_event_id'],
                'matchup_id': r['bfo_matchup_id'],
            })

# Load consensus from bfo_close_all for comparison
consensus = {}
with open('bfo_close_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        eid = r['bfo_event_id']; mid = r['bfo_matchup_id']
        f1 = normalize(r['fighter1_name']); f2 = normalize(r['fighter2_name'])
        is_women = f1 in women_fighters and f2 in women_fighters
        # Determine favorite
        p1 = float(r['f1_devigged_prob']); p2 = float(r['f2_devigged_prob'])
        if p1 >= p2:
            fav_side = '1'; fav_cons_ip = float(r['f1_implied_prob']); fav_devig = p1
        else:
            fav_side = '2'; fav_cons_ip = float(r['f2_implied_prob']); fav_devig = p2
        consensus[(eid, mid)] = {
            'is_women': is_women, 'fav_side': fav_side,
            'fav_cons_ip': fav_cons_ip, 'fav_devig': fav_devig,
        }

# For each fight's favorite, compute each book's implied vs consensus
book_offsets = defaultdict(lambda: {'women': [], 'men': []})

for (eid, mid, side), book_entries in per_book.items():
    cons = consensus.get((eid, mid))
    if not cons: continue
    if side != cons['fav_side']: continue  # only look at the favorite side

    for entry in book_entries:
        book_ip = ai(entry['odds'])
        offset = book_ip - cons['fav_cons_ip']  # positive = book thinks fav is stronger
        # Negative = book is softer on the fav (gives better price to backer)
        gender = 'women' if cons['is_women'] else 'men'
        book_offsets[entry['book']][gender].append(offset)

print(f"\nPer-book offset = book_implied − consensus_implied for the FAVORITE")
print(f"Negative = book is SOFTER (more generous to fav backers)")
print(f"\n{'Book':<15} | {'WOMEN offset':>30} | {'MEN offset':>30}")
print(f"{'':>15} | {'n':>4} {'mean':>7} {'SD':>6} | {'n':>5} {'mean':>7} {'SD':>6}")
print("-" * 75)

book_p_values = []
for book in sorted(book_offsets):
    w = book_offsets[book]['women']
    m = book_offsets[book]['men']
    w_s = f"{len(w):>4} {np.mean(w):>+6.1%} {np.std(w):>5.1%}" if w else "   0     —     —"
    m_s = f"{len(m):>5} {np.mean(m):>+6.1%} {np.std(m):>5.1%}" if m else "    0     —     —"
    print(f"{book:<15} | {w_s} | {m_s}")

    # Test: is the women's offset significantly different from zero?
    if len(w) >= 10:
        # Bootstrap
        boot = []
        for _ in range(N_BOOT):
            s = rng.choice(w, size=len(w), replace=True)
            boot.append(s.mean())
        ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))
        # Two-sided p: is mean offset != 0?
        p_val = 2 * min((np.array(boot) >= 0).mean(), (np.array(boot) <= 0).mean())
        book_p_values.append((book, len(w), np.mean(w), p_val, ci))

# Multiplicity correction
n_books_tested = len(book_p_values)
bonf = 0.05 / n_books_tested if n_books_tested > 0 else 0.05

print(f"\n{'='*80}")
print(f"PER-BOOK STALENESS TEST (women's fights, offset != 0)")
print(f"Tests: {n_books_tested}, Bonferroni threshold: {bonf:.4f}")
print(f"{'='*80}")

print(f"\n{'Book':<15} {'n_w':>4} {'mean_off':>9} {'p-value':>9} {'Bonf':>6} {'CI':>22}")
print("-" * 70)

sorted_bp = sorted(book_p_values, key=lambda x: x[3])
for book, n_w, mean_off, p, ci in sorted_bp:
    bonf_sig = 'YES' if p < bonf else 'no'
    print(f"{book:<15} {n_w:>4} {mean_off:>+8.1%} {p:>9.4f} {bonf_sig:>6} [{ci[0]:>+6.1%},{ci[1]:>+6.1%}]")

# BH FDR
print(f"\nBenjamini-Hochberg FDR:")
max_pass = 0
for rank, (book, n_w, mean_off, p, ci) in enumerate(sorted_bp, 1):
    bh_thr = 0.05 * rank / n_books_tested
    passes = p <= bh_thr
    if passes: max_pass = rank
    print(f"  rank {rank}: {book:<15} p={p:.4f} thr={bh_thr:.4f} {'PASS' if passes else 'fail'}")

survivors = [sorted_bp[i] for i in range(max_pass)]

# ═══════════════════════════════════════════════════════════════════
# PART 3: PERSISTENCE (split-half for survivors)
# ═══════════════════════════════════════════════════════════════════
if survivors:
    print(f"\n{'='*80}")
    print("PART 3: PERSISTENCE (split-half for surviving books)")
    print(f"{'='*80}")
    # Would need to split women's fights into early/late and check offset persists
    # But with so few women's fights per book (~20-30), split-half will be very noisy
    for book, n_w, mean_off, p, ci in survivors:
        w_offsets = book_offsets[book]['women']
        mid = len(w_offsets) // 2
        early = w_offsets[:mid]; late = w_offsets[mid:]
        print(f"\n  {book}: n={len(w_offsets)}, early={np.mean(early):+.1%} (n={len(early)}), "
              f"late={np.mean(late):+.1%} (n={len(late)})")
        if np.sign(np.mean(early)) == np.sign(np.mean(late)):
            print(f"    Same direction across halves")
        else:
            print(f"    SIGN FLIP across halves — not persistent")
else:
    print(f"\n  No books survived multiplicity correction. Skipping Part 3.")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VERDICT")
print(f"{'='*80}")

print(f"\n  DISPERSION: Women's cross-book spread is "
      f"{np.mean(w_disp)/np.mean(m_disp):.2f}x men's "
      f"({'wider' if np.mean(w_disp) > np.mean(m_disp) else 'same/narrower'}, "
      f"CI {'excl 0' if ci[0] > 0 else 'incl 0'}).")
print(f"  → Women's fights DO have {'more' if np.mean(w_disp) > np.mean(m_disp) else 'similar'} "
      f"cross-book disagreement — consistent with thinner liquidity.")

if survivors:
    print(f"\n  STALENESS: {len(survivors)} book(s) survived multiplicity correction.")
else:
    print(f"\n  STALENESS: No book shows a persistent, significant directional offset")
    print(f"  on women's fights after multiplicity correction.")
    print(f"  Cross-book dispersion is wider noise on a thin category,")
    print(f"  not a directionally exploitable book-level inefficiency.")

print(f"\n  EXPLOITABILITY CAVEAT: Closing-line dispersion shows disagreement but not")
print(f"  real-time fillability. Thin women's markets have low limits; getting down")
print(f"  at the stale price before it moves is not demonstrated by this data.")
