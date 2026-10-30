#!/usr/bin/env python3
"""Scrape remaining rank-window BFO event pages, build bfo_close_rank.csv + bfo_close_all.csv."""

import csv, re, os, hashlib, time, urllib.request
from datetime import datetime, timezone
from collections import defaultdict, Counter
from statistics import median

os.chdir(os.path.dirname(os.path.abspath(__file__)))
from scrape_bfo import parse_event_page

SITEMAP_SLUGS = {
    '3789': 'ufc-fight-night-dolidze-vs-hernandez-odds',
    '3767': 'ufc-319-odds', '3800': 'ufc-319',
    '3775': 'ufc-fight-night', '3776': 'ufc-fight-night',
    '3794': 'ufc-fight-night', '3840': 'ufc-fight-night',
    '3846': 'ufc-fight-night', '3779': 'ufc-320-odds',
    '3853': 'ufc-320', '3869': 'ufc', '3872': 'ufc-rio',
    '3822': 'ufc-fight-night', '3780': 'ufc-321-odds',
    '3917': 'ufc-vegas-111', '3918': 'ufc-vegas-111',
    '3830': 'ufc-322', '3924': 'ufc-322',
    '3895': 'ufc', '3951': 'ufc-323',
    '3987': 'ufc-vegas-112', '3970': 'ufc',
    '3973': 'ufc-324', '4026': 'ufc-fight-night',
    '4033': 'ufc-vegas-113', '4053': 'ufc-mexico',
    '4025': 'ufc', '4065': 'ufc-326',
    '4080': 'ufc-vegas-114', '4018': 'ufc-seattle',
    '4095': 'ufc-seattle', '4074': 'ufc-327',
}

RANK_EVENTS = [
    ('3789', 'UFC Fight Night: Dolidze vs. Hernandez', '2025-08-09', 'main'),
    ('3767', 'UFC 319: Du Plessis vs. Chimaev', '2025-08-16', 'early_prelims'),
    ('3800', 'UFC 319: Du Plessis vs. Chimaev', '2025-08-16', 'main'),
    ('3775', 'UFC Fight Night: Imavov vs. Borralho', '2025-09-06', 'main'),
    ('3776', 'UFC Fight Night: Lopes vs. Silva', '2025-09-13', 'main'),
    ('3794', 'UFC Fight Night: Lopes vs. Silva', '2025-09-13', 'early_prelims'),
    ('3840', 'UFC Fight Night: Ulberg vs. Reyes', '2025-09-27', 'early_prelims'),
    ('3846', 'UFC Fight Night: Ulberg vs. Reyes', '2025-09-27', 'main'),
    ('3779', 'UFC 320: Ankalaev vs. Pereira 2', '2025-10-04', 'main'),
    ('3853', 'UFC 320: Ankalaev vs. Pereira 2', '2025-10-04', 'early_prelims'),
    ('3869', 'UFC Fight Night: Oliveira vs. Gamrot', '2025-10-11', 'main'),
    ('3872', 'UFC Fight Night: Oliveira vs. Gamrot', '2025-10-11', 'early_prelims'),
    ('3822', 'UFC Fight Night: De Ridder vs. Allen', '2025-10-18', 'main'),
    ('3780', 'UFC 321: Aspinall vs. Gane', '2025-10-25', 'main'),
    ('3917', 'UFC Fight Night: Bonfim vs. Brown', '2025-11-08', 'main'),
    ('3918', 'UFC Fight Night: Bonfim vs. Brown', '2025-11-08', 'early_prelims'),
    ('3830', 'UFC 322: Della Maddalena vs. Makhachev', '2025-11-15', 'main'),
    ('3924', 'UFC 322: Della Maddalena vs. Makhachev', '2025-11-15', 'early_prelims'),
    ('3895', 'UFC 323: Dvalishvili vs. Yan 2', '2025-12-06', 'main'),
    ('3951', 'UFC 323: Dvalishvili vs. Yan 2', '2025-12-06', 'early_prelims'),
    ('3987', 'UFC Fight Night: Royval vs. Kape', '2025-12-13', 'main'),
    ('3970', 'UFC 324: Gaethje vs. Pimblett', '2026-01-24', 'main'),
    ('3973', 'UFC 324: Gaethje vs. Pimblett', '2026-01-24', 'early_prelims'),
    ('4026', 'UFC Fight Night: Bautista vs. Oliveira', '2026-02-07', 'early_prelims'),
    ('4033', 'UFC Fight Night: Bautista vs. Oliveira', '2026-02-07', 'main'),
    ('4053', 'UFC Fight Night: Moreno vs. Kavanagh', '2026-02-28', 'main'),
    ('4025', 'UFC 326: Holloway vs. Oliveira 2', '2026-03-07', 'main'),
    ('4065', 'UFC 326: Holloway vs. Oliveira 2', '2026-03-07', 'early_prelims'),
    ('4080', 'UFC Fight Night: Emmett vs. Vallejos', '2026-03-14', 'main'),
    ('4018', 'UFC Fight Night: Adesanya vs. Pyfer', '2026-03-28', 'main'),
    ('4095', 'UFC Fight Night: Adesanya vs. Pyfer', '2026-03-28', 'early_prelims'),
    ('4074', 'UFC 327: Prochazka vs. Ulberg', '2026-04-11', 'main'),
]


