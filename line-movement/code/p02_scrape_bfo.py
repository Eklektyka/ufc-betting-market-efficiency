"""
bfo_scraper.py
--------------
Scrapes https://www.bestfightodds.com for UFC bout odds.

Outputs
  bfo_raw/bfo_odds.csv  – one row per fighter per bout

SITE NOTE: The /organizations/1-Ultimate-Fighting-Championship URL no longer
exists (returns 404). Event URLs are collected from three sources:
  1. BFO search with multiple UFC-specific queries (covers historical events)
  2. The /archive page (recently completed events)
  3. The homepage (upcoming/current events)
All are filtered to UFC-only events before scraping.

Event page structure (confirmed via live inspection):
  - Two <table> elements per event: Table[0] sticky name-only, Table[1] odds
  - Table[1] tbody rows: <tr id="mu-{id}"> = fighter A, next <tr> = fighter B
  - Prop rows have class "pr" and no fighter name — skip them
  - Odds in <td class="but-sg"> cells; first non-empty = open, last = close
  - Date: JSON-LD "startDate" field (ISO format) or full date in page text
"""

import csv
import json
import logging
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "https://www.bestfightodds.com"
OUT_DIR = Path("bfo_raw")
ODDS_CSV = OUT_DIR / "bfo_odds.csv"
LOG_FILE = OUT_DIR / "scrape.log"

RATE_PAGE   = 1.0   # seconds between page loads
RATE_EVENT  = 2.0   # extra wait between events
MAX_RETRIES = 4
FLUSH_EVERY = 20    # events

FIELDS = [
    "fighter_name", "fighter_url",
    "opponent_name",
    "event_name", "event_url",
    "date",
    "odds_open",
    "odds_close",
]

