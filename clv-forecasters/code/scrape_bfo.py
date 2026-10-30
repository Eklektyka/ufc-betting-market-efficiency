#!/usr/bin/env python3
"""Step 2: Parse cached BFO event pages into bfo_odds_ext_2026.csv"""

import re, csv, os, hashlib, urllib.request, time
from datetime import datetime, timezone
from collections import Counter

def parse_event_page(html, bfo_event_id, event_name, event_date):
    """Parse a BFO event page and return moneyline rows."""
    sha = hashlib.sha256(html.encode('utf-8', errors='replace')).hexdigest()
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Find the TWO odds tables
    table_starts = [m.start() for m in re.finditer(r'<table[^>]*class="odds-table', html)]
    if len(table_starts) < 2:
        print(f'  WARNING: {bfo_event_id} has {len(table_starts)} odds tables')
        return []

    # Table 1: fighter names (left column)
    t1_end = html.find('</table>', table_starts[0]) + len('</table>')
    table1 = html[table_starts[0]:t1_end]

    # Table 2: odds grid
    t2_end = html.find('</table>', table_starts[1]) + len('</table>')
    table2 = html[table_starts[1]:t2_end]

    # Parse header from table 2 to get book column order
    header_match = re.search(r'<tr>(.*?)</tr>', table2, re.DOTALL)
    if not header_match:
        print(f'  WARNING: {bfo_event_id} no header row')
        return []

    header_html = header_match.group(1)
    header_ths = re.findall(r'<th[^>]*>(.*?)</th>', header_html, re.DOTALL)
    # First TH is the label column (matches the TH in data rows).
    # Remaining THs map 1:1 to the TDs in data rows.
    books = []
    for th in header_ths[1:]:           # skip label column
        link = re.search(r'>([^<]+)</a>', th)
        if link:
            name = link.group(1).strip()
        else:
            name = re.sub(r'<[^>]+>', '', th).strip().replace('\xa0', '').replace('&nbsp;', '')
        books.append(name)

    # Parse rows from both tables in parallel
    rows1 = re.findall(r'<tr[^>]*>(.*?)</tr>', table1, re.DOTALL)
    rows2 = re.findall(r'<tr[^>]*>(.*?)</tr>', table2, re.DOTALL)
    tr_attrs1 = re.findall(r'<tr([^>]*)>', table1)

    results = []
    current_matchup_id = None
    fighter_side = 0

    for i in range(min(len(rows1), len(rows2))):
        row1 = rows1[i]
        row2 = rows2[i]
        tr_attr = tr_attrs1[i] if i < len(tr_attrs1) else ''

        # Skip header row
        if i == 0:
            continue

        # Skip prop rows
        if 'class="pr"' in f'<tr{tr_attr}>':
            continue

        # Check for matchup ID
        mu = re.search(r'id="mu-(\d+)"', tr_attr)
        if mu:
            current_matchup_id = mu.group(1)
            fighter_side = 1
        else:
            if fighter_side == 1:
                fighter_side = 2
            else:
                continue

        # Extract fighter name and slug from table1
        fighter_link = re.search(
            r'<a href="(/fighters/[^"]+)"[^>]*><span[^>]*>([^<]+)</span></a>', row1
        )
        if not fighter_link:
            fighter_link = re.search(r'<a href="(/fighters/[^"]+)"[^>]*>([^<]+)</a>', row1)
        if not fighter_link:
            continue

        fighter_slug = fighter_link.group(1)
        fighter_name = fighter_link.group(2).strip()

        # Extract odds from table2 TDs
        tds = re.findall(r'<td[^>]*>(.*?)</td>', row2, re.DOTALL)

        for col_idx, td_content in enumerate(tds):
            if col_idx >= len(books):
                break
            book = books[col_idx]
            if not book or book in ('Props', ''):
                continue

            odds_match = re.search(r'<span[^>]*>([+-]?\d+)</span>', td_content)
            if not odds_match:
                continue

            odds_american = odds_match.group(1)

            movement = 'none'
            if 'class="aru' in td_content:
                movement = 'up'
            elif 'class="ard' in td_content:
                movement = 'down'

            is_book = 0 if book in ('Polymarket', 'Kalshi') else 1

            results.append({
                'bfo_event_id': bfo_event_id,
                'event_name': event_name,
                'event_date': event_date,
                'bfo_matchup_id': current_matchup_id,
                'fighter_name': fighter_name,
                'fighter_slug': fighter_slug,
                'fighter_side': fighter_side,
                'book': book,
                'odds_american': int(odds_american),
                'movement_flag': movement,
                'is_book': is_book,
                'source': 'bfo_event_page',
                'collected_at_utc': now,
                'page_sha256': sha,
            })

    return results


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Load completed events from index
    events_to_scrape = []
    with open('bfo_events_ext_2026.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['status'] == 'completed':
                events_to_scrape.append(row)

    # Add Step 4 convention-diff event
    step4_events = [
        {'bfo_event_id': '4107', 'event_name': 'UFC Fight Night: Moicano vs. Duncan',
         'event_date': '2026-04-04', 'url': '/events/ufc-vegas-115-4107'},
    ]

    all_events = step4_events + events_to_scrape
    all_rows = []
    fetched_count = 0

    for evt in all_events:
        eid = evt['bfo_event_id']
        url_path = evt['url']
        slug_id = url_path.split('/events/')[-1]
        cache_path = f'raw_html/{slug_id}.html'

        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8', errors='replace') as f:
                html = f.read()
        else:
            url = f'https://www.bestfightodds.com{url_path}'
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            })
            try:
                resp = urllib.request.urlopen(req, timeout=20)
                raw = resp.read()
                with open(cache_path, 'wb') as f:
                    f.write(raw)
                html = raw.decode('utf-8', errors='replace')
                fetched_count += 1
                time.sleep(8)
            except Exception as e:
                print(f'  FETCH ERROR {eid} {slug_id}: {e}')
                continue

        rows = parse_event_page(html, eid, evt['event_name'], evt['event_date'])
        n_matchups = len(set(r['bfo_matchup_id'] for r in rows))
        n_fighters = len(set(r['fighter_name'] for r in rows))
        print(f'  {eid}: {evt["event_name"][:45]:<45} | {n_matchups:>2} matchups, {n_fighters:>2} fighters, {len(rows):>3} odds rows')
        all_rows.extend(rows)

    print(f'\nTotal: {len(all_rows)} rows, fetched {fetched_count} new pages')

    # Write bfo_odds_ext_2026.csv
    fieldnames = [
        'bfo_event_id', 'event_name', 'event_date', 'bfo_matchup_id',
        'fighter_name', 'fighter_slug', 'fighter_side', 'book',
        'odds_american', 'movement_flag', 'is_book', 'source',
        'collected_at_utc', 'page_sha256',
    ]
    with open('bfo_odds_ext_2026.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in all_rows:
            w.writerow(row)
    print(f'Wrote bfo_odds_ext_2026.csv: {len(all_rows)} rows')

    # Summary
    book_counts = Counter(r['book'] for r in all_rows)
    print('\n=== ODDS PER BOOK ===')
    for book, count in book_counts.most_common():
        print(f'  {book:<15} {count}')

    event_summary = {}
    for r in all_rows:
        eid = r['bfo_event_id']
        if eid not in event_summary:
            event_summary[eid] = {'name': r['event_name'], 'matchups': set(), 'books': set()}
        event_summary[eid]['matchups'].add(r['bfo_matchup_id'])
        event_summary[eid]['books'].add(r['book'])

    print('\n=== PER-EVENT SUMMARY ===')
    for eid in sorted(event_summary, key=lambda x: int(x)):
        s = event_summary[eid]
        print(f'  {eid}: {s["name"][:40]:<40} | {len(s["matchups"]):>2} matchups | books: {", ".join(sorted(s["books"]))}')


if __name__ == '__main__':
    main()
