#!/usr/bin/env python3
"""
Step 1: Pull BFO chart XHR for all fights in the phase2 panel sample.
Both corners, all real books (exclude Kalshi/Polymarket).
Resume-safe via checkpoint file. ~1 req/s + jitter.
"""
import sys, time, json, os, re, unicodedata, random
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('data/bfo/chart_raw', exist_ok=True)

PM_ROOT = r'C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public'
CHECKPOINT = 'data/bfo/pull_checkpoint.json'
SKIP_BOOKS = {'Polymarket', 'Kalshi'}

# Load crosswalk to get fight list and event URLs
cw = pd.read_parquet(f'{PM_ROOT}/data/meta/ufc_crosswalk.parquet')
cw = cw[cw['exclusion_reason'].isna()].copy()
cw['event_date'] = pd.to_datetime(cw['event_date'])
cw = cw[cw['event_date'] >= '2025-05-01'].copy()  # full panel range

# Load card_map to get BFO event URLs
import csv
event_urls = {}
with open('bfo_events_ext_2026.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_urls[r['bfo_event_id']] = r['url']

# Also build from card_map + known URL patterns
with open('card_map.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        eid = r['bfo_event_id']
        if eid not in event_urls:
            # Try to find in raw_html filenames
            for fname in os.listdir('raw_html') if os.path.exists('raw_html') else []:
                if fname.endswith(f'-{eid}.html'):
                    slug = fname.replace('.html', '')
                    event_urls[eid] = f'/events/{slug}'
                    break

# Group fights by event_date for BFO page loading
fights_by_event = {}
for _, row in cw.iterrows():
    fid = row['fight_id']
    edate = str(row['event_date'].date())
    fighters_k = json.loads(row['fighters_kalshi']) if isinstance(row['fighters_kalshi'], str) else row['fighters_kalshi']
    if not fighters_k or len(fighters_k) < 2:
        continue
    if edate not in fights_by_event:
        fights_by_event[edate] = []
    fights_by_event[edate].append({
        'fight_id': fid,
        'fighter_a': fighters_k[0],
        'fighter_b': fighters_k[1],
    })

# Checkpoint
def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            return json.load(f)
    return {'done_fights': []}

def save_checkpoint(cp):
    with open(CHECKPOINT, 'w') as f:
        json.dump(cp, f)

# BFO event URL discovery — search for each event date
def find_bfo_url(page, event_date, fighters):
    """Search BFO for the event URL matching a date and fighters."""
    # Try search
    query = f"UFC {event_date}"
    url = f'https://www.bestfightodds.com/search?query={query.replace(" ", "+")}'
    page.goto(url, timeout=30_000, wait_until='domcontentloaded')
    time.sleep(1 + random.random())

    html = page.content()
    matches = re.findall(r'href="(/events/([^"]+))"[^>]*>([^<]{3,80})</a>', html)
    for path, slug, name in matches:
        if 'ufc' in name.lower() or 'ufc' in path.lower():
            return f'https://www.bestfightodds.com{path}'
    return None


def extract_fight_from_page(page, name_rows, odds_rows, fighter_a, fighter_b):
    """Extract chart data for a specific fight on the current page."""
    def norm(s):
        s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
        return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

    fa_n = norm(fighter_a)
    fb_n = norm(fighter_b)

    # Find the row indices for this fight
    n = min(len(name_rows), len(odds_rows))
    target_a_idx = None
    target_b_idx = None

    for ri in range(n):
        nr_cls = name_rows[ri].get_attribute('class') or ''
        if 'pr' in nr_cls:
            continue
        name_el = name_rows[ri].query_selector('th span.t-b-fcc')
        if not name_el:
            continue
        txt = norm(name_el.inner_text().strip())

        if fa_n in txt or txt in fa_n or (len(fa_n) > 4 and len(txt) > 4 and (fa_n[:5] in txt or txt[:5] in fa_n)):
            target_a_idx = ri
        elif fb_n in txt or txt in fb_n or (len(fb_n) > 4 and len(txt) > 4 and (fb_n[:5] in txt or txt[:5] in fb_n)):
            target_b_idx = ri

        if target_a_idx is not None and target_b_idx is not None:
            break

    if target_a_idx is None and target_b_idx is None:
        return None

    result = {'fighter_a': fighter_a, 'fighter_b': fighter_b, 'series_a': {}, 'series_b': {}}

    for label, idx in [('a', target_a_idx), ('b', target_b_idx)]:
        if idx is None or idx >= len(odds_rows):
            continue
        cells = odds_rows[idx].query_selector_all('td.but-sg')
        for cell in cells:
            span = cell.query_selector("span[id^='oID']")
            if not span:
                continue
            txt = span.inner_text().strip()
            if not txt or txt in ('n/a', '--'):
                continue

            try:
                span.click()
                time.sleep(0.8 + random.random() * 0.4)

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
                        key = f"series_{label}"
                        if s['name'] not in result[key] or len(s['data']) > len(result[key][s['name']]):
                            result[key][s['name']] = s['data']

                page.mouse.click(10, 10)
                time.sleep(0.3)
            except Exception as e:
                continue

    return result


def main():
    cp = load_checkpoint()
    done_set = set(cp['done_fights'])

    # Load URL table
    with open('data/bfo/event_urls.json') as f:
        url_table = json.load(f)

    total_fights = sum(len(fl) for fl in fights_by_event.values())
    already_done = sum(1 for fl in fights_by_event.values() for f in fl if f['fight_id'] in done_set)
    print(f"Total fights: {total_fights}, already done: {already_done}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        page = ctx.new_page()

        events_done = 0
        for edate in sorted(fights_by_event.keys()):
            fight_list = fights_by_event[edate]

            # Skip if all fights on this date are done
            remaining = [f for f in fight_list if f['fight_id'] not in done_set]
            if not remaining:
                continue

            # Find the BFO event page from URL table (try date and date+-1)
            print(f"\n[{edate}] {len(remaining)} fights to pull", flush=True)
            event_url = None
            for d_offset in [edate]:
                if d_offset in url_table:
                    path = url_table[d_offset]
                    event_url = f'https://www.bestfightodds.com{path}' if path.startswith('/') else path
                    break
            # Try +-1 day
            if not event_url:
                from datetime import datetime as dt, timedelta
                for delta in [1, -1]:
                    d = (dt.strptime(edate, '%Y-%m-%d') + timedelta(days=delta)).strftime('%Y-%m-%d')
                    if d in url_table:
                        path = url_table[d]
                        event_url = f'https://www.bestfightodds.com{path}' if path.startswith('/') else path
                        break
            if not event_url:
                print(f"  Could not find BFO page for {edate}", flush=True)
                continue

            print(f"  URL: {event_url}", flush=True)
            page.goto(event_url, timeout=30_000, wait_until='domcontentloaded')
            time.sleep(2)

            # Get table rows
            tables = page.query_selector_all('table')
            name_table = odds_table = None
            for t in tables:
                if t.query_selector('th span.t-b-fcc') and not name_table:
                    name_table = t
                if t.query_selector('td.but-sg') and not odds_table:
                    odds_table = t

            if not name_table or not odds_table:
                print(f"  No odds table found", flush=True)
                continue

            name_rows = name_table.query_selector_all('tbody tr')
            odds_rows = odds_table.query_selector_all('tbody tr')

            for fight in remaining:
                fid = fight['fight_id']
                fa = fight['fighter_a']
                fb = fight['fighter_b']

                cache_path = f'data/bfo/chart_raw/{fid}.json'
                if os.path.exists(cache_path):
                    done_set.add(fid)
                    cp['done_fights'] = list(done_set)
                    save_checkpoint(cp)
                    continue

                print(f"  {fid}: {fa} vs {fb}", flush=True, end='')
                result = extract_fight_from_page(page, name_rows, odds_rows, fa, fb)

                if result:
                    n_books_a = len(result['series_a'])
                    n_books_b = len(result['series_b'])
                    n_pts = sum(len(v) for v in result['series_a'].values()) + \
                            sum(len(v) for v in result['series_b'].values())
                    print(f" -> {n_books_a}+{n_books_b} books, {n_pts} pts", flush=True)

                    result['fetched_at'] = datetime.now(timezone.utc).isoformat()
                    result['source'] = 'bfo_chart_xhr'
                    with open(cache_path, 'w') as f:
                        json.dump(result, f)
                else:
                    print(f" -> NOT FOUND on page", flush=True)
                    # Save empty so we don't retry
                    with open(cache_path, 'w') as f:
                        json.dump({'fighter_a': fa, 'fighter_b': fb,
                                   'series_a': {}, 'series_b': {},
                                   'fetched_at': datetime.now(timezone.utc).isoformat(),
                                   'source': 'bfo_chart_xhr', 'note': 'not_found'}, f)

                done_set.add(fid)
                cp['done_fights'] = list(done_set)
                save_checkpoint(cp)

            events_done += 1

        browser.close()

    print(f"\nDone. {len(done_set)} fights cached in data/bfo/chart_raw/")


if __name__ == '__main__':
    main()
