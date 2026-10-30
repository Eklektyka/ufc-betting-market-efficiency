#!/usr/bin/env python3
"""Scrape DWCS results from Sherdog — search by year, then scrape each event."""
import sys, time, re, csv, json
sys.stdout.reconfigure(encoding='utf-8')
import os; os.chdir(os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    page = ctx.new_page()

    # Search for each year's DWCS
    all_links = {}
    for year in range(2017, 2027):
        for query in [f'contender series {year}', f'DWCS {year}']:
            url = f'https://www.sherdog.com/search?q={query.replace(" ", "+")}&type=Event'
            try:
                page.goto(url, timeout=15000, wait_until='domcontentloaded')
                time.sleep(1.5)
            except:
                continue
            html = page.content()
            links = re.findall(r'href="(/events/[^"]*[Cc]ontender[^"]*)"', html)
            for l in links:
                if l not in all_links:
                    all_links[l] = year

        print(f"  {year}: {sum(1 for v in all_links.values() if v == year)} new links (total {len(all_links)})", flush=True)

    print(f"\nTotal DWCS event links: {len(all_links)}")

    # Scrape each event
    for link in sorted(all_links.keys()):
        url = f'https://www.sherdog.com{link}'
        try:
            page.goto(url, timeout=15000, wait_until='domcontentloaded')
        except:
            print(f"  TIMEOUT: {link[:60]}"); continue
        time.sleep(1)

        title = page.title().split('|')[0].strip() if '|' in page.title() else page.title()
        html = page.content()

        # Parse fight results
        # Sherdog format: winner "def." loser via method
        # Look for the fight card section with itemprop="subEvent"
        fight_matches = re.findall(
            r'itemprop="name"[^>]*>([^<]+)</span>.*?def\..*?itemprop="name"[^>]*>([^<]+)</span>',
            html, re.DOTALL
        )

        if not fight_matches:
            # Try alternative pattern
            fight_matches = re.findall(
                r'class="[^"]*fighter[^"]*"[^>]*>.*?<span[^>]*>([^<]{2,35})</span>.*?def\..*?'
                r'class="[^"]*fighter[^"]*"[^>]*>.*?<span[^>]*>([^<]{2,35})</span>',
                html, re.DOTALL
            )

        for winner, loser in fight_matches:
            w = winner.strip(); l = loser.strip()
            if len(w) < 3 or len(l) < 3: continue
            results.append({
                'event': title, 'winner': w, 'loser': l,
                'url': link, 'source': 'sherdog',
            })

        print(f"  {title[:50]:<50} {len(fight_matches)} fights", flush=True)

    browser.close()

# Save
with open('dwcs_sherdog_results.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['event', 'winner', 'loser', 'url', 'source'])
    w.writeheader()
    w.writerows(results)

print(f"\nTotal results: {len(results)}")
print(f"Saved to dwcs_sherdog_results.csv")
