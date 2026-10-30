#!/usr/bin/env python3
"""Self-scouting: Ezoteryka's picks dissected every which way."""
import csv, os, re, sys, unicodedata
import numpy as np
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

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

# ─── Load picks ───
with open(r'C:\Research\ufc\picks\users\Ezoteryka.csv', encoding='utf-8') as f:
    picks = list(csv.DictReader(f))

# ─── Load odds from ezoteryka_scored ───
event_bouts = defaultdict(list)
with open('ezoteryka_scored.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_bouts[normalize_event(r['card_key'])].append(r)

# ─── Load women fighters ───
women_fighters = set()
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if 'women' in r.get('division', '').lower():
            women_fighters.add(normalize(r['fighter_name']))

# ─── Division lookup ───
division_map = {}
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        fa = normalize(r['fighter_name']); fb = normalize(r['fighter_name_opp'])
        div = r.get('division', '').strip()
        if div:
            division_map[(fa, fb)] = div
            division_map[(fb, fa)] = div

# ─── Join picks to odds ───
scored = []
event_bout_idx = defaultdict(int)

for p in picks:
    ev = p['event']
    bout_pos = event_bout_idx[ev]
    event_bout_idx[ev] += 1

    fp = p['fighter_picked']; opp = p['opponent']
    fp_n = normalize(fp); opp_n = normalize(opp)
    correct = p['correct'] == 'YES'
    actual_method = p.get('actual_method', '')
    picked_method_raw = p.get('picked_method', '')
    picked_method = get_method_cat(picked_method_raw) if picked_method_raw else None
    actual_method_cat = get_method_cat(actual_method)

    # Find odds
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

    p_fair = None; best_line = None; profit = None; fav_dog = None
    if odds_row:
        if names_match(fp_n, normalize(odds_row['picked_fighter'])):
            p_fair = float(odds_row['p_fair_picked'])
            best_line = int(odds_row['best_line'])
        else:
            p_fair = 1 - float(odds_row['p_fair_picked'])
            dec = 1 / p_fair if p_fair > 0 else 100
            best_line = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))
        dec_odds = american_to_decimal(best_line)
        profit = (dec_odds - 1) * 100 if correct else -100
        fav_dog = 'fav' if p_fair >= 0.5 else 'dog'

    # Gender
    is_women = normalize(fp) in women_fighters and normalize(opp) in women_fighters

    # Division
    div = division_map.get((fp_n, opp_n), '')
    if not div: div = division_map.get((opp_n, fp_n), '')

    # Prob bucket
    prob_bucket = None
    if p_fair is not None:
        if p_fair >= 0.70: prob_bucket = 'Heavy fav (>70%)'
        elif p_fair >= 0.55: prob_bucket = 'Moderate fav (55-70%)'
        elif p_fair >= 0.45: prob_bucket = 'Coinflip (45-55%)'
        else: prob_bucket = 'Dog (<45%)'

    # Card position
    if bout_pos == 0: card_pos = 'Main event'
    elif bout_pos < 5: card_pos = 'Main card'
    else: card_pos = 'Prelims'

    scored.append({
        'event': ev, 'fighter_picked': fp, 'opponent': opp,
        'correct': correct, 'p_fair': p_fair, 'best_line': best_line,
        'profit': profit, 'fav_dog': fav_dog, 'prob_bucket': prob_bucket,
        'is_women': is_women, 'division': div,
        'picked_method': picked_method, 'actual_method_cat': actual_method_cat,
        'actual_method_raw': actual_method,
        'card_pos': card_pos, 'bout_pos': bout_pos,
        'canonical_date': odds_row['canonical_date'] if odds_row else '',
    })

# ═══════════════════════════════════════════════════════════════════
# BASELINES
# ═══════════════════════════════════════════════════════════════════
print("=" * 80)
print("EZOTERYKA SELF-SCOUT")
print("=" * 80)

total = len(scored)
correct_all = sum(s['correct'] for s in scored)
with_odds = [s for s in scored if s['p_fair'] is not None]
n_odds = len(with_odds)
correct_odds = sum(s['correct'] for s in with_odds)
total_implied = sum(s['p_fair'] for s in with_odds)
total_profit = sum(s['profit'] for s in with_odds)
roi = total_profit / (n_odds * 100)

