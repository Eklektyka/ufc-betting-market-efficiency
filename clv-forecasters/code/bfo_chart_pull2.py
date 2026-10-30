#!/usr/bin/env python3
"""
Step 1 v2: Pull ALL chart data from each BFO event page.
Don't match fighters during scraping — collect everything, match after.
One click per odds cell, parallel table traversal.
"""
import sys, time, json, os, re, random
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('data/bfo/chart_raw', exist_ok=True)

CHECKPOINT = 'data/bfo/pull2_checkpoint.json'
SKIP_BOOKS = {'Polymarket', 'Kalshi'}

# Load URL table
with open('data/bfo/event_urls.json') as f:
    url_table = json.load(f)

# Only process dates in our panel range (2025-05-10 to 2026-08-15)
target_dates = sorted(d for d in url_table if '2025-05' <= d <= '2026-08-15')

def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f: return json.load(f)
    return {'done_dates': []}

def save_checkpoint(cp):
    with open(CHECKPOINT, 'w') as f: json.dump(cp, f)


def scrape_event_page(page, event_url, event_date):
    """Scrape ALL fighters' chart data from one BFO event page."""
    full_url = f'https://www.bestfightodds.com{event_url}' if event_url.startswith('/') else event_url
    page.goto(full_url, timeout=30_000, wait_until='domcontentloaded')
    time.sleep(2)

    tables = page.query_selector_all('table')
    name_table = odds_table = None
    for t in tables:
        if t.query_selector('th span.t-b-fcc') and not name_table: name_table = t
        if t.query_selector('td.but-sg') and not odds_table: odds_table = t
    if not name_table or not odds_table:
        return []

    name_rows = name_table.query_selector_all('tbody tr')
    odds_rows = odds_table.query_selector_all('tbody tr')
    n = min(len(name_rows), len(odds_rows))

    fighters = []  # list of {name, row_idx, is_fighter_a, series}

    for ri in range(n):
        nr_cls = name_rows[ri].get_attribute('class') or ''
        if 'pr' in nr_cls: continue

        name_el = name_rows[ri].query_selector('th span.t-b-fcc')
        if not name_el: continue
        fname = name_el.inner_text().strip()

        # Extract chart from odds cells
        series = {}
        cells = odds_rows[ri].query_selector_all('td.but-sg')
        for cell in cells:
            span = cell.query_selector("span[id^='oID']")
            if not span: continue
            txt = span.inner_text().strip()
            if not txt or txt in ('n/a', '--'): continue

            try:
                span.click()
                time.sleep(0.6 + random.random() * 0.3)

                data = page.evaluate('''() => {
                    if (window.Highcharts) {
                        let charts = Highcharts.charts.filter(c => c);
                        if (charts.length > 0) {
                            let c = charts[charts.length - 1];
                            return c.series.map(s => ({name: s.name, data: s.data.map(p => [p.x, p.y])}));
                        }
                    }
                    return [];
                }''')

                for s in data:
                    if s['name'] not in SKIP_BOOKS:
                        if s['name'] not in series or len(s['data']) > len(series[s['name']]):
                            series[s['name']] = s['data']

                page.mouse.click(10, 10)
                time.sleep(0.2)
            except:
                continue

        if series:
            n_pts = sum(len(v) for v in series.values())
            fighters.append({'name': fname, 'row_idx': ri, 'series': series})

    return fighters


def main():
    cp = load_checkpoint()
    done_dates = set(cp['done_dates'])

    remaining = [d for d in target_dates if d not in done_dates]
    print(f"Dates to process: {len(remaining)} (of {len(target_dates)})", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        page = ctx.new_page()

        for edate in remaining:
            event_url = url_table[edate]
            print(f"\n[{edate}] {event_url}", flush=True)

            fighters = scrape_event_page(page, event_url, edate)

            # Save per-date
            cache_path = f'data/bfo/chart_raw/event_{edate}.json'
            with open(cache_path, 'w') as f:
                json.dump({
                    'event_date': edate, 'event_url': event_url,
                    'fighters': [{'name': fi['name'], 'row_idx': fi['row_idx'],
                                  'series': fi['series']} for fi in fighters],
                    'fetched_at': datetime.now(timezone.utc).isoformat(),
                    'source': 'bfo_chart_xhr',
                }, f)

            n_fighters = len(fighters)
            n_pts = sum(sum(len(v) for v in fi['series'].values()) for fi in fighters)
            print(f"  -> {n_fighters} fighters, {n_pts} total points", flush=True)

            done_dates.add(edate)
            cp['done_dates'] = list(done_dates)
            save_checkpoint(cp)

        browser.close()

    print(f"\nDone. {len(done_dates)} dates cached.")


if __name__ == '__main__':
    main()