# Search queries to collect historical UFC event URLs.
# Each returns up to 25 results; multiple queries cover different eras.
SEARCH_QUERIES = [
    "UFC",
    "UFC Fight Night",
    "UFC on FOX",
    "UFC on ESPN",
    "UFC on ABC",
    "UFC 1", "UFC 2", "UFC 3", "UFC 4", "UFC 5",
    "UFC 6", "UFC 7", "UFC 8", "UFC 9",
    "Ultimate Fighter",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging():
    OUT_DIR.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_done_urls(csv_path: Path, field: str) -> set:
    if not csv_path.exists():
        return set()
    with csv_path.open(encoding="utf-8") as f:
        return {row[field] for row in csv.DictReader(f) if row.get(field)}


def _navigate(page, url: str, timeout: int = 30_000) -> bool:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            time.sleep(RATE_PAGE)
            return True
        except PWTimeout:
            wait = 2 ** attempt
            log.warning("Timeout %s (attempt %d/%d), retry %ds", url, attempt, MAX_RETRIES, wait)
            time.sleep(wait)
        except Exception as exc:
            wait = 2 ** attempt
            log.warning("Error %s: %s (attempt %d/%d), retry %ds", url, exc, attempt, MAX_RETRIES, wait)
            time.sleep(wait)
    log.error("Giving up on %s after %d attempts", url, MAX_RETRIES)
    return False


def _is_ufc(text: str) -> bool:
    """Return True if an event name/URL looks like a UFC event."""
    t = text.lower()
    return (
        "ufc" in t
        or "ultimate fighter" in t
        or "the ultimate fighter" in t
    )


def _parse_american_odds(raw: str):
    raw = raw.strip()
    if not raw or raw in ("--", "N/A", "EVS", "PK"):
        return None
    m = re.match(r"^([+-]?\d+)", raw.replace(",", ""))
    if m:
        return int(m.group(1))
    return None


def _extract_date(page) -> str:
    """
    Try multiple strategies to get ISO date from BFO event page.
    Returns 'YYYY-MM-DD' or empty string.
    """
    # 1. JSON-LD startDate
    html = page.content()
    schema = re.findall(r'"startDate"\s*:\s*"(\d{4}-\d{2}-\d{2})"', html)
    if schema:
        return schema[0]

    # 2. Full date text (e.g. "June 27, 2026")
    full = re.findall(
        r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
        r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
        r'\s+\d{1,2},?\s+(\d{4})',
        html
    )
    if full:
        from datetime import datetime
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
            try:
                m = re.search(
                    r'((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
                    r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
                    r'\s+\d{1,2},?\s+\d{4})',
                    html
                )
                if m:
                    return datetime.strptime(m.group(1).replace(",", ""), fmt.replace(",", "")).strftime("%Y-%m-%d")
            except ValueError:
                continue

    # 3. Page title (e.g. "UFC Fight Night for June 27 | ...")
    title_el = page.query_selector("title")
    if title_el:
        title = title_el.inner_text()
        # Title has month/day but not year; not useful on its own
        pass

    return ""


# ---------------------------------------------------------------------------
# Event URL collection
# ---------------------------------------------------------------------------
def collect_event_urls(page) -> list[tuple[str, str]]:
    """
    Return deduplicated list of (event_url, event_name) for UFC events.
    Sources: search queries, archive page, homepage.
    """
    seen: dict[str, str] = {}  # url → name

    # --- 1. Search queries ---
    for query in SEARCH_QUERIES:
        url = f"{BASE_URL}/search?query={query.replace(' ', '+')}"
        log.info("Search: %s", url)
        if not _navigate(page, url):
            continue
        html = page.content()
        # Search results: <a href="/events/...">Event Name</a>
        matches = re.findall(r'href="(/events/([^"]+))"[^>]*>([^<]{3,80})</a>', html)
        for path, _, name in matches:
            name = name.strip()
            full_url = BASE_URL + path
            if _is_ufc(name) or _is_ufc(path):
                if full_url not in seen:
                    seen[full_url] = name
        log.info("  found %d UFC events (total: %d)", sum(1 for _ in matches), len(seen))
        time.sleep(0.5)

    # --- 2. Archive page ---
    log.info("Fetching archive page")
    if _navigate(page, f"{BASE_URL}/archive"):
        html = page.content()
        rows = re.findall(
            r'href="(/events/([^"]+))"[^>]*>\s*([^<]{3,80})\s*</a>',
            html
        )
        for path, _, name in rows:
            name = name.strip()
            full_url = BASE_URL + path
            if _is_ufc(name) or _is_ufc(path):
                if full_url not in seen:
                    seen[full_url] = name

    # --- 3. Homepage (current/upcoming) ---
    log.info("Fetching homepage")
    if _navigate(page, BASE_URL):
        html = page.content()
        # Event divs: <div class="table-div" id="event{N}">
        # Event links: <a href="/events/..."><h1>Name</h1></a>
        matches = re.findall(
            r'href="(/events/([^"]+))"[^>]*><h[12]>([^<]+)</h[12]>',
            html
        )
        for path, _, name in matches:
            name = name.strip()
            full_url = BASE_URL + path
            if _is_ufc(name) or _is_ufc(path):
                if full_url not in seen:
                    seen[full_url] = name

    # Sort newest-first by BFO event ID (trailing number in the URL slug).
    # New-format pages (with embedded odds) start around ID ~2016 (Jan 2021).
    # Sorting descending means we process 2024-2026 events first, then
    # 2021-2023, and only hit old no-data events at the very end.
    def _bfo_id(url: str) -> int:
        m = re.search(r"-(\d+)$", url)
        return int(m.group(1)) if m else 0

    result = sorted(seen.items(), key=lambda kv: _bfo_id(kv[0]), reverse=True)
    result = [(url, name) for url, name in result]
    log.info("Total unique UFC event URLs collected: %d (sorted newest-first)", len(result))
    return result


# ---------------------------------------------------------------------------
# Event page parser
# ---------------------------------------------------------------------------
def parse_event(page, event_url: str, event_name: str) -> list[dict]:
    """
    Parse a BFO event page and return two rows per bout (one per fighter).
    """
    if not _navigate(page, event_url):
        return []

    date = _extract_date(page)

    # The odds table is the second <table> (first is the sticky name-column table).
    # New format (2021+): cells are <td class="but-sg"><span id="oID...">
    # Old format (pre-2021): cells are empty TDs, no embedded odds → skip silently.
    tables = page.query_selector_all("table")
    odds_table = None
    for t in tables:
        if t.query_selector("td.but-sg"):
            odds_table = t
            break

    if not odds_table:
        log.debug("No new-format odds on %s (old page layout, skipping)", event_url)
        return []

    rows = odds_table.query_selector_all("tbody tr")
    output = []
    i = 0
    while i < len(rows):
        row_a = rows[i]
        # Skip prop rows
        if "pr" in (row_a.get_attribute("class") or ""):
            i += 1
            continue

        name_el_a = row_a.query_selector("th span.t-b-fcc")
        if not name_el_a:
            i += 1
            continue

        # Look for fighter B in the next non-prop row
        j = i + 1
        while j < len(rows) and "pr" in (rows[j].get_attribute("class") or ""):
            j += 1

        if j >= len(rows):
            i += 1
            continue

        row_b = rows[j]
        name_el_b = row_b.query_selector("th span.t-b-fcc")
        if not name_el_b:
            i += 1
            continue

        # Parse each fighter
        fa = _parse_fighter_row(row_a, BASE_URL)
        fb = _parse_fighter_row(row_b, BASE_URL)

        if fa and fb:
            fa["opponent_name"] = fb["fighter_name"]
            fb["opponent_name"] = fa["fighter_name"]
            for r in (fa, fb):
                r["event_name"] = event_name
                r["event_url"] = event_url
                r["date"] = date
            output.extend([fa, fb])

        i = j + 1  # advance past fighter B

    log.info("  Parsed %d fighter rows from %s", len(output), event_url)
    return output


def _parse_fighter_row(tr, base_url: str) -> dict | None:
    name_el = tr.query_selector("th span.t-b-fcc")
    if not name_el:
        return None
    fighter_name = name_el.inner_text().strip()

    href_el = tr.query_selector("th a[href^='/fighters/']")
    fighter_href = href_el.get_attribute("href") if href_el else ""
    fighter_url = base_url + fighter_href if fighter_href else ""

    # Odds cells: <td class="but-sg"><span id="oID...">value</span>...
    odds_cells = tr.query_selector_all("td.but-sg")
    all_odds = []
    for td in odds_cells:
        span = td.query_selector("span[id^='oID']")
        if span:
            raw = span.inner_text().strip()
            parsed = _parse_american_odds(raw)
            if parsed is not None:
                all_odds.append(parsed)

    odds_open  = all_odds[0]  if all_odds else None
    odds_close = all_odds[-1] if all_odds else None

    return {
        "fighter_name": fighter_name,
        "fighter_url":  fighter_url,
        "opponent_name": "",   # filled by caller
        "event_name":   "",    # filled by caller
        "event_url":    "",    # filled by caller
        "date":         "",    # filled by caller
        "odds_open":    odds_open,
        "odds_close":   odds_close,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    setup_logging()
    OUT_DIR.mkdir(exist_ok=True)

    done_event_urls = _load_done_urls(ODDS_CSV, "event_url")
    log.info("Already-done event URLs: %d", len(done_event_urls))

    file_existed = ODDS_CSV.exists()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = ctx.new_page()

        event_list = collect_event_urls(page)

        if not file_existed:
            with ODDS_CSV.open("w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDS).writeheader()

        pending: list[dict] = []
        events_since_flush = 0
        total_written = 0

        def _flush(force=False):
            nonlocal pending, total_written, events_since_flush
            if not pending:
                return
            if not force and events_since_flush < FLUSH_EVERY:
                return
            with ODDS_CSV.open("a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDS).writerows(pending)
            total_written += len(pending)
            log.info("Flushed %d rows (total: %d)", len(pending), total_written)
            pending = []
            events_since_flush = 0

        for event_url, event_name in event_list:
            if event_url in done_event_urls:
                log.debug("Skip (done): %s", event_url)
                continue

            log.info("Scraping: %s — %s", event_name, event_url)
            try:
                rows = parse_event(page, event_url, event_name)
                pending.extend(rows)
                done_event_urls.add(event_url)
                events_since_flush += 1
            except Exception as exc:
                log.error("Error on %s: %s", event_url, exc)

            time.sleep(RATE_EVENT)
            _flush()

        _flush(force=True)
        browser.close()

    log.info("Done. Total rows written this run: %d", total_written)


if __name__ == "__main__":
    main()
