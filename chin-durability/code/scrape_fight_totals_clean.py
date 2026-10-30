"""
scrape_fight_totals_clean.py
============================
Re-scrapes each fight detail page and correctly parses the fight Totals table
by extracting <p> elements within each <td> separately (Fighter A = first <p>,
Fighter B = second <p>), avoiding the get_text() concatenation bug.

Output: ufcstats_raw/fight_totals_clean.csv
  One row per fighter per fight, columns:
    fight_url, event_name, date, fighter_a, fighter_b,
    fighter_url_a, fighter_url_b, result_a, result_b,
    method, round, time, division,
    kd, sig_str_landed, sig_str_att, sig_str_pct,
    total_str_landed, total_str_att,
    td_landed, td_att, td_pct,
    sub_att, rev, ctrl_sec

Resumable — skips fight_urls already in the output file.
Run: py scrape_fight_totals_clean.py
"""

import time, logging, sys, re
from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL    = 'http://www.ufcstats.com'
IN_DIR      = Path(r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\ufcstats_raw')
OUT_PATH    = IN_DIR / 'fight_totals_clean.csv'
LINKS_PATH  = IN_DIR / 'fight_links.csv'

DELAY       = 0.5   # seconds between page loads
FLUSH_EVERY = 50    # write to disk every N fights

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(IN_DIR / 'scrape_clean.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)


# ── Browser session ───────────────────────────────────────────────────────────
class Session:
    def __init__(self, pw):
        self.pw = pw
        self.browser = None
        self.page = None
        self._launch()

    def _launch(self):
        if self.browser:
            try: self.browser.close()
            except Exception: pass
        self.browser = self.pw.chromium.launch(headless=True)
        self.page = self.browser.new_page()
        log.info('Browser launched — warming up...')
        self.page.goto(BASE_URL, wait_until='domcontentloaded', timeout=30000)
        time.sleep(3)
        log.info('Warm-up done.')

    def get_html(self, url, retries=5):
        for attempt in range(retries):
            try:
                self.page.goto(url, wait_until='domcontentloaded', timeout=25000)
                time.sleep(DELAY)
                return self.page.content()
            except PWTimeout:
                log.warning(f'Timeout attempt {attempt+1}: {url}')
                time.sleep(min(2 ** attempt, 16))
            except Exception as e:
                log.warning(f'Error attempt {attempt+1}: {url} — {str(e)[:120]}')
                try:
                    self.page.close()
                    self.page = self.browser.new_page()
                    self.page.goto(BASE_URL, wait_until='domcontentloaded', timeout=20000)
                    time.sleep(2)
                except Exception:
                    log.warning('Page restart failed — relaunching browser...')
                    try: self._launch()
                    except Exception as e2: log.error(f'Relaunch failed: {e2}')
                time.sleep(min(2 ** attempt, 16))
        log.error(f'Giving up: {url}')
        return None


# ── Parsers ───────────────────────────────────────────────────────────────────
def cell_values(td):
    """Extract [val_a, val_b] from a <td> containing two <p> tags."""
    ps = td.find_all('p')
    if len(ps) >= 2:
        return ps[0].get_text(strip=True), ps[1].get_text(strip=True)
    # Fallback: single value (treat as fighter A only)
    return td.get_text(strip=True), ''


def parse_of(s):
    """Parse 'X of Y' → (X, Y). Returns (None, None) on failure."""
    nums = re.findall(r'\d+', str(s))
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    if len(nums) == 1:
        return int(nums[0]), None
    return None, None


def parse_pct(s):
    """Parse '60%' → 60.0. Returns None on failure."""
    m = re.search(r'(\d+(?:\.\d+)?)\s*%', str(s))
    return float(m.group(1)) if m else None


def parse_ctrl(s):
    """Parse 'M:SS' → total seconds. Returns None on failure."""
    m = re.match(r'(\d+):(\d+)', str(s).strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def meta_value(soup, label):
    for el in soup.select('i.b-fight-details__label'):
        if label.lower() in el.get_text(strip=True).lower():
            p = el.find_parent()
            if p:
                return p.get_text(strip=True).replace(el.get_text(strip=True), '').strip()
    return ''


def parse_fight(html, fight_url, event_name, date):
    """
    Parse fight detail page. Returns list of 2 dicts (one per fighter),
    or empty list on failure.
    """
    soup = BeautifulSoup(html, 'html.parser')
    rows = []

    # Fighter names and URLs
    name_els = soup.select('h3.b-fight-details__person-name a')
    fighters = [el.get_text(strip=True) for el in name_els[:2]]
    f_urls   = [el['href'] for el in name_els[:2]]
    while len(fighters) < 2: fighters.append('')
    while len(f_urls)   < 2: f_urls.append('')

    # Results (W/L/D/NC)
    res_els = soup.select('i.b-fight-details__person-status')
    results = [el.get_text(strip=True) for el in res_els[:2]]
    while len(results) < 2: results.append('')

    method   = meta_value(soup, 'Method')
    round_n  = meta_value(soup, 'Round')
    time_str = meta_value(soup, 'Time')
    division = meta_value(soup, 'Weight class')

    tables = soup.select('table.b-fight-details__table')
    if not tables:
        log.warning(f'No tables found: {fight_url}')
        return []

    # tables[0] = fight Totals
    tbl = tables[0]
    data_rows = tbl.select('tbody tr')
    if not data_rows:
        log.warning(f'No data rows in totals table: {fight_url}')
        return []

    # The totals table has ONE data row; each <td> contains two <p> values
    row = data_rows[0]
    tds = row.find_all('td')
    if len(tds) < 10:
        log.warning(f'Too few columns ({len(tds)}) in totals table: {fight_url}')
        return []

    # Column layout (0-indexed): 0=fighter, 1=kd, 2=sig_str, 3=sig_str_pct,
    #   4=total_str, 5=td, 6=td_pct, 7=sub_att, 8=rev, 9=ctrl
    vals = [cell_values(td) for td in tds]

    for fi in range(2):
        kd_raw         = vals[1][fi]
        sig_str_raw    = vals[2][fi]
        sig_str_pct_raw= vals[3][fi]
        total_str_raw  = vals[4][fi]
        td_raw         = vals[5][fi]
        td_pct_raw     = vals[6][fi]
        sub_att_raw    = vals[7][fi]
        rev_raw        = vals[8][fi]
        ctrl_raw       = vals[9][fi]

        sig_l, sig_a   = parse_of(sig_str_raw)
        tot_l, tot_a   = parse_of(total_str_raw)
        td_l,  td_a    = parse_of(td_raw)

        rows.append({
            'fight_url'     : fight_url,
            'event_name'    : event_name,
            'date'          : date,
            'fighter'       : fighters[fi],
            'fighter_url'   : f_urls[fi],
            'fighter_opp'   : fighters[1 - fi],
            'fighter_url_opp': f_urls[1 - fi],
            'result'        : results[fi],
            'result_opp'    : results[1 - fi],
            'method'        : method,
            'round'         : round_n,
            'time'          : time_str,
            'division'      : division,
            'kd'            : pd.to_numeric(kd_raw, errors='coerce'),
            'sig_str_landed': sig_l,
            'sig_str_att'   : sig_a,
            'sig_str_pct'   : parse_pct(sig_str_pct_raw),
            'total_str_landed': tot_l,
            'total_str_att' : tot_a,
            'td_landed'     : td_l,
            'td_att'        : td_a,
            'td_pct'        : parse_pct(td_pct_raw),
            'sub_att'       : pd.to_numeric(sub_att_raw, errors='coerce'),
            'rev'           : pd.to_numeric(rev_raw, errors='coerce'),
            'ctrl_sec'      : parse_ctrl(ctrl_raw),
        })

    return rows


# ── Main scrape loop ──────────────────────────────────────────────────────────
def main():
    fight_links = pd.read_csv(LINKS_PATH)
    all_urls = fight_links['fight_url'].dropna().tolist()
    log.info(f'Total fight URLs: {len(all_urls)}')

    # Resume: skip already-scraped fights
    done = set()
    if OUT_PATH.exists():
        existing = pd.read_csv(OUT_PATH)
        done = set(existing['fight_url'].unique())
        log.info(f'Resuming — {len(done)} fights already done, {len(all_urls)-len(done)} remaining.')

    todo = [u for u in all_urls if u not in done]
    if not todo:
        log.info('All fights already scraped.')
        return

    buffer = []
    n_done = 0
    n_failed = 0

    with sync_playwright() as pw:
        s = Session(pw)
        for i, url in enumerate(todo):
            row_meta = fight_links[fight_links['fight_url'] == url].iloc[0]
            html = s.get_html(url)
            if html is None:
                n_failed += 1
                log.error(f'[{i+1}/{len(todo)}] FAILED: {url}')
                continue

            parsed = parse_fight(html, url, row_meta['event_name'], row_meta['date'])
            if parsed:
                buffer.extend(parsed)
                n_done += 1
            else:
                n_failed += 1
                log.warning(f'[{i+1}/{len(todo)}] Parse returned empty: {url}')

            if (i + 1) % FLUSH_EVERY == 0 and buffer:
                _flush(buffer)
                buffer = []
                log.info(f'Progress: {i+1}/{len(todo)} processed ({n_done} ok, {n_failed} failed)')

        if buffer:
            _flush(buffer)

    log.info(f'Done. {n_done} fights scraped, {n_failed} failed. Output: {OUT_PATH}')


def _flush(rows):
    df = pd.DataFrame(rows)
    if OUT_PATH.exists():
        existing = pd.read_csv(OUT_PATH)
        df = pd.concat([existing, df], ignore_index=True).drop_duplicates(
            subset=['fight_url', 'fighter_url'])
    df.to_csv(OUT_PATH, index=False)


if __name__ == '__main__':
    main()
