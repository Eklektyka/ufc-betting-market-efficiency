#!/usr/bin/env python3
"""Parse method-of-victory prop odds from cached BFO event HTML pages.

Uses the same raw_html/ cache as scrape_bfo.py. No network requests needed.

Outputs:
  bfo_mov_odds.csv — one row per method prop per fighter per bout
"""

import re, csv, os, sys
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Method-of-victory prop patterns (applied to prop row text)
MOV_PATTERNS = [
    (r"^(.+?) wins by TKO/KO$", "ko_tko"),
    (r"^(.+?) wins by submission$", "submission"),
    (r"^(.+?) wins by decision$", "decision"),
    (r"^(.+?) wins inside distance$", "inside_distance"),
]

FIELDNAMES = [
    "bfo_event_id", "event_name", "event_date",
    "bfo_matchup_id", "fighter_a", "fighter_b",
    "prop_text", "prop_type", "prop_fighter",
    "book", "odds_american",
]


def parse_event_mov(html, bfo_event_id, event_name, event_date):
    """Parse MoV props from a BFO event page HTML string."""

    # Find the TWO odds tables
    table_starts = [m.start() for m in re.finditer(r'<table[^>]*class="odds-table', html)]
    if len(table_starts) < 2:
        return []

    # Table 1: fighter names
    t1_end = html.find('</table>', table_starts[0]) + len('</table>')
    table1 = html[table_starts[0]:t1_end]

    # Table 2: odds grid
    t2_end = html.find('</table>', table_starts[1]) + len('</table>')
    table2 = html[table_starts[1]:t2_end]

    # Parse header for book names
    header_match = re.search(r'<tr>(.*?)</tr>', table2, re.DOTALL)
    if not header_match:
        return []

    header_html = header_match.group(1)
    header_ths = re.findall(r'<th[^>]*>(.*?)</th>', header_html, re.DOTALL)
    books = []
    for th in header_ths[1:]:
        link = re.search(r'>([^<]+)</a>', th)
        if link:
            name = link.group(1).strip()
        else:
            name = re.sub(r'<[^>]+>', '', th).strip().replace('\xa0', '').replace('&nbsp;', '')
        books.append(name)

    # Parse rows from both tables
    rows1 = re.findall(r'<tr[^>]*>(.*?)</tr>', table1, re.DOTALL)
    rows2 = re.findall(r'<tr[^>]*>(.*?)</tr>', table2, re.DOTALL)
    tr_attrs1 = re.findall(r'<tr([^>]*)>', table1)

    results = []
    current_matchup_id = None
    fighter_a = None
    fighter_b = None

    for i in range(min(len(rows1), len(rows2))):
        row1 = rows1[i]
        row2 = rows2[i]
        tr_attr = tr_attrs1[i] if i < len(tr_attrs1) else ''

        if i == 0:
            continue

        is_prop = 'class="pr"' in f'<tr{tr_attr}>'

        if not is_prop:
            # Fighter row
            mu = re.search(r'id="mu-(\d+)"', tr_attr)
            if mu:
                current_matchup_id = mu.group(1)
                # Extract fighter name
                fighter_link = re.search(
                    r'<a href="(/fighters/[^"]+)"[^>]*><span[^>]*>([^<]+)</span></a>', row1
                )
                if not fighter_link:
                    fighter_link = re.search(r'<a href="(/fighters/[^"]+)"[^>]*>([^<]+)</a>', row1)
                if fighter_link:
                    fighter_a = fighter_link.group(2).strip()
                    fighter_b = None
            else:
                # Second fighter in pair
                fighter_link = re.search(
                    r'<a href="(/fighters/[^"]+)"[^>]*><span[^>]*>([^<]+)</span></a>', row1
                )
                if not fighter_link:
                    fighter_link = re.search(r'<a href="(/fighters/[^"]+)"[^>]*>([^<]+)</a>', row1)
                if fighter_link:
                    fighter_b = fighter_link.group(2).strip()
        else:
            # Prop row — check if it's a MoV prop
            if not fighter_a or not fighter_b or not current_matchup_id:
                continue

            # Get prop text from table1 row
            prop_text_match = re.search(r'<th[^>]*>(.*?)</th>', row1, re.DOTALL)
            if not prop_text_match:
                continue
            prop_text = re.sub(r'<[^>]+>', '', prop_text_match.group(1)).strip()

            for pattern, prop_type in MOV_PATTERNS:
                m = re.match(pattern, prop_text, re.IGNORECASE)
                if m:
                    prop_fighter = m.group(1).strip()

                    # Extract odds from table2 row TDs
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

                        results.append({
                            "bfo_event_id": bfo_event_id,
                            "event_name": event_name,
                            "event_date": event_date,
                            "bfo_matchup_id": current_matchup_id,
                            "fighter_a": fighter_a,
                            "fighter_b": fighter_b,
                            "prop_text": prop_text,
                            "prop_type": prop_type,
                            "prop_fighter": prop_fighter,
                            "book": book,
                            "odds_american": int(odds_match.group(1)),
                        })
                    break

    return results


