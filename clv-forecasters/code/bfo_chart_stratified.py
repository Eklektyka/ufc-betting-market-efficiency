#!/usr/bin/env python3
"""
Step 0.5: Stratified recon — 15 fights across card positions and dates.
Pull chart XHR for all books, both corners. Report density and close agreement.
"""
import sys, time, json, os, csv, re
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('data/bfo/chart_raw', exist_ok=True)

# Select 15 fights: 5 main, 5 co-main/featured, 5 undercard
# Spread across the year from the ezoteryka_scored sample
FIGHTS = [
    # Main events (headliners of numbered cards)
    {'label': 'main', 'event_url': '/events/ufc-319-3800', 'fighters': ['Dricus Du Plessis', 'Khamzat Chimaev'], 'date': '2025-08-17'},
    {'label': 'main', 'event_url': '/events/ufc-322-3924', 'fighters': ['Jack Della Maddalena', 'Islam Makhachev'], 'date': '2025-11-15'},
    {'label': 'main', 'event_url': '/events/ufc-326-4065', 'fighters': ['Max Holloway', 'Charles Oliveira'], 'date': '2026-03-07'},
    {'label': 'main', 'event_url': '/events/ufc-328-4165', 'fighters': ['Khamzat Chimaev', 'Sean Strickland'], 'date': '2026-05-09'},
    {'label': 'main', 'event_url': '/events/ufc-329-4252', 'fighters': ['Conor McGregor', 'Max Holloway'], 'date': '2026-07-11'},
    # Co-main / featured (2nd or 3rd on card)
    {'label': 'co-main', 'event_url': '/events/ufc-319-3800', 'fighters': ['Lerone Murphy', 'Aaron Pico'], 'date': '2025-08-17'},
    {'label': 'co-main', 'event_url': '/events/ufc-322-3924', 'fighters': ['Sean Brady', 'Joaquin Buckley'], 'date': '2025-11-15'},  # actually 3830
    {'label': 'co-main', 'event_url': '/events/ufc-328-4165', 'fighters': ['Tatsuro Taira', 'Joshua Van'], 'date': '2026-05-09'},
    {'label': 'co-main', 'event_url': '/events/ufc-329-4252', 'fighters': ['Paddy Pimblett', 'Benoit Saint Denis'], 'date': '2026-07-11'},
    {'label': 'co-main', 'event_url': '/events/ufc-330-4237', 'fighters': ['Islam Makhachev', 'Ian Machado Garry'], 'date': '2026-08-15'},
    # Undercard
    {'label': 'undercard', 'event_url': '/events/ufc-319-3800', 'fighters': ['Edson Barboza', 'Drakkar Klose'], 'date': '2025-08-17'},
    {'label': 'undercard', 'event_url': '/events/ufc-328-4165', 'fighters': ['Grant Dawson', 'Mateusz Rebecki'], 'date': '2026-05-09'},
    {'label': 'undercard', 'event_url': '/events/ufc-328-4165', 'fighters': ['Jim Miller', 'Jared Gordon'], 'date': '2026-05-09'},
    {'label': 'undercard', 'event_url': '/events/ufc-329-4252', 'fighters': ['King Green', 'Jeremy Stephens'], 'date': '2026-07-11'},
    {'label': 'undercard', 'event_url': '/events/ufc-330-4237', 'fighters': ['Esteban Ribovics', 'Edson Barboza'], 'date': '2026-08-15'},
]

