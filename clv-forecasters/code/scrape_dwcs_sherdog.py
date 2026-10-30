#!/usr/bin/env python3
"""Scrape DWCS results from Sherdog. No login needed."""
import sys, time, re, csv, json
sys.stdout.reconfigure(encoding='utf-8')
import os; os.chdir(os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright

# Load our fight pairs (need to match winners)
with open('dwcs_fights.csv', encoding='utf-8') as f:
    fights = list(csv.DictReader(f))
print(f"Fight pairs to match: {len(fights)}")

# Sherdog DWCS events listing: search for each season
# Sherdog URL pattern: /events/Dana-Whites-Contender-Series-Season-N-NNNNN

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    page = ctx.new_page()

    # Search Sherdog for DWCS events
    print("Searching Sherdog for DWCS events...", flush=True)
    page.goto('https://www.sherdog.com/search?q=contender+series&type=Event',
              timeout=30000, wait_until='domcontentloaded')
    time.sleep(2)

    # Get all event links from search results
    html = page.content()
    event_links = re.findall(r'href="(/events/[^"]*[Cc]ontender[^"]*)"', html)
    # Also try the organizations page
    page.goto('https://www.sherdog.com/organizations/Dana-Whites-Contender-Series-10578',
              timeout=30000, wait_until='domcontentloaded')
    time.sleep(2)
    html2 = page.content()
    event_links2 = re.findall(r'href="(/events/[^"]*)"', html2)

    all_links = list(set(event_links + event_links2))
    # Filter to DWCS-related
    dwcs_links = [l for l in all_links if 'contender' in l.lower() or 'dwcs' in l.lower()]
    print(f"DWCS event links found: {len(dwcs_links)}")

    if not dwcs_links:
        # Try direct organization page with past events
        print("Trying organization past events page...", flush=True)
        page.goto('https://www.sherdog.com/organizations/Dana-Whites-Contender-Series-10578/past-events/1',
                  timeout=30000, wait_until='domcontentloaded')
        time.sleep(2)
        html3 = page.content()
        dwcs_links = re.findall(r'href="(/events/[^"]*)"', html3)
        dwcs_links = [l for l in dwcs_links if 'contender' in l.lower() or 'dwcs' in l.lower()]
        print(f"Past events links: {len(dwcs_links)}")

        # Paginate
        for pg in range(2, 8):
            page.goto(f'https://www.sherdog.com/organizations/Dana-Whites-Contender-Series-10578/past-events/{pg}',
                      timeout=30000, wait_until='domcontentloaded')
            time.sleep(1.5)
            html_pg = page.content()
            more = re.findall(r'href="(/events/[^"]*)"', html_pg)
            more = [l for l in more if 'contender' in l.lower() or 'dwcs' in l.lower()]
            if not more: break
            dwcs_links.extend(more)
            print(f"  Page {pg}: +{len(more)} links (total {len(dwcs_links)})")

    dwcs_links = list(set(dwcs_links))
    print(f"Total unique DWCS links: {len(dwcs_links)}")

    # Scrape each event page for fight results
    for link in sorted(dwcs_links):
        url = f'https://www.sherdog.com{link}' if link.startswith('/') else link
        try:
            page.goto(url, timeout=15000, wait_until='domcontentloaded')
        except:
            print(f"  TIMEOUT: {link[:50]}"); continue
        time.sleep(1.5)

        title = page.title()
        event_name = title.split('|')[0].strip() if '|' in title else title

        # Sherdog fight cards show results in sections
        # Each fight has: fighter names, result (win/loss), method
        # Look for fight result sections
        fight_sections = page.query_selector_all('.fight_card, .event_match, [itemprop="subEvent"], .fightCard')
        if not fight_sections:
            # Try broader selectors
            fight_sections = page.query_selector_all('section.fight, div.fight_card, tr.fight')

        if not fight_sections:
            # Parse from raw HTML — Sherdog fight results are in a consistent format
            html_ev = page.content()
            # Pattern: winner name, "def.", loser name, method
            fight_matches = re.findall(
                r'itemprop="name"[^>]*>([^<]+)</span>.*?(?:def\.|defeats?).*?itemprop="name"[^>]*>([^<]+)</span>',
                html_ev, re.DOTALL | re.IGNORECASE
            )
            if not fight_matches:
                # Try simpler: look for "def." pattern
                fight_matches = re.findall(
                    r'<span[^>]*>([^<]{3,30})</span>\s*(?:</a>)?\s*def\.\s*(?:<a[^>]*>)?\s*<span[^>]*>([^<]{3,30})</span>',
                    html_ev, re.IGNORECASE
                )

            n_found = len(fight_matches)
            for winner, loser in fight_matches:
                winner = winner.strip(); loser = loser.strip()
                results.append({
                    'event': event_name, 'winner': winner, 'loser': loser,
                    'source': 'sherdog',
                })

            if n_found > 0:
                print(f"  {event_name[:45]:<45} {n_found} fights")
            else:
                # Last resort: dump what we can find
                names_on_page = page.query_selector_all('[itemprop="name"]')
                n_names = len(names_on_page)
                print(f"  {event_name[:45]:<45} 0 fights ({n_names} name elements)")
        else:
            n_found = 0
            for section in fight_sections:
                text = section.inner_text()
                # Parse winner/loser from section
                names = section.query_selector_all('[itemprop="name"]')
                if len(names) >= 2:
                    winner = names[0].inner_text().strip()
                    loser = names[1].inner_text().strip()
                    results.append({
                        'event': event_name, 'winner': winner, 'loser': loser,
                        'source': 'sherdog',
                    })
                    n_found += 1
            print(f"  {event_name[:45]:<45} {n_found} fights")

    browser.close()

# Save
with open('dwcs_sherdog_results.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['event', 'winner', 'loser', 'source'])
    w.writeheader()
    w.writerows(results)

print(f"\nTotal results: {len(results)}")
print(f"Saved to dwcs_sherdog_results.csv")