def implied_prob(american):
    a = int(american)
    if a == 0:
        return 0.5
    return 1 / (1 + a / 100) if a > 0 else 1 / (1 + 100 / abs(a))


def main():
    # Fetch pages
    all_odds = []
    fetched = 0
    for eid, card_key, cdate, segment in RANK_EVENTS:
        slug = SITEMAP_SLUGS[eid]
        cache = f'raw_html/{slug}-{eid}.html'

        if os.path.exists(cache):
            with open(cache, 'r', encoding='utf-8', errors='replace') as f:
                html = f.read()
        else:
            url = f'https://www.bestfightodds.com/events/{slug}-{eid}'
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/126.0.0.0 Safari/537.36',
            })
            try:
                resp = urllib.request.urlopen(req, timeout=20)
                raw = resp.read()
                with open(cache, 'wb') as f:
                    f.write(raw)
                html = raw.decode('utf-8', errors='replace')
                fetched += 1
                time.sleep(8)
            except Exception as e:
                print(f'  FETCH ERROR {eid}: {e}')
                continue

        rows = parse_event_page(html, eid, card_key, cdate)
        for r in rows:
            r['source'] = 'bfo_event_page_rank'
        n_mu = len(set(r['bfo_matchup_id'] for r in rows))
        print(f'  {eid}: {card_key[:42]:<42} ({segment:15}) '
              f'| {n_mu:>2} matchups, {len(rows):>3} odds')
        all_odds.append(rows)

    flat_odds = [r for batch in all_odds for r in batch]
    print(f'\nTotal rank odds rows: {len(flat_odds)}, fetched {fetched} new pages')

    # Also merge fill odds
    with open('bfo_odds_fill_2025.csv', 'r', encoding='utf-8') as f:
        fill_odds = list(csv.DictReader(f))
    print(f'Fill odds rows: {len(fill_odds)}')

    combined_odds = flat_odds + [{**r, 'odds_american': int(r['odds_american']),
                                   'is_book': int(r['is_book']),
                                   'fighter_side': int(r['fighter_side'])}
                                  for r in fill_odds]

    # Write bfo_odds_rank.csv (rank + fill combined)
    fieldnames = [
        'bfo_event_id', 'event_name', 'event_date', 'bfo_matchup_id',
        'fighter_name', 'fighter_slug', 'fighter_side', 'book',
        'odds_american', 'movement_flag', 'is_book', 'source',
        'collected_at_utc', 'page_sha256',
    ]
    with open('bfo_odds_rank.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in combined_odds:
            w.writerow(r)

    # Derive bfo_close_rank.csv
    odds_by_mu = defaultdict(lambda: {'f1': {}, 'f2': {}, 'meta': {}})
    for r in combined_odds:
        mid = r['bfo_matchup_id']
        side = str(r['fighter_side'])
        key = 'f1' if side == '1' else 'f2'
        if int(r['is_book']) == 1:
            odds_by_mu[mid][key][r['book']] = int(r['odds_american'])
        odds_by_mu[mid]['meta'][f'f{side}_name'] = r['fighter_name']
        odds_by_mu[mid]['meta'][f'f{side}_slug'] = r.get('fighter_slug', '')
        odds_by_mu[mid]['meta']['bfo_event_id'] = str(r['bfo_event_id'])
        odds_by_mu[mid]['meta']['event_name'] = r['event_name']
        odds_by_mu[mid]['meta']['event_date'] = r['event_date']

    derived = []
    for mid, data in odds_by_mu.items():
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
    with open('bfo_close_rank.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(derived[0].keys()))
        w.writeheader()
        w.writerows(derived)
    print(f'Wrote bfo_close_rank.csv: {len(derived)} matchups')

    # Concatenate rank + ext → bfo_close_all.csv
    ext_rows = []
    with open('bfo_close_ext_2026.csv', 'r', encoding='utf-8') as f:
        ext_rows = list(csv.DictReader(f))

    all_close = derived + ext_rows
    all_close.sort(key=lambda r: (r['event_date'], r['bfo_matchup_id']))

    with open('bfo_close_all.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(all_close[0].keys()))
        w.writeheader()
        w.writerows(all_close)
    print(f'Wrote bfo_close_all.csv: {len(all_close)} matchups '
          f'({len(derived)} rank + {len(ext_rows)} ext)')


if __name__ == '__main__':
    main()
