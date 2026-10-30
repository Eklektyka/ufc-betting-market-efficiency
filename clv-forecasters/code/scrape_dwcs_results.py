#!/usr/bin/env python3
"""Scrape DWCS results from BFO event pages (results are shown inline)."""
import csv, json, os, re, sys, time, unicodedata
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright

# DWCS BFO event IDs from bfo_odds_raw
dwcs_events = {}
path = r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_raw.csv'
with open(path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        name = r['event_name'].lower()
        if 'contender' in name or 'dwcs' in name:
            eid = r['event_bfo_id']
            if eid not in dwcs_events:
                dwcs_events[eid] = {'name': r['event_name'], 'date': r['date_raw']}

# Filter to 2017+ (when DWCS started)
target = {eid: v for eid, v in dwcs_events.items()
           if any(str(y) in v['date'] for y in range(2017, 2027))}

print(f"DWCS events to scrape: {len(target)}")

# We need event URL slugs. Try common patterns.
# BFO URL format: /events/SLUG-{eid}
# For DWCS, the slug varies. We'll search BFO for each.

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    page = ctx.new_page()

    for eid, info in sorted(target.items(), key=lambda x: x[1]['date']):
        # Try to find the event page by searching
        # Common DWCS slugs: dana-whites-contender-series-{N}-{eid}, dwcs-week-{N}-{eid}
        # Simplest: try /events/dana-whites-contender-series-{eid}
        # Or search BFO

        # Try multiple URL patterns
        urls_to_try = [
            f'https://www.bestfightodds.com/events/dana-whites-contender-series-{int(float(eid))}',
            f'https://www.bestfightodds.com/events/contender-series-{int(float(eid))}',
            f'https://www.bestfightodds.com/events/dwcs-week-{int(float(eid))}',
        ]

        found = False
        for url in urls_to_try:
            try:
                resp = page.goto(url, timeout=15_000, wait_until='domcontentloaded')
                if resp and resp.status == 200:
                    title = page.title()
                    if 'contender' in title.lower() or 'dwcs' in title.lower():
                        found = True; break
            except:
                continue

        if not found:
            # Search BFO
            search_url = f'https://www.bestfightodds.com/search?query={info["name"].replace(" ", "+")}'
            try:
                page.goto(search_url, timeout=15_000, wait_until='domcontentloaded')
                time.sleep(1)
                html = page.content()
                # Find event link with matching eid
                eid_int = int(float(eid))
                match = re.search(rf'href="(/events/[^"]*-{eid_int})"', html)
                if match:
                    page.goto(f'https://www.bestfightodds.com{match.group(1)}',
                              timeout=15_000, wait_until='domcontentloaded')
                    found = True
            except:
                pass

        if not found:
            print(f"  SKIP {info['name']} ({info['date']}) — page not found")
            continue

        time.sleep(1)

        # Parse results from the page
        # BFO event pages have two tables: names (table 1) and odds (table 2)
        # Fighter rows are paired; the result is not directly shown on BFO event pages.
        # Actually, BFO event pages DON'T show results — they show odds only.
        # We need a different source.

        # However: the fighter name table shows the winning fighter's name in BOLD
        # or with a special class. Let me check.
        tables = page.query_selector_all('table')
        name_table = None
        for t in tables:
            if t.query_selector('th span.t-b-fcc'):
                name_table = t; break

        if not name_table:
            print(f"  SKIP {info['name']} ({info['date']}) — no name table")
            continue

        rows = name_table.query_selector_all('tbody tr')
        fight_count = 0

        i = 0
        while i < len(rows):
            cls = rows[i].get_attribute('class') or ''
            if 'pr' in cls: i += 1; continue

            ne = rows[i].query_selector('th span.t-b-fcc')
            if not ne: i += 1; continue
            fighter_a = ne.inner_text().strip()

            # Check if this row has a "winner" indicator
            # BFO uses a green/bold style for the winner
            # Let's check the row's HTML for win indicators
            row_html = rows[i].evaluate('el => el.outerHTML')
            a_wins = 'class="steep"' in row_html or 'winner' in row_html.lower()

            # Next non-prop row = fighter B
            j = i + 1
            while j < len(rows):
                cls_b = rows[j].get_attribute('class') or ''
                if 'pr' not in cls_b:
                    ne_b = rows[j].query_selector('th span.t-b-fcc')
                    if ne_b:
                        fighter_b = ne_b.inner_text().strip()
                        row_b_html = rows[j].evaluate('el => el.outerHTML')
                        b_wins = 'class="steep"' in row_b_html or 'winner' in row_b_html.lower()

                        # Determine winner
                        if a_wins and not b_wins:
                            winner = fighter_a
                        elif b_wins and not a_wins:
                            winner = fighter_b
                        else:
                            winner = ''  # can't determine

                        results.append({
                            'event': info['name'], 'date': info['date'],
                            'fighter_a': fighter_a, 'fighter_b': fighter_b,
                            'winner': winner, 'bfo_event_id': eid,
                        })
                        fight_count += 1
                        i = j + 1
                        break
                j += 1
            else:
                i += 1

        print(f"  {info['name'][:40]:<40} ({info['date']}) — {fight_count} fights, "
              f"{sum(1 for r in results[-fight_count:] if r['winner'])} with winners")

    browser.close()

# Save
out_path = 'dwcs_results.csv'
with open(out_path, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['event', 'date', 'fighter_a', 'fighter_b', 'winner', 'bfo_event_id'])
    w.writeheader()
    w.writerows(results)

print(f"\nSaved {len(results)} fights to {out_path}")
print(f"With winners: {sum(1 for r in results if r['winner'])}")
print(f"Without winners: {sum(1 for r in results if not r['winner'])}")
