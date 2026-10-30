#!/usr/bin/env python3
"""Step 0 v2: capture the chart XHR data after clicking an odds cell."""
import sys, time, json, re, os, csv
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('data/bfo/chart_raw', exist_ok=True)

EVENT_URL = 'https://www.bestfightodds.com/events/ufc-328-4165'

xhr_log = []

def handle_response(response):
    url = response.url
    ct = response.headers.get('content-type', '')
    try:
        if response.status == 200 and ('json' in ct or 'chart' in url.lower() or
            'graph' in url.lower() or '/api/' in url.lower() or
            response.url != EVENT_URL):
            body = response.text()
            if len(body) > 50:  # skip tiny responses
                xhr_log.append({
                    'url': url, 'status': response.status,
                    'content_type': ct, 'body': body,
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

    page.goto(EVENT_URL, timeout=30_000, wait_until='domcontentloaded')
    time.sleep(3)

    # Clear XHR log from page load
    pre_click = len(xhr_log)
    print(f"XHRs from page load: {pre_click}", flush=True)

    # Click on an odds cell to trigger the chart popup
    # Use the first span with oID
    span = page.query_selector("span[id^='oID']")
    if span:
        span_id = span.get_attribute('id')
        span_text = span.inner_text().strip()
        print(f"Clicking span id={span_id} text={span_text}", flush=True)
        span.click()
        time.sleep(3)

    post_click = len(xhr_log)
    new_xhrs = xhr_log[pre_click:]
    print(f"New XHRs after click: {len(new_xhrs)}", flush=True)

    for i, xhr in enumerate(new_xhrs):
        print(f"\n[{i}] URL: {xhr['url'][:120]}")
        print(f"    Type: {xhr['content_type']}")
        print(f"    Body length: {len(xhr['body'])}")
        print(f"    Body preview: {xhr['body'][:500]}")

    # If no XHRs, the chart data might be embedded in the page JS
    # Check for inline chart data near the chart-container
    if not new_xhrs:
        print("\nNo new XHRs. Checking embedded chart data...", flush=True)
        # The chart might use data from a JS variable or inline script
        scripts = page.query_selector_all('script')
        for s in scripts:
            content = s.inner_text()
            if 'chart' in content.lower() and ('data' in content.lower() or 'series' in content.lower()):
                print(f"\nScript with chart data ({len(content)} chars):")
                print(content[:1000])
                break

    # Also check the chart container HTML
    chart = page.query_selector('.chart-container')
    if chart:
        html = chart.inner_html()
        print(f"\nChart container HTML ({len(html)} chars):")
        print(html[:1000])

    # Check for Highcharts data
    # Highcharts stores data in window.Highcharts or chart.series[0].data
    try:
        chart_data = page.evaluate('''() => {
            if (window.Highcharts) {
                let charts = Highcharts.charts.filter(c => c);
                if (charts.length > 0) {
                    let c = charts[charts.length - 1];
                    return {
                        type: 'highcharts',
                        n_series: c.series.length,
                        series: c.series.map(s => ({
                            name: s.name,
                            n_points: s.data.length,
                            sample: s.data.slice(0, 5).map(p => ({x: p.x, y: p.y})),
                            last: s.data.slice(-3).map(p => ({x: p.x, y: p.y})),
                        })),
                        title: c.title ? c.title.textStr : '',
                    };
                }
            }
            return {type: 'not_found'};
        }''')
        print(f"\n=== HIGHCHARTS DATA ===")
        print(json.dumps(chart_data, indent=2, default=str))

        if chart_data.get('type') == 'highcharts':
            # Save full series data
            full_data = page.evaluate('''() => {
                let charts = Highcharts.charts.filter(c => c);
                if (charts.length > 0) {
                    let c = charts[charts.length - 1];
                    return c.series.map(s => ({
                        name: s.name,
                        data: s.data.map(p => [p.x, p.y]),
                    }));
                }
                return [];
            }''')
            with open('data/bfo/chart_raw/recon_ufc328_sample.json', 'w') as f:
                json.dump(full_data, f, indent=2)
            print(f"\nSaved full chart data: {len(full_data)} series")
            for s in full_data:
                print(f"  {s['name']}: {len(s['data'])} points")
                if s['data']:
                    print(f"    First: x={s['data'][0][0]}, y={s['data'][0][1]}")
                    print(f"    Last:  x={s['data'][-1][0]}, y={s['data'][-1][1]}")
    except Exception as e:
        print(f"\nHighcharts extraction error: {e}")

    browser.close()
