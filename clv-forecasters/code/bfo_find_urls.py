#!/usr/bin/env python3
"""Find BFO event URLs for the May-Aug 2025 events missing from our URL table."""
import sys, time, json, re, random
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

# Events we need URLs for (from bfo_close_all.csv dates)
MISSING_DATES = [
    ('2025-05-10', 'UFC 315'),
    ('2025-05-17', 'UFC Fight Night'),
    ('2025-05-31', 'UFC Fight Night'),
    ('2025-06-07', 'UFC 316'),
    ('2025-06-14', 'UFC Freedom 250'),
    ('2025-06-15', 'UFC Freedom 250'),
    ('2025-06-21', 'UFC Fight Night'),
    ('2025-06-28', 'UFC Fight Night'),
    ('2025-07-12', 'UFC 317'),
    ('2025-07-19', 'UFC Fight Night'),
    ('2025-07-26', 'UFC Fight Night'),
    ('2025-08-02', 'UFC 318'),
]

found = {}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    page = ctx.new_page()

    for date, name in MISSING_DATES:
        # Try numbered UFC search first
        queries = [name, f"UFC {date[:7]}"]
        for q in queries:
            url = f'https://www.bestfightodds.com/search?query={q.replace(" ", "+")}'
            page.goto(url, timeout=30_000, wait_until='domcontentloaded')
            time.sleep(1 + random.random())

            html = page.content()
            matches = re.findall(r'href="(/events/([^"]+))"[^>]*>([^<]{3,80})</a>', html)
            for path, slug, text in matches:
                text = text.strip()
                if 'ufc' in text.lower():
                    # Check if this is the right date by looking for the slug
                    m = re.search(r'-(\d+)$', slug)
                    if m:
                        eid = m.group(1)
                        # We can verify by loading the page, but let's be smart
                        # Check if the date or month appears
                        month_map = {'05': 'may', '06': 'jun', '07': 'jul', '08': 'aug'}
                        month = date[5:7]
                        if month in month_map and month_map[month] in slug.lower():
                            found[date] = path
                            break
                        # For numbered UFCs, check the number
                        if name.startswith('UFC ') and name[4:].isdigit():
                            if name[4:] in text:
                                found[date] = path
                                break
            if date in found:
                break

        if date in found:
            print(f'{date}: {found[date]}')
        else:
            print(f'{date}: NOT FOUND')

    browser.close()

print(f'\nFound {len(found)}/{len(MISSING_DATES)}')
# Write to a file
with open('C:/Research/ufc/odds/data/bfo/missing_urls.json', 'w') as f:
    json.dump(found, f, indent=2)
