#!/usr/bin/env python3
"""Step 0 v3: click multiple book cells, extract chart data for each."""
import sys, time, json, os
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

os.chdir(os.path.dirname(os.path.abspath(__file__)))

EVENT_URL = 'https://www.bestfightodds.com/events/ufc-328-4165'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ))
    page = ctx.new_page()
    page.goto(EVENT_URL, timeout=30_000, wait_until='domcontentloaded')
    time.sleep(3)

    # Get all odds cells in the first two fighter rows (Chimaev vs Strickland)
    # Each td.but-sg or td.but-sgp has a span with oID
    # The first fighter row is tr[0] (after header), second is tr[1]
    tables = page.query_selector_all("table")
    odds_table = None
    for t in tables:
        if t.query_selector("td.but-sg"):
            odds_table = t
            break

    if not odds_table:
        print("No odds table!")
        browser.close()
        sys.exit(1)

    rows = odds_table.query_selector_all("tbody tr")

    # First two non-prop rows = fighter A and fighter B of main event
    fighter_rows = []
    for row in rows:
        cls = row.get_attribute("class") or ""
        if "pr" in cls: continue
        name_el = row.query_selector("th span.t-b-fcc")
        if name_el:
            fighter_rows.append((name_el.inner_text().strip(), row))
        if len(fighter_rows) >= 2:
            break

    print(f"Fighter rows: {[f[0] for f in fighter_rows]}")

    # For fighter A, click each odds cell and extract chart data
    for fighter_name, row in fighter_rows[:1]:  # Just first fighter
        cells = row.query_selector_all("td.but-sg")
        print(f"\n{fighter_name}: {len(cells)} odds cells")

        for ci, cell in enumerate(cells[:6]):  # First 6 books
            span = cell.query_selector("span[id^='oID']")
            if not span: continue
            odds_text = span.inner_text().strip()
            if not odds_text or odds_text == 'n/a': continue

            print(f"\n  Clicking cell {ci} (odds={odds_text})...", flush=True)
            span.click()
            time.sleep(2)

            # Extract Highcharts data
            chart_data = page.evaluate('''() => {
                if (window.Highcharts) {
                    let charts = Highcharts.charts.filter(c => c);
                    if (charts.length > 0) {
                        let c = charts[charts.length - 1];
                        return c.series.map(s => ({
                            name: s.name,
                            n_points: s.data.length,
                            first: s.data.length > 0 ? [s.data[0].x, s.data[0].y] : null,
                            last: s.data.length > 0 ? [s.data[s.data.length-1].x, s.data[s.data.length-1].y] : null,
                        }));
                    }
                }
                return [];
            }''')

            for s in chart_data:
                span_hrs = 0
                if s['first'] and s['last']:
                    span_hrs = (s['last'][0] - s['first'][0]) / 3600000
                    first_dt = datetime.fromtimestamp(s['first'][0]/1000, tz=timezone.utc)
                    last_dt = datetime.fromtimestamp(s['last'][0]/1000, tz=timezone.utc)
                    pph = s['n_points'] / span_hrs if span_hrs > 0 else 0
                    print(f"    {s['name']}: {s['n_points']} pts, {span_hrs:.0f}h span, {pph:.1f} pts/hr")
                    print(f"      {first_dt.strftime('%Y-%m-%d %H:%M')} → {last_dt.strftime('%Y-%m-%d %H:%M')}")
                    print(f"      first_y={s['first'][1]:.4f} last_y={s['last'][1]:.4f}")
                else:
                    print(f"    {s['name']}: {s['n_points']} pts (no data)")

            # Close chart popup (click elsewhere)
            page.mouse.click(10, 10)
            time.sleep(1)

    browser.close()