def main():
    # Combine event sources:
    # 1. bfo_events_ext_2026.csv (post-April events)
    # 2. Pre-April events from bfo_odds_raw.csv mapped to cached HTML

    events = {}  # bfo_event_id -> {name, date, html_file}

    # Source 1: ext_2026 event list
    with open('bfo_events_ext_2026.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            eid = row['bfo_event_id']
            slug = row['url'].split('/events/')[-1]
            html_path = f'raw_html/{slug}.html'
            events[eid] = {
                'name': row['event_name'],
                'date': row['event_date'],
                'html': html_path,
            }

    # Source 2: scan raw_html/ for pre-April cached pages
    # These are pages from the bfo_odds_raw.csv era (pre-Apr 2026)
    html_dir = Path('raw_html')
    for f in html_dir.glob('ufc*.html'):
        m = re.search(r'-(\d+)\.html$', f.name)
        if not m:
            continue
        eid = m.group(1)
        if eid in events:
            continue
        # Read event name from HTML
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            html_head = fh.read(5000)
        title_match = re.search(r'<title>([^<]+)</title>', html_head)
        name = title_match.group(1).strip() if title_match else f.stem
        # Clean up title
        name = re.sub(r'\s*\|.*$', '', name)
        name = re.sub(r'\s+Odds$', '', name)

        # Try to get date from HTML
        date_match = re.search(r'"startDate"\s*:\s*"(\d{4}-\d{2}-\d{2})"', html_head)
        date = date_match.group(1) if date_match else ''

        events[eid] = {
            'name': name,
            'date': date,
            'html': str(f),
        }

    # Also add the manually specified step4 event
    if '4107' not in events:
        events['4107'] = {
            'name': 'UFC Fight Night: Moicano vs. Duncan',
            'date': '2026-04-04',
            'html': 'raw_html/ufc-vegas-115-4107.html',
        }

    # Filter to UFC events only and sort by event ID
    ufc_events = {eid: v for eid, v in events.items()
                  if v['name'].lower().startswith('ufc') or v['name'].lower().startswith('noche ufc')}

    print(f"Total UFC events found: {len(ufc_events)}")

    all_rows = []
    for eid in sorted(ufc_events, key=lambda x: int(x)):
        evt = ufc_events[eid]
        html_path = evt['html']

        if not os.path.exists(html_path):
            print(f"  {eid}: MISSING {html_path}")
            continue

        with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
            html = f.read()

        rows = parse_event_mov(html, eid, evt['name'], evt['date'])
        n_matchups = len(set(r['bfo_matchup_id'] for r in rows)) if rows else 0
        print(f"  {eid}: {evt['name'][:50]:<50} | {n_matchups:>2} matchups | {len(rows):>3} MoV rows")
        all_rows.extend(rows)

    # Write output
    with open('bfo_mov_odds.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for row in all_rows:
            w.writerow(row)

    print(f"\nWrote bfo_mov_odds.csv: {len(all_rows)} rows")

    # Summary
    prop_types = Counter(r['prop_type'] for r in all_rows)
    print("\n=== PROP TYPE BREAKDOWN ===")
    for pt, c in prop_types.most_common():
        print(f"  {pt:<20} {c}")

    events_with_data = set(r['bfo_event_id'] for r in all_rows)
    print(f"\nEvents with MoV data: {len(events_with_data)} / {len(ufc_events)}")


if __name__ == '__main__':
    main()
