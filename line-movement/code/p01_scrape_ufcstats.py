"""
ufcstats_scraper.py
-------------------
Scrapes http://www.ufcstats.com for all UFC events and fight-level stats.

Outputs
  ufcstats_raw/events.csv  – one row per event
  ufcstats_raw/fights.csv  – one row per fighter per fight (two rows per fight)

Key structural notes (confirmed via live inspection):
  - Events list: ?page=all loads all events in one page
  - Event rows: tr.b-statistics__table-row; link in i.b-statistics__table-content a
  - Date: span.b-statistics__date; Location: td.b-statistics__table-col_style_big-top-padding
  - Fight links on event page: tr[data-link] attributes
  - Fight page: 2 per-round tables; need to SUM across rounds for totals
  - Table 0 columns: Fighter, KD, Sig.str., Sig.str.%, Total str., TD, TD%, Sub.Att, Rev., Ctrl
  - Method/Round/Time in i.b-fight-details__text-item elements within p.b-fight-details__text
  - Division in i.b-fight-details__fight-title
"""

import csv
import logging
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "http://www.ufcstats.com"
EVENTS_URL = f"{BASE_URL}/statistics/events/completed?page=all"
OUT_DIR = Path("ufcstats_raw")
EVENTS_CSV = OUT_DIR / "events.csv"
FIGHTS_CSV = OUT_DIR / "fights.csv"
LOG_FILE = OUT_DIR / "scrape.log"

RATE_DELAY = 0.5
MAX_RETRIES = 5
FLUSH_EVERY = 50  # fight rows