# Method accuracy
with_method = [s for s in scored if s['picked_method'] and s['actual_method_cat']]
method_correct = sum(1 for s in with_method if s['picked_method'] == s['actual_method_cat'])
joint_correct = sum(1 for s in with_method if s['correct'] and s['picked_method'] == s['actual_method_cat'])

print(f"""
BASELINES (your numbers, everything reads against these):
  Total picks:           {total}
  Raw accuracy:          {correct_all}/{total} = {correct_all/total:.1%}
  Odds-matched picks:    {n_odds}
  Accuracy (odds set):   {correct_odds}/{n_odds} = {correct_odds/n_odds:.1%}
  Market-implied hit:    {total_implied/n_odds:.1%} (sum of p_fair on your picks / n)
  Acc vs implied:        {correct_odds/n_odds - total_implied/n_odds:+.1%}pp (you minus market)
  Flat-stake ROI:        {roi:+.1%} (${total_profit:+,.0f} on {n_odds} bets)
  Method accuracy:       {method_correct}/{len(with_method)} = {method_correct/len(with_method):.1%}
  Joint (fighter+method):{joint_correct}/{len(with_method)} = {joint_correct/len(with_method):.1%}
""")

# ─── Helper for splits ───
def split_table(label, key_fn, sort_worst=True):
    buckets = defaultdict(lambda: {'n': 0, 'correct': 0, 'p_fair_sum': 0, 'profit_sum': 0, 'n_odds': 0})
    for s in scored:
        k = key_fn(s)
        if k is None: continue
        b = buckets[k]
        b['n'] += 1
        if s['correct']: b['correct'] += 1
        if s['p_fair'] is not None:
            b['n_odds'] += 1
            b['p_fair_sum'] += s['p_fair']
            b['profit_sum'] += s['profit']

    print(f"\n{'─'*80}")
    print(f"  {label}")
    print(f"{'─'*80}")
    print(f"  {'Cell':<30} {'n':>4} {'Acc':>6} {'Impl':>6} {'vs_Impl':>7} {'nOdds':>5} {'ROI':>7} {'Flag':>5}")
    print(f"  {'-'*72}")

    items = list(buckets.items())
    if sort_worst:
        items.sort(key=lambda x: (x[1]['correct']/x[1]['n'] if x[1]['n'] else 0) - (x[1]['p_fair_sum']/x[1]['n_odds'] if x[1]['n_odds'] else 0))

    for k, b in items:
        n = b['n']; c = b['correct']; acc = c / n if n else 0
        impl = b['p_fair_sum'] / b['n_odds'] if b['n_odds'] else 0
        vs_impl = acc - impl
        roi_v = b['profit_sum'] / (b['n_odds'] * 100) if b['n_odds'] else 0
        flag = '<25' if n < 25 else ''
        impl_s = f"{impl:.1%}" if b['n_odds'] else '—'
        vs_s = f"{vs_impl:+.1%}" if b['n_odds'] else '—'
        roi_s = f"{roi_v:+.1%}" if b['n_odds'] else '—'
        print(f"  {str(k)[:29]:<30} {n:>4} {acc:>5.1%} {impl_s:>6} {vs_s:>7} {b['n_odds']:>5} {roi_s:>7} {flag:>5}")

# ═══════════════════════════════════════════════════════════════════
# 1. FAV/DOG + PROB BUCKET
# ═══════════════════════════════════════════════════════════════════
split_table("1. FAVORITE vs UNDERDOG", lambda s: s['fav_dog'])
split_table("1b. BY IMPLIED-PROB BUCKET", lambda s: s['prob_bucket'])

# ═══════════════════════════════════════════════════════════════════
# 2. DIVISION
# ═══════════════════════════════════════════════════════════════════
def clean_div(d):
    if not d: return None
    d = d.upper().replace('UFC ', '').replace(' TITLE BOUT', '').replace(' BOUT', '')
    return d.strip() if d.strip() else None

split_table("2. BY DIVISION", lambda s: clean_div(s['division']))

