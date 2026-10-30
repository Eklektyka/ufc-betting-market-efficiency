#!/usr/bin/env python3
"""POC join: rank=devigged+fill, test=ext(post-Apr27)."""

import csv, re, os, unicodedata
from datetime import datetime
from collections import defaultdict, Counter

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def normalize(name):
    _map = str.maketrans({
        '\u0142': 'l', '\u0141': 'L', '\u00f8': 'o', '\u00d8': 'O',
        '\u0111': 'd', '\u0110': 'D', '\u00df': 'ss',
        '\u2019': '', "'": '', '-': ' ',
    })
    name = name.translate(_map)
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower().strip()
    name = re.sub(r'\s+(jr|sr|ii|iii|iv)\.?$', '', name)
    return re.sub(r'\s+', ' ', name)


def token_set(name):
    return frozenset(normalize(name).split())


# ── card_map ──
card_map = {}
with open('card_map.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        card_map[row['bfo_event_id']] = row
eid_to_ck = {eid: cm['card_key'] for eid, cm in card_map.items()}

# ── RANK: devigged ──
base = os.path.join(
    r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers',
    'UFC Post-KO Analysis', 'bfo_odds_final')
dpath = os.path.join(base, 'bfo_odds_devigged.csv')

bfo_index = defaultdict(dict)

with open(dpath, 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        eid = row['event_bfo_id'].replace('.0', '')
        ck = eid_to_ck.get(eid, row['event_name'])
        fname = normalize(row['fighter_name'])
        oname = normalize(row['opponent_name'])
        pair = frozenset({fname, oname})
        if pair not in bfo_index[ck]:
            bfo_index[ck][pair] = {
                'f1': row['fighter_name'], 'f2': row['opponent_name'],
            }

# ── RANK supplement: fill ──
for fill_file in ('bfo_close_fill_2025.csv',):
    if not os.path.exists(fill_file):
        continue
    with open(fill_file, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            eid = row['bfo_event_id']
            cm = card_map.get(eid, {})
            ck = cm.get('card_key', '')
            if not ck:
                continue
            pair = frozenset({normalize(row['fighter1_name']),
                              normalize(row['fighter2_name'])})
            if pair not in bfo_index[ck]:
                bfo_index[ck][pair] = {
                    'f1': row['fighter1_name'],
                    'f2': row['fighter2_name'],
                }

# ── RANK supplement: raw (fallback for events not in devigged) ──
rawpath = os.path.join(base, 'bfo_odds_raw.csv')
with open(rawpath, 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        eid = row['event_bfo_id'].replace('.0', '')
        ck = eid_to_ck.get(eid, row['event_name'])
        pair = frozenset({normalize(row['fighter_name']),
                          normalize(row['opponent_name'])})
        if pair not in bfo_index[ck]:
            bfo_index[ck][pair] = {
                'f1': row['fighter_name'],
                'f2': row['opponent_name'],
            }

# ── RANK supplement: ext cards within rank window (≤ Apr 27) ──
with open('bfo_close_ext_2026.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['event_date'] > '2026-04-27':
            continue
        eid = row['bfo_event_id']
        cm = card_map.get(eid, {})
        ck = cm.get('card_key', '')
        pair = frozenset({normalize(row['fighter1_name']),
                          normalize(row['fighter2_name'])})
        if pair not in bfo_index.get(ck, {}):
            bfo_index[ck][pair] = {
                'f1': row['fighter1_name'],
                'f2': row['fighter2_name'],
            }

# ── TEST: ext from first card after Apr 27 ──
with open('bfo_close_ext_2026.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['event_date'] <= '2026-04-27':
            continue
        eid = row['bfo_event_id']
        cm = card_map.get(eid, {})
        ck = cm.get('card_key', '')
        pair = frozenset({normalize(row['fighter1_name']),
                          normalize(row['fighter2_name'])})
        if pair not in bfo_index[ck]:
            bfo_index[ck][pair] = {
                'f1': row['fighter1_name'],
                'f2': row['fighter2_name'],
            }

print(f'BFO index: {len(bfo_index)} card_keys, '
      f'{sum(len(v) for v in bfo_index.values())} matchups')

# ── Ezoteryka picks ──
ezo_path = (r'C:\Users\micha\OneDrive\Pulpit\ufc_scraper'
            r'\ezoteryka_picks.csv')
ezo_bouts = []
ezo_seen = set()
with open(ezo_path, 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        event = row['event']
        pair = frozenset({normalize(row['fighter_picked']),
                          normalize(row['opponent'])})
        key = (event, pair)
        if key not in ezo_seen:
            ezo_seen.add(key)
            ezo_bouts.append({
                'tap_event': event, 'pair': pair,
                'fighter_picked': row['fighter_picked'],
                'opponent': row['opponent'],
            })

unique_events = sorted(set(b['tap_event'] for b in ezo_bouts))

# ── Event mapping ──
TAP_TO_CK_OVERRIDES = {
    'UFC Freedom 250: Topuria vs. Gaethje': 'UFC Freedom 250',
}

def event_number(name):
    m = re.search(r'ufc\s+(\d{3})', normalize(name))
    return int(m.group(1)) if m else None

all_card_keys = set(bfo_index.keys())
tap_to_ck = {}

for te in unique_events:
    if te in TAP_TO_CK_OVERRIDES:
        tap_to_ck[te] = TAP_TO_CK_OVERRIDES[te]
        continue
    norm_te = normalize(te)
    if te in all_card_keys:
        tap_to_ck[te] = te
        continue
    for ck in all_card_keys:
        if normalize(ck) == norm_te:
            tap_to_ck[te] = ck
            break
    else:
        stripped = re.sub(r'\s+\d+$', '', norm_te)
        for ck in all_card_keys:
            if normalize(ck) == stripped:
                tap_to_ck[te] = ck
                break
        else:
            te_num = event_number(te)
            if te_num:
                for ck in all_card_keys:
                    if event_number(ck) == te_num:
                        tap_to_ck[te] = ck
                        break
            if te not in tap_to_ck:
                m = re.search(r':\s*(.+?)\s+vs\.?\s+(.+?)$', norm_te)
                if m:
                    h1 = m.group(1).split()[-1]
                    h2 = m.group(2).split()[-1]
                    for ck in all_card_keys:
                        nck = normalize(ck)
                        if h1 in nck and h2 in nck:
                            te_n, ck_n = event_number(te), event_number(ck)
                            if te_n and ck_n and te_n != ck_n:
                                continue
                            tap_to_ck[te] = ck
                            break

unmapped = [te for te in unique_events if te not in tap_to_ck]
if unmapped:
    print(f'Unmapped events: {unmapped}')

# ── Join ──
matched = 0
unmatched = 0
issues = Counter()

for b in ezo_bouts:
    te = b['tap_event']
    ck = tap_to_ck.get(te, '')
    pair = b['pair']

    if not ck or ck not in bfo_index:
        issues['missing_BFO_event'] += 1
        unmatched += 1
        continue

    matchups = bfo_index[ck]

    # Exact normalized
    if pair in matchups:
        matched += 1
        continue

    # Token-set
    tap_ts = frozenset({token_set(b['fighter_picked']),
                        token_set(b['opponent'])})
    ts_found = False
    for bp, detail in matchups.items():
        bfo_ts = frozenset({token_set(detail['f1']),
                            token_set(detail['f2'])})
        if tap_ts == bfo_ts:
            matched += 1
            ts_found = True
            break
    if ts_found:
        continue

    # Partial -> classify
    partial = False
    for bp, detail in matchups.items():
        bfo_ts = frozenset({token_set(detail['f1']),
                            token_set(detail['f2'])})
        if pair & bp or tap_ts & bfo_ts:
            issues['spelling'] += 1
            partial = True
            break
    if not partial:
        issues['missing_BFO'] += 1
    unmatched += 1

total = matched + unmatched
print(f'\n=== POC JOIN: rank=devigged+fill, test=ext(post-Apr27) ===')
print(f'Total Ezoteryka bouts:  {total}')
print(f'Matched:                {matched} ({matched/total*100:.1f}%)')
print(f'Unmatched:              {unmatched} ({unmatched/total*100:.1f}%)')
print(f'\nIssue breakdown:')
for issue, count in issues.most_common():
    print(f'  {issue}: {count}')
