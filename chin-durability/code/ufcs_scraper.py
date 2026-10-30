"""
ufcs_scraper.py  (v4 — Playwright, domcontentloaded, full browser restart)
====================================
UFCStats requires JS rendering (bot check). Uses Playwright with a visible
browser so it passes. Resumable — skips already-scraped pages.

Outputs to ufcstats_raw/:
  events.csv, fight_links.csv, fight_totals.csv,
  round_stats.csv, fighter_features.csv, ufc_extended.csv

Run: py ufcs_scraper.py
"""
import time, logging, sys
from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = 'http://www.ufcstats.com'
OUT_DIR  = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\ufcstats_raw')
OUT_DIR.mkdir(exist_ok=True)

DELAY       = 1.2   # seconds between page loads
FLUSH_EVERY = 100   # flush to disk every N fights

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(OUT_DIR / 'scrape.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)

# ── Session state (mutable, so crash-recovery can replace browser/page) ──────
class Session:
    def __init__(self, pw):
        self.pw = pw
        self.browser = None
        self.page    = None
        self._launch()

    def _launch(self):
        if self.browser:
            try: self.browser.close()
            except Exception: pass
        self.browser = self.pw.chromium.launch(headless=True)
        self.page    = self.browser.new_page()
        log.info('Browser launched. Warming up (passing JS check)...')
        self.page.goto(BASE_URL, wait_until='domcontentloaded', timeout=30000)
        time.sleep(3)
        log.info('Warm-up done.')

    def get_html(self, url, retries=5):
        for attempt in range(retries):
            try:
                self.page.goto(url, wait_until='domcontentloaded', timeout=25000)
                time.sleep(DELAY)
                html = self.page.content()
                return html
            except PWTimeout:
                log.warning(f'Timeout attempt {attempt+1}: {url}')
                time.sleep(min(2 ** attempt, 16))
            except Exception as e:
                msg = str(e)
                log.warning(f'Error attempt {attempt+1}: {url} — {msg[:120]}')
                # Try page restart first
                try:
                    self.page.close()
                    self.page = self.browser.new_page()
                    self.page.goto(BASE_URL, wait_until='domcontentloaded', timeout=20000)
                    time.sleep(2)
                    log.info('Page restarted.')
                except Exception:
                    # Full browser restart
                    log.warning('Page restart failed — relaunching browser...')
                    try:
                        self._launch()
                    except Exception as e2:
                        log.error(f'Browser relaunch failed: {e2}')
                time.sleep(min(2 ** attempt, 16))
        log.error(f'Giving up after {retries} attempts: {url}')
        return None

# ── Helpers ───────────────────────────────────────────────────────────────────
def save(df, path):
    if path.exists():
        existing = pd.read_csv(path)
        df = pd.concat([existing, df]).drop_duplicates()
    df.to_csv(path, index=False)
    return df

# ── Step 1: Events ────────────────────────────────────────────────────────────
def scrape_events(s):
    log.info('Scraping events...')
    html = s.get_html(f'{BASE_URL}/statistics/events/completed?page=all')
    if not html:
        return pd.DataFrame()

    soup = BeautifulSoup(html, 'html.parser')
    events = []
    for row in soup.select('tr.b-statistics__table-row'):
        cols = row.find_all('td')
        if len(cols) < 2:
            continue
        a = cols[0].find('a')
        if not a:
            continue
        span = cols[0].find('span', class_='b-statistics__date')
        events.append({
            'event_name': a.get_text(strip=True),
            'event_url':  a['href'],
            'date':       span.get_text(strip=True) if span else '',
            'location':   cols[1].get_text(strip=True),
        })

    df = pd.DataFrame(events)
    df.to_csv(OUT_DIR / 'events.csv', index=False)
    log.info(f'Events: {len(df)}')
    return df

# ── Step 2: Fight links ───────────────────────────────────────────────────────
def scrape_fight_links(s, events_df):
    log.info('Scraping fight links...')
    path = OUT_DIR / 'fight_links.csv'
    done = set(pd.read_csv(path)['event_url'].unique()) if path.exists() else set()

    new_links = []
    todo = events_df[~events_df['event_url'].isin(done)]
    log.info(f'Events to scrape: {len(todo)} (done: {len(done)})')

    for i, (_, ev) in enumerate(todo.iterrows()):
        if i % 50 == 0:
            log.info(f'  Event {i}/{len(todo)}')
            if new_links:
                save(pd.DataFrame(new_links), path)
                new_links = []

        html = s.get_html(ev['event_url'])
        if not html:
            continue
        soup = BeautifulSoup(html, 'html.parser')
        seen = {l['fight_url'] for l in new_links}
        for a in soup.select('a[href*="fight-details"]'):
            href = a['href']
            if href not in seen:
                new_links.append({
                    'event_url':  ev['event_url'],
                    'event_name': ev['event_name'],
                    'date':       ev['date'],
                    'fight_url':  href,
                })
                seen.add(href)

    if new_links:
        save(pd.DataFrame(new_links), path)

    df = pd.read_csv(path) if path.exists() else pd.DataFrame()
    df = df.drop_duplicates(subset=['fight_url'])
    df.to_csv(path, index=False)
    log.info(f'Fight links: {len(df)}')
    return df

# ── Step 3: Fight totals + round stats ────────────────────────────────────────
def parse_fight(html, fight_url, event_name, date):
    soup = BeautifulSoup(html, 'html.parser')
    totals, rounds = [], []

    name_els = soup.select('h3.b-fight-details__person-name a')
    fighters  = [el.get_text(strip=True) for el in name_els[:2]]
    f_urls    = [el['href'] for el in name_els[:2]]
    while len(fighters) < 2: fighters.append('')
    while len(f_urls)   < 2: f_urls.append('')

    res_els = soup.select('i.b-fight-details__person-status')
    results = [el.get_text(strip=True) for el in res_els[:2]]
    while len(results) < 2: results.append('')

    def meta(label):
        for i in soup.select('i.b-fight-details__label'):
            if label.lower() in i.get_text(strip=True).lower():
                p = i.find_parent()
                if p:
                    return p.get_text(strip=True).replace(i.get_text(strip=True), '').strip()
        return ''

    method   = meta('Method')
    round_n  = meta('Round')
    time_str = meta('Time')
    division = meta('Weight class')

    tables = soup.select('table.b-fight-details__table')

    if tables:
        for i, row in enumerate(tables[0].select('tbody tr')[:2]):
            cols = [td.get_text(strip=True) for td in row.find_all('td')]
            if len(cols) < 10: continue
            totals.append({
                'fight_url': fight_url, 'event_name': event_name, 'date': date,
                'fighter': fighters[i], 'fighter_url': f_urls[i], 'result': results[i],
                'method': method, 'round': round_n, 'time': time_str, 'division': division,
                'kd': cols[1], 'sig_str': cols[2], 'sig_str_pct': cols[3],
                'total_str': cols[4], 'td': cols[5], 'td_pct': cols[6],
                'sub_att': cols[7], 'rev': cols[8], 'ctrl': cols[9],
            })

    if len(tables) > 2:
        rnd, fidx = 1, 0
        for row in tables[2].select('tbody tr'):
            cols = [td.get_text(strip=True) for td in row.find_all('td')]
            if not cols: continue
            if len(cols) == 1 and cols[0].lower().startswith('round'):
                try: rnd = int(cols[0].split()[-1])
                except: pass
                fidx = 0
                continue
            if len(cols) < 10: continue
            rounds.append({
                'fight_url': fight_url, 'date': date,
                'fighter': fighters[fidx % 2], 'fighter_url': f_urls[fidx % 2],
                'round': rnd,
                'kd': cols[1], 'sig_str': cols[2], 'sig_str_pct': cols[3],
                'total_str': cols[4], 'td': cols[5], 'td_pct': cols[6],
                'sub_att': cols[7], 'rev': cols[8], 'ctrl': cols[9],
            })
            fidx += 1

    return totals, rounds


def scrape_fights(s, fight_links_df):
    log.info('Scraping fight pages...')
    t_path = OUT_DIR / 'fight_totals.csv'
    r_path = OUT_DIR / 'round_stats.csv'

    done = set(pd.read_csv(t_path)['fight_url'].unique()) if t_path.exists() else set()
    todo = fight_links_df[~fight_links_df['fight_url'].isin(done)]
    log.info(f'Fights to scrape: {len(todo)} (done: {len(done)})')

    all_t, all_r = [], []
    for i, (_, row) in enumerate(todo.iterrows()):
        if i % FLUSH_EVERY == 0 and i > 0:
            log.info(f'  Fight {i}/{len(todo)} — flushing...')
            if all_t: save(pd.DataFrame(all_t), t_path); all_t = []
            if all_r: save(pd.DataFrame(all_r), r_path); all_r = []

        furl = row['fight_url']
        if pd.isna(furl) or not str(furl).startswith('http'):
            continue
        html = s.get_html(str(furl))
        if not html: continue
        t, r = parse_fight(html, row['fight_url'], row['event_name'], row['date'])
        all_t.extend(t); all_r.extend(r)

    if all_t: save(pd.DataFrame(all_t), t_path)
    if all_r: save(pd.DataFrame(all_r), r_path)
    log.info('Fight scraping done.')

# ── Step 4: Fighter features ──────────────────────────────────────────────────
def scrape_fighters(s, totals_df):
    log.info('Scraping fighter pages...')
    path = OUT_DIR / 'fighter_features.csv'
    done = set(pd.read_csv(path)['fighter_url'].unique()) if path.exists() else set()

    all_urls = totals_df['fighter_url'].dropna().unique()
    todo     = [u for u in all_urls if u and u not in done]
    log.info(f'Fighters to scrape: {len(todo)} (done: {len(done)})')

    feats = []
    for i, url in enumerate(todo):
        if i % FLUSH_EVERY == 0 and i > 0:
            log.info(f'  Fighter {i}/{len(todo)} — flushing...')
            if feats: save(pd.DataFrame(feats), path); feats = []

        html = s.get_html(url)
        if not html: continue
        soup = BeautifulSoup(html, 'html.parser')

        name_el = soup.find('span', class_='b-content__title-highlight')
        name    = name_el.get_text(strip=True) if name_el else ''

        def stat(label):
            for li in soup.select('li.b-list__box-list-item'):
                txt = li.get_text(separator='|', strip=True)
                parts = txt.split('|')
                if len(parts) == 2 and label.lower() in parts[0].lower():
                    return parts[1].strip()
            return ''

        feats.append({
            'fighter_url': url, 'name': name,
            'height': stat('Height'), 'weight': stat('Weight'),
            'reach':  stat('Reach'),  'stance': stat('Stance'),
            'dob':    stat('DOB'),
            'slpm':   stat('SLpM'),   'str_acc': stat('Str. Acc'),
            'sapm':   stat('SApM'),   'str_def': stat('Str. Def'),
            'td_avg': stat('TD Avg'), 'td_acc':  stat('TD Acc'),
            'td_def': stat('TD Def'), 'sub_avg': stat('Sub. Avg'),
        })

    if feats: save(pd.DataFrame(feats), path)
    log.info('Fighter scraping done.')

# ── Step 5: Build ufc_extended ────────────────────────────────────────────────
def build_extended():
    log.info('Building ufc_extended.csv...')
    totals = pd.read_csv(OUT_DIR / 'fight_totals.csv')
    events = pd.read_csv(OUT_DIR / 'events.csv')
    feat_p = OUT_DIR / 'fighter_features.csv'

    df = totals.merge(events[['event_name', 'location']], on='event_name', how='left')

    if feat_p.exists():
        feats = pd.read_csv(feat_p)
        df = df.merge(
            feats[['fighter_url','name','height','weight','reach','stance','dob']],
            on='fighter_url', how='left')

    df.to_csv(OUT_DIR / 'ufc_extended.csv', index=False)
    log.info(f'ufc_extended.csv: {len(df)} rows.')

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    log.info('=== UFCStats scraper started (v4) ===')

    with sync_playwright() as pw:
        s = Session(pw)

        events_df   = scrape_events(s)
        fight_links = scrape_fight_links(s, events_df)
        scrape_fights(s, fight_links)

        totals_df = pd.read_csv(OUT_DIR / 'fight_totals.csv')
        scrape_fighters(s, totals_df)

        s.browser.close()

    build_extended()
    log.info('=== Done ===')
