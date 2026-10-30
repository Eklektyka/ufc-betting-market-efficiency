#!/usr/bin/env python3
"""
Amendment 3: Capture-mode diagnostics on cached chart data.
a. Duplicate-y rate per series
b. Inter-point delta histograms, cross-book timestamp collision rate
c. Points-per-event by calendar date (capture density drift)
"""
import sys, json, os, re
import numpy as np
from collections import defaultdict
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

CHART_DIR = 'data/bfo/chart_raw'

# Load all event files
events = []
for f in sorted(os.listdir(CHART_DIR)):
    if not f.startswith('event_') or not f.endswith('.json'):
        continue
    with open(os.path.join(CHART_DIR, f)) as fh:
        events.append(json.load(fh))

print(f"Events loaded: {len(events)}")
print("=" * 80)

# ═══════════════════════════════════════════════════════════════════
# (a) DUPLICATE-Y RATE
# ═══════════════════════════════════════════════════════════════════
print("\n(a) DUPLICATE-Y RATE (consecutive identical y values)")
print("=" * 80)

dup_by_book = defaultdict(lambda: {'total_pairs': 0, 'dup_pairs': 0})

for ev in events:
    for fighter in ev.get('fighters', []):
        for book, pts in fighter.get('series', {}).items():
            if len(pts) < 2:
                continue
            for i in range(1, len(pts)):
                dup_by_book[book]['total_pairs'] += 1
                if pts[i][1] == pts[i-1][1]:
                    dup_by_book[book]['dup_pairs'] += 1

print(f"\n{'Book':<15} {'Pairs':>8} {'Dup':>6} {'Rate':>7}")
print("-" * 40)
for book in sorted(dup_by_book):
    d = dup_by_book[book]
    rate = d['dup_pairs'] / d['total_pairs'] if d['total_pairs'] > 0 else 0
    print(f"{book:<15} {d['total_pairs']:>8} {d['dup_pairs']:>6} {rate:>6.1%}")

# ═══════════════════════════════════════════════════════════════════
# (b) INTER-POINT DELTAS + CROSS-BOOK COLLISION RATE
# ═══════════════════════════════════════════════════════════════════
print("\n(b) INTER-POINT DELTA DISTRIBUTION (minutes)")
print("=" * 80)

deltas_by_book = defaultdict(list)

for ev in events:
    for fighter in ev.get('fighters', []):
        for book, pts in fighter.get('series', {}).items():
            if len(pts) < 2:
                continue
            for i in range(1, len(pts)):
                delta_min = (pts[i][0] - pts[i-1][0]) / 60000
                deltas_by_book[book].append(delta_min)

print(f"\n{'Book':<15} {'n':>6} {'p10':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p90':>8} {'mean':>8}")
print("-" * 75)
for book in sorted(deltas_by_book):
    d = np.array(deltas_by_book[book])
    if len(d) == 0:
        continue
    pcts = np.percentile(d, [10, 25, 50, 75, 90])
    print(f"{book:<15} {len(d):>6} {pcts[0]:>7.0f}m {pcts[1]:>7.0f}m {pcts[2]:>7.0f}m "
          f"{pcts[3]:>7.0f}m {pcts[4]:>7.0f}m {d.mean():>7.0f}m")

# Estimated polling cadence = median inter-point delta
print(f"\n  Estimated cadence (median delta):")
for book in sorted(deltas_by_book):
    d = np.array(deltas_by_book[book])
    if len(d) > 0:
        print(f"    {book:<15} {np.median(d):>6.0f} min")

# Cross-book timestamp collision rate per fight
print(f"\n  Cross-book timestamp collision rate:")
collision_total = 0
collision_hits = 0

for ev in events:
    for fighter in ev.get('fighters', []):
        books = fighter.get('series', {})
        if len(books) < 2:
            continue
        # Collect all timestamps per book
        all_ts = {}
        for book, pts in books.items():
            all_ts[book] = set(p[0] for p in pts)

        # Check pairs of books
        book_list = list(all_ts.keys())
        for i in range(len(book_list)):
            for j in range(i+1, len(book_list)):
                ts_i = all_ts[book_list[i]]
                ts_j = all_ts[book_list[j]]
                # Collisions: timestamps within 60 seconds
                for t in ts_i:
                    collision_total += 1
                    if any(abs(t - tj) < 60000 for tj in ts_j):  # within 60s
                        collision_hits += 1

if collision_total > 0:
    print(f"    Pairs checked: {collision_total}")
    print(f"    Collisions (<60s): {collision_hits} ({collision_hits/collision_total:.1%})")
    if collision_hits / collision_total > 0.3:
        print(f"    → HIGH: suggests BFO polls all books in batch")
    else:
        print(f"    → LOW: suggests independent feeds or staggered polling")

# ═══════════════════════════════════════════════════════════════════
# (c) POINTS-PER-EVENT BY CALENDAR DATE (capture density drift)
# ═══════════════════════════════════════════════════════════════════
print(f"\n(c) CAPTURE DENSITY DRIFT (points per event by date)")
print("=" * 80)

# Era split: 2025 lychee vs 2026 collector
era_stats = defaultdict(list)

print(f"\n{'Date':<12} {'Fighters':>8} {'Points':>8} {'Pts/fighter':>12} {'Era'}")
print("-" * 55)
for ev in events:
    edate = ev.get('event_date', '?')
    n_fighters = len(ev.get('fighters', []))
    n_pts = sum(sum(len(v) for v in fi['series'].values()) for fi in ev.get('fighters', []))
    ppf = n_pts / n_fighters if n_fighters > 0 else 0
    era = 'lychee' if edate < '2026-01-01' else 'collector'
    era_stats[era].append(ppf)
    print(f"{edate:<12} {n_fighters:>8} {n_pts:>8} {ppf:>11.1f} {era}")

print(f"\nEra summary:")
for era in sorted(era_stats):
    vals = np.array(era_stats[era])
    print(f"  {era}: n={len(vals)}, mean={vals.mean():.1f} pts/fighter, SD={vals.std():.1f}")

# Time trend
dates_numeric = []
ppf_values = []
for ev in events:
    edate = ev.get('event_date', '')
    n_fighters = len(ev.get('fighters', []))
    n_pts = sum(sum(len(v) for v in fi['series'].values()) for fi in ev.get('fighters', []))
    if n_fighters > 0:
        ppf = n_pts / n_fighters
        try:
            days = (datetime.strptime(edate, '%Y-%m-%d') - datetime(2025, 1, 1)).days
            dates_numeric.append(days)
            ppf_values.append(ppf)
        except:
            pass

if len(dates_numeric) > 3:
    from numpy.polynomial import polynomial as P
    coef = np.polyfit(dates_numeric, ppf_values, 1)
    print(f"\n  Linear trend: {coef[0]:+.3f} pts/fighter per day (slope)")
    print(f"  {'TREND PRESENT' if abs(coef[0]) > 0.05 else 'No significant trend'}")
