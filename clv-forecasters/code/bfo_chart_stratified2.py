#!/usr/bin/env python3
"""Step 0.5 v2: correct table traversal, full data extraction."""
import sys, time, json, os, csv, re, unicodedata
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('data/bfo/chart_raw', exist_ok=True)

EVENT_URLS = [
    '/events/ufc-319-3800',
    '/events/ufc-322-3924',
    '/events/ufc-326-4065',
    '/events/ufc-328-4165',
    '/events/ufc-329-4252',
    '/events/ufc-330-4237',
]

# Load bfo_close_all for close agreement
def norm(s):
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

close_ref = {}
with open('bfo_close_all.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        f1 = norm(r['fighter1_name']); f2 = norm(r['fighter2_name'])
        close_ref[(f1, f2)] = {'p_fair_a': float(r['p_fair_a']), 'p_fair_b': float(r['p_fair_b'])}
        close_ref[(f2, f1)] = {'p_fair_a': float(r['p_fair_b']), 'p_fair_b': float(r['p_fair_a'])}

SKIP_BOOKS = {'Polymarket', 'Kalshi'}

def extract_all_fights(page, event_url):
    """Extract chart data for all fights on an event page."""
    full_url = f'https://www.bestfightodds.com{event_url}'
    page.goto(full_url, timeout=30_000, wait_until='domcontentloaded')
    time.sleep(3)

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

    fights = []
    fighter_a = None; fighter_a_series = None; row_a_idx = None

    for ri in range(n):
        nr_cls = name_rows[ri].get_attribute('class') or ''
        if 'pr' in nr_cls: continue  # skip prop rows

        name_el = name_rows[ri].query_selector('th span.t-b-fcc')
        if not name_el: continue
        fname = name_el.inner_text().strip()

        # Check for matchup ID (fighter A row)
        nr_attr = name_rows[ri].evaluate('el => el.outerHTML.substring(0, 200)')
        is_mu = 'id="mu-' in nr_attr

        if is_mu or fighter_a is None:
            fighter_a = fname
            fighter_a_series = {}
            row_a_idx = ri
            # Extract chart for fighter A
            odds_cells = odds_rows[ri].query_selector_all('td.but-sg')
            for cell in odds_cells:
                span = cell.query_selector("span[id^='oID']")
                if not span: continue
                txt = span.inner_text().strip()
                if not txt or txt in ('n/a', '--'): continue
                span.click()
                time.sleep(1)
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
                        if s['name'] not in fighter_a_series or len(s['data']) > len(fighter_a_series[s['name']]):
                            fighter_a_series[s['name']] = s['data']
                page.mouse.click(10, 10)
                time.sleep(0.3)
        else:
            fighter_b = fname
            fighter_b_series = {}
            # Extract chart for fighter B
            odds_cells = odds_rows[ri].query_selector_all('td.but-sg')
            for cell in odds_cells:
                span = cell.query_selector("span[id^='oID']")
                if not span: continue
                txt = span.inner_text().strip()
                if not txt or txt in ('n/a', '--'): continue
                span.click()
                time.sleep(1)
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
                        if s['name'] not in fighter_b_series or len(s['data']) > len(fighter_b_series[s['name']]):
                            fighter_b_series[s['name']] = s['data']
                page.mouse.click(10, 10)
                time.sleep(0.3)

            fights.append({
                'fighter_a': fighter_a, 'fighter_b': fighter_b,
                'series_a': fighter_a_series, 'series_b': fighter_b_series,
            })
            fighter_a = None
            fighter_a_series = None

            # Only do first 5 fights per event (15 total across 6 events is plenty)
            if len(fights) >= 3:
                break

    return fights


def main():
    print("=" * 90)
    print("STEP 0.5: STRATIFIED RECON — parallel table traversal")
    print("=" * 90)

    all_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        page = ctx.new_page()

        for event_url in EVENT_URLS:
            print(f"\n{'='*60}")
            print(f"Event: {event_url}", flush=True)
            print(f"{'='*60}")

            fights = extract_all_fights(page, event_url)

            for fight in fights:
                fa = fight['fighter_a']; fb = fight['fighter_b']
                all_books = set(fight['series_a'].keys()) | set(fight['series_b'].keys())
                sharp = [b for b in all_books if b.lower() in ('pinnacle', 'circa', 'betonline', 'bookmaker', '5dimes')]

                # Count change-points in windows
                # Use fight date from the last point's timestamp
                all_ts = []
                for s in list(fight['series_a'].values()) + list(fight['series_b'].values()):
                    if s: all_ts.extend([pt[0] for pt in s])
                if not all_ts:
                    print(f"  {fa} vs {fb}: NO DATA")
                    continue
                fight_end = max(all_ts)

                def count_in_window(series_dict, hours):
                    total = 0
                    cutoff = fight_end - hours * 3600 * 1000
                    for pts in series_dict.values():
                        total += sum(1 for x, y in pts if x >= cutoff)
                    return total

                pts_72a = count_in_window(fight['series_a'], 72)
                pts_72b = count_in_window(fight['series_b'], 72)
                pts_24a = count_in_window(fight['series_a'], 24)
                pts_24b = count_in_window(fight['series_b'], 24)
                pts_6a = count_in_window(fight['series_a'], 6)
                pts_6b = count_in_window(fight['series_b'], 6)
                union_72 = pts_72a + pts_72b
                union_24 = pts_24a + pts_24b
                union_6 = pts_6a + pts_6b

                # Close agreement
                fa_n = norm(fa); fb_n = norm(fb)
                ref = close_ref.get((fa_n, fb_n))
                diffs = []
                if ref:
                    for book, pts in fight['series_a'].items():
                        if pts:
                            last_odds = pts[-1][1]
                            if last_odds > 1:
                                chart_ip = 1 / last_odds
                                diffs.append(chart_ip - ref['p_fair_a'])
                    for book, pts in fight['series_b'].items():
                        if pts:
                            last_odds = pts[-1][1]
                            if last_odds > 1:
                                chart_ip = 1 / last_odds
                                diffs.append(chart_ip - ref['p_fair_b'])

                print(f"\n  {fa} vs {fb}")
                print(f"    Books: {sorted(all_books)}{' SHARP: '+str(sharp) if sharp else ''}")
                print(f"    Change-points: 72h={union_72} (A={pts_72a} B={pts_72b}), "
                      f"24h={union_24} (A={pts_24a} B={pts_24b}), 6h={union_6}")
                for b in sorted(all_books):
                    a_pts = len(fight['series_a'].get(b, []))
                    b_pts = len(fight['series_b'].get(b, []))
                    print(f"      {b:<15} A={a_pts:>3} B={b_pts:>3}")
                if diffs:
                    d = np.array(diffs)
                    print(f"    Close diff (chart_ip - p_fair): mean={d.mean():+.4f} SD={d.std():.4f}")

                all_results.append({
                    'fight': f'{fa} vs {fb}',
                    'books': len(all_books), 'sharp': sharp,
                    'union_72h': union_72, 'union_24h': union_24, 'union_6h': union_6,
                    'diffs': diffs,
                })

                # Cache
                safe = f"{fa[:8]}_{fb[:8]}".replace(' ', '_')
                with open(f'data/bfo/chart_raw/strat_{safe}.json', 'w') as f:
                    json.dump(fight, f, default=str)

        browser.close()

    # GATE CHECK
    print(f"\n{'='*90}")
    print("GATE CHECK")
    print(f"{'='*90}")

    u48 = [r['union_72h'] for r in all_results]  # 72h as proxy for 48h
    med = np.median(u48) if u48 else 0
    print(f"\n  Median union change-points in ~48-72h: {med:.0f}")
    print(f"  Gate: >= 6 required → {'PASS' if med >= 6 else 'FAIL'}")

    all_d = []
    for r in all_results: all_d.extend(r.get('diffs', []))
    if all_d:
        ad = np.array(all_d)
        print(f"  Close agreement SD: {ad.std():.4f}")
        print(f"  Gate: SD <= 0.02 required → {'PASS' if ad.std() <= 0.02 else 'FAIL'}")

    print(f"\n  {'Fight':<35} {'Books':>5} {'72h':>4} {'24h':>4} {'6h':>3}")
    print("  " + "-" * 55)
    for r in all_results:
        print(f"  {r['fight'][:34]:<35} {r['books']:>5} {r['union_72h']:>4} {r['union_24h']:>4} {r['union_6h']:>3}")


if __name__ == '__main__':
    main()