# ═══════════════════════════════════════════════════════════════════
# 3. GENDER
# ═══════════════════════════════════════════════════════════════════
split_table("3. MEN'S vs WOMEN'S", lambda s: "Women's" if s['is_women'] else "Men's")

# ═══════════════════════════════════════════════════════════════════
# 4. PREDICTED METHOD
# ═══════════════════════════════════════════════════════════════════
split_table("4. BY PREDICTED METHOD (my call)", lambda s: s['picked_method'])

# Method accuracy per call type
print(f"\n  Method accuracy breakdown:")
for m in ['KO/TKO', 'Submission', 'Decision']:
    sub = [s for s in with_method if s['picked_method'] == m]
    if sub:
        mc = sum(1 for s in sub if s['picked_method'] == s['actual_method_cat'])
        jc = sum(1 for s in sub if s['correct'] and s['picked_method'] == s['actual_method_cat'])
        print(f"    I called {m}: {len(sub)} times, method right {mc}/{len(sub)} ({mc/len(sub):.0%}), "
              f"fighter+method right {jc}/{len(sub)} ({jc/len(sub):.0%})")

# Over/under-pick analysis
method_counts = Counter(s['picked_method'] for s in with_method if s['picked_method'])
actual_counts = Counter(s['actual_method_cat'] for s in with_method if s['actual_method_cat'])
print(f"\n  Method selection vs reality:")
print(f"    {'Method':<15} {'I picked':>10} {'Actually':>10} {'Over/under':>12}")
for m in ['KO/TKO', 'Submission', 'Decision']:
    picked = method_counts.get(m, 0)
    actual = actual_counts.get(m, 0)
    diff = picked - actual
    print(f"    {m:<15} {picked:>10} {actual:>10} {diff:>+12}")

# ═══════════════════════════════════════════════════════════════════
# 5. CARD POSITION
# ═══════════════════════════════════════════════════════════════════
split_table("5. BY CARD POSITION", lambda s: s['card_pos'])

# ═══════════════════════════════════════════════════════════════════
# 6. STYLE — skip (not in data)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'─'*80}")
print(f"  6. STYLE (striker vs grappler) — SKIPPED, not in data")

# ═══════════════════════════════════════════════════════════════════
# 7. RIGHT FIGHTER, WRONG METHOD
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'─'*80}")
print(f"  7. WHEN I PICK THE RIGHT FIGHTER BUT WRONG METHOD")
print(f"{'─'*80}")

right_fighter_wrong_method = [s for s in with_method if s['correct'] and s['picked_method'] != s['actual_method_cat']]
print(f"\n  Total: {len(right_fighter_wrong_method)} picks (right fighter, wrong method)")

confusion = defaultdict(int)
for s in right_fighter_wrong_method:
    confusion[(s['picked_method'], s['actual_method_cat'])] += 1

print(f"\n  {'I predicted →':<20} {'Actually was →':<20} {'Count':>5}")
print(f"  {'-'*48}")
for (pred, actual), n in sorted(confusion.items(), key=lambda x: -x[1]):
    print(f"  {pred:<20} {actual:<20} {n:>5}")

# Finish over-call rate
finish_calls = sum(1 for s in with_method if s['picked_method'] in ('KO/TKO', 'Submission'))
decision_calls = sum(1 for s in with_method if s['picked_method'] == 'Decision')
actual_finishes = sum(1 for s in with_method if s['actual_method_cat'] in ('KO/TKO', 'Submission'))
actual_decisions = sum(1 for s in with_method if s['actual_method_cat'] == 'Decision')
print(f"\n  I called finish (KO+Sub): {finish_calls}/{len(with_method)} ({finish_calls/len(with_method):.0%})")
print(f"  Actually finished:        {actual_finishes}/{len(with_method)} ({actual_finishes/len(with_method):.0%})")
print(f"  → I {'over' if finish_calls > actual_finishes else 'under'}-call finishes by {abs(finish_calls - actual_finishes)} picks")

# ═══════════════════════════════════════════════════════════════════
# 8. CALIBRATION CURVE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'─'*80}")
print(f"  8. CALIBRATION CURVE (my hit rate per market-confidence bucket)")
print(f"{'─'*80}")