EVENTS_FIELDS = ["event_url", "event_name", "date", "location"]
FIGHTS_FIELDS = [
    "fight_url", "event_url", "event_name", "date",
    "fighter_url", "fighter_name",
    "fighter_url_opp", "fighter_name_opp",
    "result",
    "method", "round", "time", "division",
    "kd", "sig_str_landed", "sig_str_att",
    "total_str_landed", "total_str_att",
    "td_landed", "td_att", "sub_att", "rev", "ctrl_sec",
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
def _load_done_urls(csv_path: Path, url_field: str) -> set:
    if not csv_path.exists():
        return set()
    with csv_path.open(encoding="utf-8") as f:
        return {row[url_field] for row in csv.DictReader(f) if row.get(url_field)}


def _navigate(page, url: str, wait_for: str | None = None, timeout: int = 30_000) -> bool:
    """Navigate with retry + exponential back-off. Returns True on success."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            if wait_for:
                page.wait_for_selector(wait_for, timeout=15_000)
            time.sleep(RATE_DELAY)
            return True
        except PWTimeout:
            wait = 2 ** attempt
            log.warning("Timeout on %s (attempt %d/%d), retry in %ds", url, attempt, MAX_RETRIES, wait)
            time.sleep(wait)
        except Exception as exc:
            wait = 2 ** attempt
            log.warning("Error on %s: %s (attempt %d/%d), retry in %ds", url, exc, attempt, MAX_RETRIES, wait)
            time.sleep(wait)
    log.error("Giving up on %s after %d attempts", url, MAX_RETRIES)
    return False


def _safe_int(val: str, default: str = "") -> str:
    val = val.strip().replace("---", "").replace("--", "")
    try:
        return str(int(val))
    except ValueError:
        return default


def _ctrl_to_seconds(value: str) -> str:
    value = value.strip()
    if not value or value in ("--", "---"):
        return ""
    m = re.match(r"^(\d+):(\d{2})$", value)
    if m:
        return str(int(m.group(1)) * 60 + int(m.group(2)))
    return ""


def _parse_of(value: str) -> tuple[str, str]:
    """'X of Y' → (X, Y). Fallback → ('', '')."""
    value = value.strip()
    if " of " in value:
        parts = value.split(" of ", 1)
        return parts[0].strip(), parts[1].strip()
    return "", ""


def _add_of(a_landed: str, a_att: str, b_landed: str, b_att: str) -> tuple[str, str, str, str]:
    """Sum two 'X of Y' totals; keep '' if both are missing."""
    def to_int(v):
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    la, aa, lb, ab = to_int(a_landed), to_int(a_att), to_int(b_landed), to_int(b_att)
    if la is None and lb is None:
        return a_landed, a_att, b_landed, b_att
    la = (la or 0) + (lb or 0)
    aa = (aa or 0) + (ab or 0)
    return str(la), str(aa), str(la), str(aa)  # won't be used for both A and B simultaneously


def _sum_int(a: str, b: str) -> str:
    try:
        return str(int(a or 0) + int(b or 0))
    except (ValueError, TypeError):
        return a or b or ""


def _p_texts(td) -> tuple[str, str]:
    """Return (text_p0, text_p1) from a <td> that contains two <p> tags."""
    ps = td.query_selector_all("p")
    a = ps[0].inner_text().strip() if len(ps) > 0 else ""
    b = ps[1].inner_text().strip() if len(ps) > 1 else ""
    return a, b


# ---------------------------------------------------------------------------
# Events scraper
# ---------------------------------------------------------------------------
def scrape_events(page) -> list[dict]:
    log.info("Fetching events list: %s", EVENTS_URL)
    if not _navigate(page, EVENTS_URL, wait_for="tr.b-statistics__table-row"):
        log.error("Failed to load events page")
        return []

    events = []
    rows = page.query_selector_all("tr.b-statistics__table-row")
    for row in rows:
        link_el = row.query_selector("i.b-statistics__table-content a")
        if not link_el:
            continue
        event_url = link_el.get_attribute("href") or ""
        event_name = link_el.inner_text().strip()
        if not event_url or not event_name:
            continue

        date_el = row.query_selector("span.b-statistics__date")
        date = date_el.inner_text().strip() if date_el else ""

        loc_el = row.query_selector("td.b-statistics__table-col_style_big-top-padding")
        location = loc_el.inner_text().strip() if loc_el else ""

        events.append({
            "event_url": event_url,
            "event_name": event_name,
            "date": date,
            "location": location,
        })

    log.info("Found %d events", len(events))
    return events


# ---------------------------------------------------------------------------
# Fight URL extractor
# ---------------------------------------------------------------------------
def get_fight_urls(page, event_url: str) -> list[str]:
    if not _navigate(page, event_url, wait_for="table.b-fight-details__table"):
        return []
    rows = page.query_selector_all("tr[data-link]")
    urls = [r.get_attribute("data-link") for r in rows if r.get_attribute("data-link")]
    return urls


# ---------------------------------------------------------------------------
# Fight page parser
# ---------------------------------------------------------------------------
def parse_fight(page, fight_url: str, event_url: str, event_name: str, date: str) -> list[dict]:
    if not _navigate(page, fight_url, wait_for="div.b-fight-details__person"):
        return []

    # ---- Fighter names & URLs ----
    person_divs = page.query_selector_all("div.b-fight-details__person")
    if len(person_divs) < 2:
        log.warning("Fighters not found on %s", fight_url)
        return []

    def _person_info(div):
        a = div.query_selector("a")
        url_ = (a.get_attribute("href") or "").strip() if a else ""
        name = a.inner_text().strip() if a else ""
        status_el = div.query_selector("i.b-fight-details__person-status")
        status = status_el.inner_text().strip() if status_el else ""
        return url_, name, status

    url_a, name_a, raw_res_a = _person_info(person_divs[0])
    url_b, name_b, raw_res_b = _person_info(person_divs[1])

    def _norm(r: str) -> str:
        r = r.upper()
        if r in ("W", "WIN"):    return "W"
        if r in ("L", "LOSS"):   return "L"
        if r in ("D", "DRAW"):   return "D"
        if "NC" in r or "NO CONTEST" in r: return "NC"
        return r

    res_a, res_b = _norm(raw_res_a), _norm(raw_res_b)

    # ---- Method / Round / Time from <i.b-fight-details__text-item*> ----
    method, round_, time_, division = "", "", "", ""

    details_p = page.query_selector("p.b-fight-details__text")
    if details_p:
        items = details_p.query_selector_all(
            "i.b-fight-details__text-item_first, i.b-fight-details__text-item"
        )
        for item in items:
            label_el = item.query_selector("i.b-fight-details__label")
            label = label_el.inner_text().strip().rstrip(":").upper() if label_el else ""
            # value = all text after removing the label <i>
            value = item.evaluate("""el => {
                const c = el.cloneNode(true);
                c.querySelectorAll('i.b-fight-details__label').forEach(n => n.remove());
                return c.innerText.trim();
            }""")
            if label == "METHOD":
                method = value
            elif label == "ROUND":
                round_ = value
            elif label == "TIME":
                time_ = value

    # ---- Division from fight title ----
    title_el = page.query_selector("i.b-fight-details__fight-title")
    if title_el:
        division = title_el.inner_text().strip()

    # ---- Totals from first stats table (per-round; sum all rounds) ----
    # Table 0 columns: Fighter(0), KD(1), Sig.str.(2), Sig.str.%(3),
    #                  Total str.(4), TD(5), TD%(6), Sub.Att(7), Rev.(8), Ctrl(9)
    acc = {k: ["", ""] for k in
           ["kd", "sig_l", "sig_a", "tot_l", "tot_a",
            "td_l", "td_a", "sub", "rev", "ctrl"]}

    tables = page.query_selector_all("table.b-fight-details__table")
    if tables:
        tbl = tables[0]
        data_rows = [
            r for r in tbl.query_selector_all("tr")
            if r.query_selector_all("td")   # skip header + section-header rows
        ]
        for row in data_rows:
            tds = row.query_selector_all("td")
            if len(tds) < 10:
                continue

            def _accumulate(key, td, mode="int"):
                pa, pb = _p_texts(td)
                if mode == "of":
                    la, aa = _parse_of(pa)
                    lb, ab = _parse_of(pb)
                    acc[key + "_l"][0] = _sum_int(acc[key + "_l"][0], la)
                    acc[key + "_l"][1] = _sum_int(acc[key + "_l"][1], lb)
                    acc[key + "_a"][0] = _sum_int(acc[key + "_a"][0], aa)
                    acc[key + "_a"][1] = _sum_int(acc[key + "_a"][1], ab)
                elif mode == "ctrl":
                    acc[key][0] = _sum_int(acc[key][0], _ctrl_to_seconds(pa))
                    acc[key][1] = _sum_int(acc[key][1], _ctrl_to_seconds(pb))
                else:
                    acc[key][0] = _sum_int(acc[key][0], pa.replace("---", "0").replace("--", "0"))
                    acc[key][1] = _sum_int(acc[key][1], pb.replace("---", "0").replace("--", "0"))

            _accumulate("kd",  tds[1])
            _accumulate("sig", tds[2], mode="of")
            _accumulate("tot", tds[4], mode="of")
            _accumulate("td",  tds[5], mode="of")
            _accumulate("sub", tds[7])
            _accumulate("rev", tds[8])
            _accumulate("ctrl", tds[9], mode="ctrl")

    base = {
        "fight_url": fight_url, "event_url": event_url,
        "event_name": event_name, "date": date,
        "method": method, "round": round_, "time": time_, "division": division,
    }

    row_a = {
        **base,
        "fighter_url": url_a, "fighter_name": name_a,
        "fighter_url_opp": url_b, "fighter_name_opp": name_b,
        "result": res_a,
        "kd":               acc["kd"][0],
        "sig_str_landed":   acc["sig_l"][0],
        "sig_str_att":      acc["sig_a"][0],
        "total_str_landed": acc["tot_l"][0],
        "total_str_att":    acc["tot_a"][0],
        "td_landed":        acc["td_l"][0],
        "td_att":           acc["td_a"][0],
        "sub_att":          acc["sub"][0],
        "rev":              acc["rev"][0],
        "ctrl_sec":         acc["ctrl"][0],
    }
    row_b = {
        **base,
        "fighter_url": url_b, "fighter_name": name_b,
        "fighter_url_opp": url_a, "fighter_name_opp": name_a,
        "result": res_b,
        "kd":               acc["kd"][1],
        "sig_str_landed":   acc["sig_l"][1],
        "sig_str_att":      acc["sig_a"][1],
        "total_str_landed": acc["tot_l"][1],
        "total_str_att":    acc["tot_a"][1],
        "td_landed":        acc["td_l"][1],
        "td_att":           acc["td_a"][1],
        "sub_att":          acc["sub"][1],
        "rev":              acc["rev"][1],
        "ctrl_sec":         acc["ctrl"][1],
    }

    return [row_a, row_b]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    setup_logging()
    OUT_DIR.mkdir(exist_ok=True)

    done_fight_urls = _load_done_urls(FIGHTS_CSV, "fight_url")
    log.info("Already-done fight URLs: %d", len(done_fight_urls))

    fights_existed = FIGHTS_CSV.exists()

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

        # ---- Scrape + write events ----
        events = scrape_events(page)
        with EVENTS_CSV.open("w", newline="", encoding="utf-8") as ef:
            w = csv.DictWriter(ef, fieldnames=EVENTS_FIELDS)
            w.writeheader()
            w.writerows(events)
        log.info("Wrote %d events → %s", len(events), EVENTS_CSV)

        # ---- Initialise fights CSV ----
        if not fights_existed:
            with FIGHTS_CSV.open("w", newline="", encoding="utf-8") as ff:
                csv.DictWriter(ff, fieldnames=FIGHTS_FIELDS).writeheader()

        pending: list[dict] = []
        total_written = 0

        def _flush(force=False):
            nonlocal pending, total_written
            if not pending:
                return
            if not force and len(pending) < FLUSH_EVERY:
                return
            with FIGHTS_CSV.open("a", newline="", encoding="utf-8") as ff:
                csv.DictWriter(ff, fieldnames=FIGHTS_FIELDS).writerows(pending)
            total_written += len(pending)
            log.info("Flushed %d rows (total: %d)", len(pending), total_written)
            pending = []

        # ---- Scrape fights ----
        for event in events:
            ev_url   = event["event_url"]
            ev_name  = event["event_name"]
            ev_date  = event["date"]

            log.info("Event: %s", ev_name)
            fight_urls = get_fight_urls(page, ev_url)
            log.info("  %d fights found", len(fight_urls))

            for fight_url in fight_urls:
                if fight_url in done_fight_urls:
                    log.debug("  skip (done): %s", fight_url)
                    continue
                log.info("  Scraping: %s", fight_url)
                try:
                    rows = parse_fight(page, fight_url, ev_url, ev_name, ev_date)
                    pending.extend(rows)
                    done_fight_urls.add(fight_url)
                except Exception as exc:
                    log.error("  Error on %s: %s", fight_url, exc)

                _flush()

        _flush(force=True)
        browser.close()

    log.info("Done. Fight rows written this run: %d", total_written)


if __name__ == "__main__":
    main()
