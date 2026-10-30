#!/usr/bin/env python3
"""
Step 0: XHR recon — find the BFO chart data endpoint for intraday odds series.
Load one event page, intercept XHR calls, find the chart popup data.
"""
import sys, time, json, re, os
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('data/bfo/chart_raw', exist_ok=True)

# Use a fight from UFC 328 (2026-05-09) — has good data
EVENT_URL = 'https://www.bestfightodds.com/events/ufc-328-4165'

xhr_responses = []

def handle_response(response):
    url = response.url
    ct = response.headers.get('content-type', '')
    if 'json' in ct or 'javascript' in ct or 'chart' in url.lower() or 'odds' in url.lower():
        try:
            body = response.text()
            xhr_responses.append({
                'url': url, 'status': response.status,
                'content_type': ct, 'body_len': len(body),
                'body_preview': body[:500],
            })
        except:
            pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ))
    page = ctx.new_page()
    page.on('response', handle_response)

    print(f"Loading {EVENT_URL}...", flush=True)
    page.goto(EVENT_URL, timeout=30_000, wait_until='domcontentloaded')
    time.sleep(3)

    # The chart popup appears when you click on a fighter's odds cell
    # Try clicking on the first odds cell to trigger the chart XHR
    print("Looking for clickable odds cells...", flush=True)

    # BFO has span elements with oID... that show odds
    # Clicking them may trigger a chart popup via XHR
    odds_spans = page.query_selector_all("span[id^='oID']")
    print(f"Found {len(odds_spans)} odds spans")

    if odds_spans:
        # Click the first one
        print(f"Clicking first odds span...", flush=True)
        odds_spans[0].click()
        time.sleep(3)

        # Check for chart popup
        chart = page.query_selector('.chart, #chart, [class*="chart"], canvas')
        if chart:
            print(f"Chart element found: {chart.get_attribute('class')}")

    # Also try clicking on a fighter name row (the but-sg cells)
    but_cells = page.query_selector_all("td.but-sg")
    if but_cells and len(but_cells) > 0:
        print(f"Clicking first but-sg cell...", flush=True)
        but_cells[0].click()
        time.sleep(3)

    # Try the but-sgp cells (prop odds)
    but_sgp = page.query_selector_all("td.but-sgp")
    if but_sgp and len(but_sgp) > 0:
        print(f"Clicking first but-sgp cell...", flush=True)
        but_sgp[0].click()
        time.sleep(3)

    # Check what XHRs we captured
    print(f"\n=== Captured {len(xhr_responses)} XHR responses ===")
    for i, xhr in enumerate(xhr_responses):
        print(f"\n[{i}] {xhr['url'][:100]}")
        print(f"    status={xhr['status']} type={xhr['content_type']} len={xhr['body_len']}")
        print(f"    preview: {xhr['body_preview'][:200]}")

    # Now check the page HTML for embedded chart data
    # BFO might have the sparkline data embedded in the HTML
    html = page.content()

    # Look for sparkline data (the odds history is in the sparkline column)
    # The CSV already has fighter_sparkline which is comma-separated decimal odds
    # Check if the page has more detailed time-series data

    # Search for JSON-like structures with timestamps
    patterns = [
        r'chart.*?data.*?\[',
        r'series.*?\[',
        r'timestamps',
        r'\"x\".*?\"y\"',
        r'Date\.UTC',
        r'pointStart',
    ]
    for pat in patterns:
        matches = re.findall(pat, html, re.IGNORECASE)
        if matches:
            print(f"\nPattern '{pat}': {len(matches)} matches")
            # Find context
            for m in re.finditer(pat, html, re.IGNORECASE):
                ctx = html[m.start():m.start()+300]
                print(f"  ...{ctx[:200]}...")
                break

    # Check for Highcharts or similar charting library
    for lib in ['Highcharts', 'highcharts', 'Chart.js', 'chartjs', 'plotly', 'amcharts']:
        if lib in html:
            print(f"\nCharting library found: {lib}")

    # The sparkline in the existing data is decimal odds at 10 timepoints
    # Check the existing bfo_odds_raw.csv sparkline format
    print("\n=== Sparkline format check ===")
    with open(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_raw.csv', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        import csv
        for r in reader:
            if r.get('fighter_sparkline'):
                print(f"Sparkline sample: {r['fighter_sparkline'][:100]}")
                print(f"Event: {r['event_name']}, Fighter: {r['fighter_name']}")
                break

    browser.close()