cal_buckets = [(0.0, 0.30, '<30%'), (0.30, 0.40, '30-40%'), (0.40, 0.50, '40-50%'),
               (0.50, 0.60, '50-60%'), (0.60, 0.70, '60-70%'), (0.70, 0.80, '70-80%'),
               (0.80, 0.90, '80-90%'), (0.90, 1.01, '90%+')]

print(f"\n  {'Bucket':<12} {'n':>5} {'My hit%':>8} {'Mkt imp%':>9} {'Diff':>7} {'Bar'}")
print(f"  {'-'*60}")
for lo, hi, label in cal_buckets:
    sub = [s for s in with_odds if lo <= s['p_fair'] < hi]
    if not sub: continue
    my_hit = sum(s['correct'] for s in sub) / len(sub)
    mkt_imp = sum(s['p_fair'] for s in sub) / len(sub)
    diff = my_hit - mkt_imp
    bar_len = int(abs(diff) * 200)
    bar = ('▓' * bar_len + ' ') if diff > 0 else (' ' * bar_len + '░' * bar_len)
    sign = '+' if diff >= 0 else ''
    print(f"  {label:<12} {len(sub):>5} {my_hit:>7.1%} {mkt_imp:>8.1%} {sign}{diff:>6.1%} {'█' * min(int(abs(diff)*100), 20)} {'↑' if diff > 0 else '↓'}")

# ═══════════════════════════════════════════════════════════════════
# 9. TIME TREND
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'─'*80}")
print(f"  9. TIME TREND (accuracy and acc-vs-implied per event)")
print(f"{'─'*80}")

events_ordered = []
seen = set()
for s in scored:
    if s['event'] not in seen:
        seen.add(s['event'])
        events_ordered.append(s['event'])

print(f"\n  {'Event':<50} {'n':>4} {'Acc':>6} {'vsImpl':>7}")
print(f"  {'-'*70}")

# Rolling 5-event average
event_stats = []
for ev in events_ordered:
    sub = [s for s in scored if s['event'] == ev]
    n = len(sub); c = sum(s['correct'] for s in sub)
    sub_odds = [s for s in sub if s['p_fair'] is not None]
    impl = sum(s['p_fair'] for s in sub_odds) / len(sub_odds) if sub_odds else 0
    acc = c / n
    vs = acc - impl if sub_odds else 0
    event_stats.append({'ev': ev, 'n': n, 'acc': acc, 'vs': vs})
    print(f"  {ev[:49]:<50} {n:>4} {acc:>5.0%} {vs:>+6.1%}")

# Rolling avg
print(f"\n  Rolling 5-event accuracy:")
for i in range(0, len(event_stats), 5):
    chunk = event_stats[i:i+5]
    total_n = sum(c['n'] for c in chunk)
    total_c = sum(int(c['acc'] * c['n']) for c in chunk)
    avg_acc = total_c / total_n if total_n else 0
    avg_vs = np.mean([c['vs'] for c in chunk])
    label = f"Events {i+1}-{min(i+5, len(event_stats))}"
    print(f"    {label:<20} acc={avg_acc:.0%}  vs_impl={avg_vs:+.1%}")

# ═══════════════════════════════════════════════════════════════════
# 10. BIGGEST MISSES (heavy favorites that lost)
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'─'*80}")
print(f"  10. BIGGEST MISSES — heavy favorites I picked that LOST")
print(f"{'─'*80}")

misses = [s for s in with_odds if not s['correct'] and s['p_fair'] and s['p_fair'] >= 0.65]
misses.sort(key=lambda s: -s['p_fair'])
print(f"\n  {'Fighter I picked':<25} {'Opponent':<25} {'p_fair':>7} {'Line':>7} {'Loss $':>7} {'Event'}")
print(f"  {'-'*95}")
for s in misses[:15]:
    loss = s['profit']
    print(f"  {s['fighter_picked'][:24]:<25} {s['opponent'][:24]:<25} {s['p_fair']:>6.1%} {s['best_line']:>+7} "
          f"${loss:>+6.0f} {s['event'][:30]}")