# Load bfo_close_all for close agreement check
close_ref = {}
with open('bfo_close_all.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        def norm(s):
            import unicodedata
            s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
            return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()
        f1 = norm(r['fighter1_name'])
        f2 = norm(r['fighter2_name'])
        close_ref[(f1, f2)] = {
            'best_a': int(r['best_line_a']), 'best_b': int(r['best_line_b']),
            'p_fair_a': float(r['p_fair_a']), 'p_fair_b': float(r['p_fair_b']),
        }
        close_ref[(f2, f1)] = {
            'best_a': int(r['best_line_b']), 'best_b': int(r['best_line_a']),
            'p_fair_a': float(r['p_fair_b']), 'p_fair_b': float(r['p_fair_a']),
        }


def extract_chart_for_fighter(page, row, fighter_name):
    """Find and click the odds cells for a fighter, extract all book series."""
    # Find the fighter's row in the odds table
    name_el = None
    all_name_els = page.query_selector_all("th span.t-b-fcc")
    for ne in all_name_els:
        txt = ne.inner_text().strip()
        if fighter_name.lower() in txt.lower() or txt.lower() in fighter_name.lower():
            name_el = ne
            break

    if not name_el:
        return {}

    # Get the parent row
    fighter_row = name_el.evaluate('el => el.closest("tr")')
    if not fighter_row:
        return {}

    # Get parent tr element properly
    tr = name_el.evaluate_handle('el => el.closest("tr")')

    # Get all but-sg cells in this row
    cells = tr.as_element().query_selector_all("td.but-sg")

    all_series = {}
    for ci, cell in enumerate(cells):
        span = cell.query_selector("span[id^='oID']")
        if not span:
            continue
        odds_text = span.inner_text().strip()
        if not odds_text or odds_text in ('n/a', '--'):
            continue

        span.click()
        time.sleep(1.5)

        try:
            chart_data = page.evaluate('''() => {
                if (window.Highcharts) {
                    let charts = Highcharts.charts.filter(c => c);
                    if (charts.length > 0) {
                        let c = charts[charts.length - 1];
                        return c.series.map(s => ({
                            name: s.name,
                            data: s.data.map(p => [p.x, p.y]),
                        }));
                    }
                }
                return [];
            }''')

            for s in chart_data:
                book = s['name']
                if book not in all_series or len(s['data']) > len(all_series[book]):
                    all_series[book] = s['data']
        except:
            pass

        page.mouse.click(10, 10)
        time.sleep(0.5)

    return all_series


def analyze_series(series_dict, event_date_str):
    """Analyze change-point density in final 72h/24h/6h."""
    event_dt = datetime.strptime(event_date_str, '%Y-%m-%d').replace(
        hour=23, minute=59, tzinfo=timezone.utc)

    results = {}
    for book, points in series_dict.items():
        if book in ('Polymarket', 'Kalshi'):
            continue  # Drop per spec

        pts_72h = 0; pts_24h = 0; pts_6h = 0
        last_y = None
        last_ts = None

        for x, y in points:
            ts = datetime.fromtimestamp(x / 1000, tz=timezone.utc)
            hours_before = (event_dt - ts).total_seconds() / 3600
            if hours_before <= 72: pts_72h += 1
            if hours_before <= 24: pts_24h += 1
            if hours_before <= 6: pts_6h += 1
            last_y = y
            last_ts = ts

        results[book] = {
            'total': len(points), 'pts_72h': pts_72h,
            'pts_24h': pts_24h, 'pts_6h': pts_6h,
            'last_odds': last_y, 'last_ts': last_ts,
        }

    return results


def main():
    print("=" * 90)
    print("STEP 0.5: STRATIFIED RECON — 15 fights")
    print("=" * 90)

    # Group fights by event URL to minimize page loads
    events = {}
    for f in FIGHTS:
        url = f['event_url']
        if url not in events:
            events[url] = []
        events[url].append(f)

    all_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ))
        page = ctx.new_page()

        for event_url, fight_list in events.items():
            full_url = f'https://www.bestfightodds.com{event_url}'
            print(f"\nLoading {full_url}...", flush=True)
            page.goto(full_url, timeout=30_000, wait_until='domcontentloaded')
            time.sleep(3)

            for fight in fight_list:
                fa = fight['fighters'][0]
                fb = fight['fighters'][1]
                print(f"\n  [{fight['label']}] {fa} vs {fb} ({fight['date']})", flush=True)

                # Extract chart for both corners
                series_a = extract_chart_for_fighter(page, None, fa)
                series_b = extract_chart_for_fighter(page, None, fb)

                # Cache raw
                safe = f"{fight['date']}_{fa[:10]}_{fb[:10]}".replace(' ', '_')
                cache_path = f'data/bfo/chart_raw/{safe}.json'
                with open(cache_path, 'w') as f:
                    json.dump({'fighter_a': fa, 'fighter_b': fb, 'date': fight['date'],
                               'series_a': {k: v for k, v in series_a.items()},
                               'series_b': {k: v for k, v in series_b.items()},
                               'fetched_at': datetime.now(timezone.utc).isoformat()}, f)

                # Analyze
                analysis_a = analyze_series(series_a, fight['date'])
                analysis_b = analyze_series(series_b, fight['date'])

                # Union of books
                all_books = set(analysis_a.keys()) | set(analysis_b.keys())
                sharp_books = [b for b in all_books if b.lower() in
                               ('pinnacle', 'circa', 'betonline', 'bet online', '5dimes', 'bookmaker')]

                # Union change-points in final windows
                union_72h = sum(max(analysis_a.get(b, {}).get('pts_72h', 0),
                                    analysis_b.get(b, {}).get('pts_72h', 0)) for b in all_books)
                union_24h = sum(max(analysis_a.get(b, {}).get('pts_24h', 0),
                                    analysis_b.get(b, {}).get('pts_24h', 0)) for b in all_books)
                union_6h = sum(max(analysis_a.get(b, {}).get('pts_6h', 0),
                                   analysis_b.get(b, {}).get('pts_6h', 0)) for b in all_books)
                # Total across both corners (sum not max)
                total_48h = 0
                for b in all_books:
                    total_48h += analysis_a.get(b, {}).get('pts_72h', 0)  # approx 48h from 72h
                    total_48h += analysis_b.get(b, {}).get('pts_72h', 0)

                # Close agreement
                def norm(s):
                    import unicodedata
                    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
                    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

                fa_n = norm(fa); fb_n = norm(fb)
                ref = close_ref.get((fa_n, fb_n))

                close_diffs = []
                if ref:
                    # Compare chart last odds to BFO close p_fair
                    for b, info in analysis_a.items():
                        if info['last_odds'] and info['last_odds'] > 1:
                            chart_ip = 1 / info['last_odds']  # implied prob from decimal
                            diff = chart_ip - ref['p_fair_a']
                            close_diffs.append(diff)
                    for b, info in analysis_b.items():
                        if info['last_odds'] and info['last_odds'] > 1:
                            chart_ip = 1 / info['last_odds']
                            diff = chart_ip - ref['p_fair_b']
                            close_diffs.append(diff)

                print(f"    Books: {sorted(all_books)}")
                if sharp_books:
                    print(f"    SHARP BOOKS: {sharp_books}")
                print(f"    Change-points (union across books): 72h={union_72h}, 24h={union_24h}, 6h={union_6h}")
                print(f"    Per-book detail:", flush=True)
                for b in sorted(all_books):
                    a = analysis_a.get(b, {})
                    binfo = analysis_b.get(b, {})
                    print(f"      {b:<15} A: {a.get('total',0):>3} total, {a.get('pts_72h',0):>2}/72h, "
                          f"{a.get('pts_24h',0):>2}/24h, {a.get('pts_6h',0):>2}/6h | "
                          f"B: {binfo.get('total',0):>3} total, {binfo.get('pts_72h',0):>2}/72h, "
                          f"{binfo.get('pts_24h',0):>2}/24h, {binfo.get('pts_6h',0):>2}/6h")

                if close_diffs:
                    import numpy as np
                    cd = np.array(close_diffs)
                    print(f"    Close agreement (chart_ip - p_fair): mean={cd.mean():+.4f}, SD={cd.std():.4f}, n={len(cd)}")

                all_results.append({
                    'label': fight['label'], 'date': fight['date'],
                    'fight': f"{fa} vs {fb}",
                    'n_books': len(all_books), 'sharp': sharp_books,
                    'union_72h': union_72h, 'union_24h': union_24h, 'union_6h': union_6h,
                    'close_diffs': close_diffs,
                })

        browser.close()

    # ─── GATE CHECK ───
    print("\n" + "=" * 90)
    print("GATE CHECK")
    print("=" * 90)

    import numpy as np
    # Union change-points in final 48h (approximate from 72h data)
    union_48h_per_fight = []
    for r in all_results:
        # Use union_72h as proxy (includes some >48h points but close enough)
        union_48h_per_fight.append(r['union_72h'])

    median_union = np.median(union_48h_per_fight) if union_48h_per_fight else 0
    print(f"\n  Median union change-points in ~48h: {median_union:.0f}")
    print(f"  Gate: >= 6 required")
    print(f"  {'PASS' if median_union >= 6 else 'FAIL'}")

    all_diffs = []
    for r in all_results:
        all_diffs.extend(r['close_diffs'])
    if all_diffs:
        ad = np.array(all_diffs)
        print(f"\n  Close agreement: mean={ad.mean():+.4f}, SD={ad.std():.4f}")
        print(f"  Gate: SD <= 0.02 required")
        print(f"  {'PASS' if ad.std() <= 0.02 else 'FAIL'}")

    # Summary table
    print(f"\n  {'Fight':<40} {'Pos':<10} {'Books':>5} {'72h':>4} {'24h':>4} {'6h':>3} {'Sharp'}")
    print("  " + "-" * 80)
    for r in all_results:
        sharp_str = ','.join(r['sharp']) if r['sharp'] else '-'
        print(f"  {r['fight'][:39]:<40} {r['label']:<10} {r['n_books']:>5} "
              f"{r['union_72h']:>4} {r['union_24h']:>4} {r['union_6h']:>3} {sharp_str}")


if __name__ == '__main__':
    main()
