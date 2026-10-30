#!/usr/bin/env python3
"""Build card_map for Aug 2025 – Apr 2026 from bfo_odds_raw.csv ↔ UFCStats dates."""

import csv, re, os, unicodedata
from datetime import datetime, timedelta
from collections import defaultdict

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def parse_bfo_date(s):
    s = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', s.strip())
    try:
        return datetime.strptime(s, '%b %d %Y')
    except:
        return None

def norm(name):
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    return name.lower().strip()

# ── Load BFO raw events ──
rawpath = (r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers'
           r'\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_raw.csv')
bfo_raw = {}  # (event_name, eid) -> date
with open(rawpath, 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        ename = row['event_name']
        eid = row['event_bfo_id'].replace('.0', '')
        dt = parse_bfo_date(row['date_raw'])
        nl = ename.lower()
        if dt and ('ufc' in nl or 'noche' in nl) and 'bjj' not in nl:
            key = (ename, eid)
            if key not in bfo_raw:
                bfo_raw[key] = dt

# ── Load UFCStats events ──
ufcpath = (r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers'
           r'\UFC Post-KO Analysis\ufcstats_raw\fight_totals_clean.csv')
ufc_events = {}
with open(ufcpath, 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        ename = row['event_name']
        try:
            dt = datetime.strptime(row['date'], '%B %d, %Y')
        except:
            continue
        if ename not in ufc_events:
            ufc_events[ename] = dt

# ── Match BFO raw events to UFCStats by date (≤1 day) ──
# Group BFO events by date
bfo_by_date = defaultdict(list)
for (ename, eid), dt in bfo_raw.items():
    bfo_by_date[dt].append((ename, eid))
    bfo_by_date[dt + timedelta(days=1)].append((ename, eid))   # ±1 day
    bfo_by_date[dt - timedelta(days=1)].append((ename, eid))

# For each UFCStats event, find BFO matches within ±1 day
new_card_map = []
ambiguities = []

for ufc_name, ufc_dt in sorted(ufc_events.items(), key=lambda x: x[1]):
    if ufc_dt < datetime(2025, 8, 1) or ufc_dt > datetime(2026, 4, 18):
        continue
    if 'road to ufc' in ufc_name.lower() or 'bjj' in ufc_name.lower():
        continue

    matches = []
    for delta in [timedelta(0), timedelta(days=1), timedelta(days=-1)]:
        check_dt = ufc_dt + delta
        for ename, eid in bfo_by_date.get(check_dt, []):
            if (ename, eid) not in [(m[0], m[1]) for m in matches]:
                actual_dt = bfo_raw[(ename, eid)]
                matches.append((ename, eid, actual_dt))

    # Deduplicate
    seen = set()
    unique_matches = []
    for ename, eid, dt in matches:
        if eid not in seen:
            seen.add(eid)
            unique_matches.append((ename, eid, dt))

    if len(unique_matches) == 0:
        print(f'  NO BFO MATCH: {ufc_name} ({ufc_dt.strftime("%Y-%m-%d")})')
    elif len(unique_matches) == 1:
        ename, eid, dt = unique_matches[0]
        new_card_map.append({
            'bfo_event_id': eid,
            'card_key': ufc_name,
            'canonical_date': ufc_dt.strftime('%Y-%m-%d'),
            'segment': 'main',
        })
    else:
        # Multiple BFO events for one UFC card — split card
        # Sort by date: earlier = early_prelims, later/same = main
        unique_matches.sort(key=lambda x: (x[2], x[1]))

        # Heuristic: if names differ (e.g. "UFC 319 Odds" vs "UFC 319"),
        # the one with "Odds" suffix or higher event ID is usually main
        for i, (ename, eid, dt) in enumerate(unique_matches):
            if len(unique_matches) == 2:
                segment = 'early_prelims' if i == 0 else 'main'
                # But check: if first is later date, swap
                if unique_matches[0][2] > unique_matches[1][2]:
                    segment = 'main' if i == 0 else 'early_prelims'
            else:
                segment = f'part_{i+1}'

            new_card_map.append({
                'bfo_event_id': eid,
                'card_key': ufc_name,
                'canonical_date': ufc_dt.strftime('%Y-%m-%d'),
                'segment': segment,
            })

        amb_str = '; '.join(f'{e[1]}={e[0]} ({e[2].strftime("%Y-%m-%d")})'
                           for e in unique_matches)
        ambiguities.append(f'{ufc_name}: {amb_str}')
        print(f'  SPLIT: {ufc_name} -> {amb_str}')

# ── Load existing card_map (Apr 2026+) ──
existing = []
with open('card_map.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        existing.append(row)

# Merge: keep existing, add new ones that aren't already there
existing_eids = {r['bfo_event_id'] for r in existing}
added = 0
for row in new_card_map:
    if row['bfo_event_id'] not in existing_eids:
        existing.append(row)
        added += 1

# Sort by canonical_date, then bfo_event_id
existing.sort(key=lambda r: (r['canonical_date'], r['bfo_event_id']))

with open('card_map.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['bfo_event_id', 'card_key', 'canonical_date', 'segment'])
    w.writeheader()
    w.writerows(existing)

print(f'\ncard_map.csv: {len(existing)} total rows ({added} new)')

if ambiguities:
    print(f'\n=== AMBIGUITIES (split cards) ===')
    for a in ambiguities:
        print(f'  {a}')

# Show the new entries
print(f'\n=== NEW ENTRIES ===')
for row in new_card_map:
    if row['bfo_event_id'] not in existing_eids:
        print(f'  {row["canonical_date"]} | {row["bfo_event_id"]:>5} | {row["segment"]:15} | {row["card_key"]}')