print(f"\n  Heavy-dog picks that also lost:")
dog_misses = [s for s in with_odds if not s['correct'] and s['p_fair'] and s['p_fair'] < 0.35]
dog_misses.sort(key=lambda s: s['p_fair'])
for s in dog_misses[:10]:
    print(f"  {s['fighter_picked'][:24]:<25} {s['opponent'][:24]:<25} {s['p_fair']:>6.1%} {s['best_line']:>+7} "
          f"${s['profit']:>+6.0f}")

# ═══════════════════════════════════════════════════════════════════
# 11. BIGGEST DOG WINS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'─'*80}")
print(f"  11. BIGGEST DOGS I PICKED THAT WON 🎯")
print(f"{'─'*80}")

dog_wins = [s for s in with_odds if s['correct'] and s['p_fair'] and s['p_fair'] < 0.45]
dog_wins.sort(key=lambda s: s['p_fair'])
print(f"\n  {'Fighter I picked':<25} {'Opponent':<25} {'p_fair':>7} {'Line':>7} {'Win $':>7} {'Event'}")
print(f"  {'-'*95}")
for s in dog_wins[:15]:
    print(f"  {s['fighter_picked'][:24]:<25} {s['opponent'][:24]:<25} {s['p_fair']:>6.1%} {s['best_line']:>+7} "
          f"${s['profit']:>+6.0f} {s['event'][:30]}")

# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("WHERE YOU LEAK (hypothesis-generating, not proof)")
print(f"{'='*80}")
print("""
Based on the splits above, here are the patterns most worth noticing:
""")

# Compute key numbers for summary
fav_sub = [s for s in with_odds if s['fav_dog'] == 'fav']
dog_sub = [s for s in with_odds if s['fav_dog'] == 'dog']
fav_acc = sum(s['correct'] for s in fav_sub) / len(fav_sub) if fav_sub else 0
dog_acc = sum(s['correct'] for s in dog_sub) / len(dog_sub) if dog_sub else 0
fav_impl = sum(s['p_fair'] for s in fav_sub) / len(fav_sub) if fav_sub else 0
dog_impl = sum(s['p_fair'] for s in dog_sub) / len(dog_sub) if dog_sub else 0
fav_roi = sum(s['profit'] for s in fav_sub) / (len(fav_sub) * 100) if fav_sub else 0
dog_roi = sum(s['profit'] for s in dog_sub) / (len(dog_sub) * 100) if dog_sub else 0

# Method over/under
ko_picked = sum(1 for s in with_method if s['picked_method'] == 'KO/TKO')
ko_actual = sum(1 for s in with_method if s['actual_method_cat'] == 'KO/TKO')
sub_picked = sum(1 for s in with_method if s['picked_method'] == 'Submission')
sub_actual = sum(1 for s in with_method if s['actual_method_cat'] == 'Submission')
dec_picked = sum(1 for s in with_method if s['picked_method'] == 'Decision')
dec_actual = sum(1 for s in with_method if s['actual_method_cat'] == 'Decision')

print(f"1. FAV/DOG PROFILE: You picked {len(fav_sub)} favorites ({fav_acc:.0%} hit, market expected {fav_impl:.0%}, "
      f"ROI {fav_roi:+.1%}) and {len(dog_sub)} dogs ({dog_acc:.0%} hit, market expected {dog_impl:.0%}, "
      f"ROI {dog_roi:+.1%}).")

print(f"\n2. METHOD BIAS: You called KO/TKO {ko_picked}x (actual {ko_actual}), "
      f"Submission {sub_picked}x (actual {sub_actual}), Decision {dec_picked}x (actual {dec_actual}). "
      f"{'Over-calling finishes.' if ko_picked + sub_picked > ko_actual + sub_actual else 'Under-calling finishes.'}")

# Worst confusion
worst_conf = max(confusion.items(), key=lambda x: x[1])
print(f"\n3. BIGGEST METHOD LEAK: When you get the fighter right but method wrong, "
      f"the most common error is calling {worst_conf[0][0]} when it was actually {worst_conf[0][1]} "
      f"({worst_conf[1]} times).")

# Calibration
print(f"\n4. CALIBRATION: Check the calibration table above — where your hit rate "
      f"diverges most from the market line is where you're systematically over- or "
      f"under-confident relative to the odds.")
