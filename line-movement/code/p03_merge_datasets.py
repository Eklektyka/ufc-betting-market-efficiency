"""
merge_datasets.py
-----------------
Joins UFCStats fights (ufcstats_raw/fights.csv) with BFO odds
(bfo_odds_final/bfo_odds_raw.csv) into one fight-level CSV.

Output: merged/ufc_fights_with_odds.csv
  - One row per fight (both fighters' stats + odds on same row)
  - Filtered to 2007-01-01 through 2026-04-30 (BFO coverage window)

Match key: (fighter_ufc_id, event_date)
  - BFO fighter_ufc_id maps directly to the hex ID in UFCStats fighter_url
  - Falls back to ±1 day if exact date doesn't match (handles timezone edge cases)
"""

import csv
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
UFC_CSV  = Path("ufcstats_raw/fights.csv")
BFO_CSV  = Path(
    r"C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers"
    r"\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_raw.csv"
)
OUT_DIR  = Path("merged")
OUT_CSV  = OUT_DIR / "ufc_fights_with_odds.csv"

DATE_MIN = date(2007, 1, 1)
DATE_MAX = date(2026, 4, 30)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_ufc_date(s: str):
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def parse_bfo_date(s: str):
    s = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", s.strip())
    for fmt in ("%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def extract_ufc_id(url: str) -> str:
    m = re.search(r"/fighter-details/([a-f0-9]+)", url)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Load + parse
# ---------------------------------------------------------------------------
print("Loading UFCStats fights …")
with UFC_CSV.open(encoding="utf-8") as f:
    ufc_rows = list(csv.DictReader(f))

print("Loading BFO odds …")
with BFO_CSV.open(encoding="utf-8") as f:
    bfo_rows = list(csv.DictReader(f))

# ---------------------------------------------------------------------------
# Filter both to date window
# ---------------------------------------------------------------------------
ufc_parsed = []
for r in ufc_rows:
    d = parse_ufc_date(r["date"])
    if d and DATE_MIN <= d <= DATE_MAX:
        ufc_parsed.append((r, d))

bfo_parsed = []
for r in bfo_rows:
    d = parse_bfo_date(r["date_raw"])
    if d and DATE_MIN <= d <= DATE_MAX:
        bfo_parsed.append((r, d))

print(f"UFC rows in window: {len(ufc_parsed)} ({len(ufc_parsed)//2} fights)")
print(f"BFO rows in window: {len(bfo_parsed)}")

# ---------------------------------------------------------------------------
# Build BFO lookup: (fighter_ufc_id, date) -> bfo_row
# ---------------------------------------------------------------------------
bfo_lookup: dict[tuple, dict] = {}
for r, d in bfo_parsed:
    uid = r["fighter_ufc_id"].strip()
    key = (uid, d)
    bfo_lookup[key] = r

# ---------------------------------------------------------------------------
# Group UFC rows by fight_url → pair of fighter rows
# ---------------------------------------------------------------------------
fight_groups: dict[str, list] = defaultdict(list)
fight_dates:  dict[str, date]  = {}
for r, d in ufc_parsed:
    fight_groups[r["fight_url"]].append((r, d))
    fight_dates[r["fight_url"]] = d

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------
STAT_FIELDS = [
    "kd", "sig_str_landed", "sig_str_att",
    "total_str_landed", "total_str_att",
    "td_landed", "td_att", "sub_att", "rev", "ctrl_sec",
]
ODDS_FIELDS = [
    "odds_open", "odds_close_lo", "odds_close_hi", "odds_sparkline",
]

FIELDNAMES = [
    # Fight metadata
    "fight_url", "event_url", "event_name", "date",
    "method", "round", "time", "division",
    # Fighter A
    "fighter_a", "fighter_a_url", "result_a",
] + [f + "_a" for f in STAT_FIELDS] + ODDS_FIELDS + [
    # Fighter B
    "fighter_b", "fighter_b_url", "result_b",
] + [f + "_b" for f in STAT_FIELDS] + [f.replace("odds_", "odds_opp_") for f in ODDS_FIELDS] + [
    # Match quality
    "odds_matched",
]

# ---------------------------------------------------------------------------
# Build output rows
# ---------------------------------------------------------------------------
OUT_DIR.mkdir(exist_ok=True)

matched = 0
unmatched_fights = 0
total_fights = 0
no_pair = 0

unmatched_samples = []

def lookup_bfo(uid: str, d: date):
    """Try exact date, then ±1 day."""
    for delta in (0, 1, -1):
        row = bfo_lookup.get((uid, d + timedelta(days=delta)))
        if row:
            return row
    return None


def bfo_odds(bfo_row) -> dict:
    if bfo_row is None:
        return {f: "" for f in ODDS_FIELDS}
    return {
        "odds_open":      bfo_row.get("fighter_open", ""),
        "odds_close_lo":  bfo_row.get("fighter_close_lo", ""),
        "odds_close_hi":  bfo_row.get("fighter_close_hi", ""),
        "odds_sparkline": bfo_row.get("fighter_sparkline", ""),
    }


output_rows = []

for url, pair in fight_groups.items():
    total_fights += 1
    if len(pair) != 2:
        no_pair += 1
        continue

    # Order: winner (W) first; if draw/NC pick arbitrarily
    pair.sort(key=lambda x: (x[0]["result"] != "W"))
    (ra, da), (rb, db) = pair

    uid_a = extract_ufc_id(ra["fighter_url"])
    uid_b = extract_ufc_id(rb["fighter_url"])
    bfo_a = lookup_bfo(uid_a, da)
    bfo_b = lookup_bfo(uid_b, db)

    if bfo_a or bfo_b:
        matched += 1
        odds_match = "full" if (bfo_a and bfo_b) else "partial"
    else:
        unmatched_fights += 1
        odds_match = "none"
        if len(unmatched_samples) < 10:
            unmatched_samples.append(f"{ra['fighter_name']} vs {rb['fighter_name']} ({ra['date']})")

    row = {
        "fight_url":   url,
        "event_url":   ra["event_url"],
        "event_name":  ra["event_name"],
        "date":        ra["date"],
        "method":      ra["method"],
        "round":       ra["round"],
        "time":        ra["time"],
        "division":    ra["division"],
        # Fighter A
        "fighter_a":     ra["fighter_name"],
        "fighter_a_url": ra["fighter_url"],
        "result_a":      ra["result"],
        **{f + "_a": ra[f] for f in STAT_FIELDS},
        **bfo_odds(bfo_a),
        # Fighter B
        "fighter_b":     rb["fighter_name"],
        "fighter_b_url": rb["fighter_url"],
        "result_b":      rb["result"],
        **{f + "_b": rb[f] for f in STAT_FIELDS},
        **{f.replace("odds_", "odds_opp_"): v for f, v in bfo_odds(bfo_b).items()},
        "odds_matched": odds_match,
    }
    output_rows.append(row)

# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------
with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDNAMES)
    w.writeheader()
    w.writerows(output_rows)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
print(f"\n=== Merge complete ===")
print(f"Total fights in window:       {total_fights}")
print(f"  Skipped (no pair):          {no_pair}")
print(f"  Odds fully matched (both):  {sum(1 for r in output_rows if r['odds_matched']=='full')}")
print(f"  Odds partially matched:     {sum(1 for r in output_rows if r['odds_matched']=='partial')}")
print(f"  Odds not matched:           {unmatched_fights}")
print(f"\nOutput rows: {len(output_rows)}")
print(f"Output file: {OUT_CSV}")
if unmatched_samples:
    print(f"\nSample unmatched fights:")
    for s in unmatched_samples:
        print(f"  {s}")
