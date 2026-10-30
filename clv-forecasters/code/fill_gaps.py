#!/usr/bin/env python3
"""Scrape the 6 missing UFC events into fill tables."""

import csv, re, os, hashlib, time
from datetime import datetime, timezone
from collections import defaultdict, Counter
from statistics import median

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Import parser from scrape_bfo.py
from scrape_bfo import parse_event_page

fill_events = [
    # (eid, slug, card_key, canonical_date, segment)
    (3818, 'ufc', 'UFC Fight Night: Walker vs. Zhang', '2025-08-23', 'early_prelims'),
    (3812, 'ufc', 'UFC Fight Night: Walker vs. Zhang', '2025-08-23', 'main'),
    (3913, 'ufc-vegas-110', 'UFC Fight Night: Garcia vs. Onama', '2025-11-01', 'main'),
    (3941, 'ufc-qatar', 'UFC Fight Night: Tsarukyan vs. Hooker', '2025-11-22', 'main'),
    (3971, 'ufc', 'UFC 325: Volkanovski vs. Lopes 2', '2026-01-31', 'main'),
    (4044, 'ufc-houston', 'UFC Fight Night: Strickland vs. Hernandez', '2026-02-21', 'early_prelims'),
    (3996, 'ufc', 'UFC Fight Night: Strickland vs. Hernandez', '2026-02-21', 'main'),
    (4081, 'ufc-london', 'UFC Fight Night: Evloev vs. Murphy', '2026-03-21', 'main'),
]


def implied_prob(american):
    a = int(american)
    return 1 / (1 + a / 100) if a > 0 else 1 / (1 + 100 / abs(a))


def main():
    all_rows = []
    for eid, slug, card_key, cdate, segment in fill_events:
        cache = f'raw_html/{slug}-{eid}.html'
        with open(cache, 'r', encoding='utf-8', errors='replace') as f:
            html = f.read()

        rows = parse_event_page(html, str(eid), card_key, cdate)
        # Override source tag
        for r in rows:
            r['source'] = 'bfo_event_page_fill'
        n_mu = len(set(r['bfo_matchup_id'] for r in rows))
        n_f = len(set(r['fighter_name'] for r in rows))
        print(f'  {eid}: {card_key[:45]:<45} ({segment:15}) '
              f'| {n_mu:>2} matchups, {n_f:>2} fighters, {len(rows):>3} odds')
        all_rows.extend(rows)

    # Write bfo_odds_fill_2025.csv
    fieldnames = [
        'bfo_event_id', 'event_name', 'event_date', 'bfo_matchup_id',
        'fighter_name', 'fighter_slug', 'fighter_side', 'book',
        'odds_american', 'movement_flag', 'is_book', 'source',
        'collected_at_utc', 'page_sha256',
    ]
    with open('bfo_odds_fill_2025.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)
    print(f'\nWrote bfo_odds_fill_2025.csv: {len(all_rows)} rows')

    # Derive bfo_close_fill_2025.csv
    odds_by_matchup = defaultdict(lambda: {'f1': {}, 'f2': {}, 'meta': {}})
    for row in all_rows:
        mid = row['bfo_matchup_id']
        side = str(row['fighter_side'])
        key = 'f1' if side == '1' else 'f2'
        odds_by_matchup[mid][key][row['book']] = int(row['odds_american'])
        odds_by_matchup[mid]['meta'][f'f{side}_name'] = row['fighter_name']
        odds_by_matchup[mid]['meta'][f'f{side}_slug'] = row['fighter_slug']
        odds_by_matchup[mid]['meta']['bfo_event_id'] = str(row['bfo_event_id'])
        odds_by_matchup[mid]['meta']['event_name'] = row['event_name']
        odds_by_matchup[mid]['meta']['event_date'] = row['event_date']

    derived = []
    for mid, data in odds_by_matchup.items():
        meta = data['meta']
        f1_sb = {b: o for b, o in data['f1'].items()
                 if b not in ('Polymarket', 'Kalshi')}
        f2_sb = {b: o for b, o in data['f2'].items()
                 if b not in ('Polymarket', 'Kalshi')}
        if not f1_sb or not f2_sb:
            continue

        f1_med = median(f1_sb.values())
        f2_med = median(f2_sb.values())
        f1_ip = implied_prob(f1_med)
        f2_ip = implied_prob(f2_med)
        total = f1_ip + f2_ip

        best_a = max(f1_sb.items(), key=lambda x: x[1])
        best_b = max(f2_sb.items(), key=lambda x: x[1])
        pa = implied_prob(best_a[1])
        pb = implied_prob(best_b[1])
        ptotal = pa + pb

        derived.append({
            'bfo_event_id': meta['bfo_event_id'],
            'event_name': meta['event_name'],
            'event_date': meta['event_date'],
            'bfo_matchup_id': mid,
            'fighter1_name': meta.get('f1_name', ''),
            'fighter1_slug': meta.get('f1_slug', ''),
            'fighter2_name': meta.get('f2_name', ''),
            'fighter2_slug': meta.get('f2_slug', ''),
            'f1_consensus_american': round(f1_med),
            'f2_consensus_american': round(f2_med),
            'f1_implied_prob': round(f1_ip, 4),
            'f2_implied_prob': round(f2_ip, 4),
            'f1_devigged_prob': round(f1_ip / total, 4),
            'f2_devigged_prob': round(f2_ip / total, 4),
            'f1_best_line': best_a[1],
            'f2_best_line': best_b[1],
            'n_books': len(f1_sb),
            'best_line_a': best_a[1],
            'best_book_a': best_a[0],
            'best_line_b': best_b[1],
            'best_book_b': best_b[0],
            'p_fair_a': round(pa / ptotal, 4),
            'p_fair_b': round(pb / ptotal, 4),
        })

    derived.sort(key=lambda r: (r['event_date'], r['bfo_matchup_id']))
    with open('bfo_close_fill_2025.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(derived[0].keys()))
        w.writeheader()
        w.writerows(derived)
    print(f'Wrote bfo_close_fill_2025.csv: {len(derived)} matchups')

    # Update card_map
    existing = []
    existing_eids = set()
    with open('card_map.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            existing.append(row)
            existing_eids.add(row['bfo_event_id'])

    added = 0
    for eid, slug, card_key, cdate, segment in fill_events:
        if str(eid) not in existing_eids:
            existing.append({
                'bfo_event_id': str(eid),
                'card_key': card_key,
                'canonical_date': cdate,
                'segment': segment,
            })
            added += 1

    existing.sort(key=lambda r: (r['canonical_date'], r['bfo_event_id']))
    with open('card_map.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=[
            'bfo_event_id', 'card_key', 'canonical_date', 'segment'])
        w.writeheader()
        w.writerows(existing)
    print(f'\ncard_map.csv: {len(existing)} rows ({added} new)')

    book_counts = Counter(r['book'] for r in all_rows)
    print('\nBooks:')
    for b, c in book_counts.most_common():
        print(f'  {b}: {c}')


if __name__ == '__main__':
    main()
