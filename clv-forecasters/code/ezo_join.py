#!/usr/bin/env python3
"""Join BFO odds to Ezoteryka POC picks on card_key + normalised fighter pair."""

import csv, unicodedata, re, os
from collections import defaultdict, Counter

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Characters that NFKD decomposition doesn't handle
_CHAR_MAP = str.maketrans({
    '\u0142': 'l',   # ł
    '\u0141': 'L',   # Ł
    '\u00f8': 'o',   # ø
    '\u00d8': 'O',   # Ø
    '\u0111': 'd',   # đ
    '\u0110': 'D',   # Đ
    '\u00df': 'ss',  # ß
    '\u2019': '',    # ' (right single quote)
    "'": '',          # apostrophe
    '-': ' ',         # hyphen -> space (Saint-Denis = Saint Denis)
})

def normalize(name):
    """Strip accents, map special chars, lowercase, remove suffixes."""
    name = name.translate(_CHAR_MAP)
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower().strip()
    name = re.sub(r'\s+(jr|sr|ii|iii|iv)\.?$', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name

def token_set(name):
    """Sorted token set for order-independent matching (Wang Cong = Cong Wang)."""
    return frozenset(normalize(name).split())


# ── Load card_map ──
card_map = {}
with open('card_map.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        card_map[row['bfo_event_id']] = row

# ── Config ──
INCLUDE_MANUAL = True  # include bfo_close_manual.csv entries

# ── Load BFO ext + fill + rank + manual matchups ──
close_files = ['bfo_close_ext_2026.csv', 'bfo_close_fill_2025.csv', 'bfo_close_rank.csv']
if INCLUDE_MANUAL:
    close_files.append('bfo_close_manual.csv')
    print('include_manual=True: loading bfo_close_manual.csv')

bfo_ext = []
for close_file in close_files:
    if not os.path.exists(close_file):
        continue
    with open(close_file, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            eid = row['bfo_event_id']
            cm = card_map.get(eid, {})
            ck = cm.get('card_key', '')
            pair = frozenset({normalize(row['fighter1_name']), normalize(row['fighter2_name'])})
            bfo_ext.append({
                'card_key': ck, 'pair': pair, 'source': 'ext',
                'f1': row['fighter1_name'], 'f2': row['fighter2_name'],
                'bfo_event_id': eid,
            })

# Also load 4107 (Step 4) matchups from bfo_odds_ext_2026.csv directly
from statistics import median as _median
_4107_matchups = defaultdict(lambda: {'f1': {}, 'f2': {}, 'meta': {}})
with open('bfo_odds_ext_2026.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['bfo_event_id'] != '4107':
            continue
        mid = row['bfo_matchup_id']
        side = row['fighter_side']
        key = 'f1' if side == '1' else 'f2'
        if int(row['is_book']) == 1:
            _4107_matchups[mid][key][row['book']] = int(row['odds_american'])
        _4107_matchups[mid]['meta'][f'f{side}_name'] = row['fighter_name']

for mid, data in _4107_matchups.items():
    f1 = data['meta'].get('f1_name', '')
    f2 = data['meta'].get('f2_name', '')
    if f1 and f2:
        pair = frozenset({normalize(f1), normalize(f2)})
        bfo_ext.append({
            'card_key': 'UFC Fight Night: Moicano vs. Duncan',
            'pair': pair, 'source': 'ext',
            'f1': f1, 'f2': f2, 'bfo_event_id': '4107',
        })

# ── Load BFO raw matchups ──
# Build reverse card_map: bfo_event_id -> card_key
eid_to_ck = {row['bfo_event_id']: row['card_key'] for row in card_map.values()}

rawpath = (r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers'
           r'\UFC Post-KO Analysis\bfo_odds_final\bfo_odds_raw.csv')
bfo_raw_detail = []
seen_raw = set()
with open(rawpath, 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        fighter = row['fighter_name']
        opponent = row['opponent_name']
        eid = row['event_bfo_id'].replace('.0', '')
        # Use card_map card_key if available, else fall back to BFO event name
        ck = eid_to_ck.get(eid, row['event_name'])
        pair = frozenset({normalize(fighter), normalize(opponent)})
        key = (ck, pair)
        if key not in seen_raw:
            seen_raw.add(key)
            bfo_raw_detail.append({
                'card_key': ck, 'pair': pair, 'source': 'raw',
                'f1': fighter, 'f2': opponent,
                'bfo_event_id': eid,
            })

# ── Load name overrides (bfo_name -> tapology_name) ──
overrides_aliases = defaultdict(set)  # normalize(name) -> set of all known aliases
if os.path.exists('name_overrides.csv'):
    with open('name_overrides.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['bfo_name'] and row['tapology_name']:
                nb = normalize(row['bfo_name'])
                nt = normalize(row['tapology_name'])
                overrides_aliases[nb].add(nt)
                overrides_aliases[nt].add(nb)
    # Transitive closure: if A->B and A->C, then B->C
    changed = True
    while changed:
        changed = False
        for name, aliases in list(overrides_aliases.items()):
            expanded = set(aliases)
            for a in aliases:
                expanded |= overrides_aliases.get(a, set())
            expanded.discard(name)
            if expanded != aliases:
                overrides_aliases[name] = expanded
                changed = True

def apply_overrides_to_pair(pair):
    """Apply name overrides to a normalized pair, returning expanded set of pairs to try."""
    pairs = {pair}
    # For each name in pair, collect all aliases
    name_variants = []
    for name in pair:
        variants = {name} | overrides_aliases.get(name, set())
        name_variants.append(variants)
    # Generate all combinations
    if len(name_variants) == 2:
        for v1 in name_variants[0]:
            for v2 in name_variants[1]:
                pairs.add(frozenset({v1, v2}))
    return pairs

# ── Build BFO index: card_key -> {normalised_pair: detail} ──
bfo_index = defaultdict(dict)
for entry in bfo_ext:
    bfo_index[entry['card_key']][entry['pair']] = entry
for entry in bfo_raw_detail:
    ck = entry['card_key']
    if entry['pair'] not in bfo_index.get(ck, {}):
        bfo_index[ck][entry['pair']] = entry

print(f'BFO index: {len(bfo_index)} card_keys, '
      f'{sum(len(v) for v in bfo_index.values())} matchups')
print(f'Name overrides loaded: {len(overrides_aliases)} names with aliases')

# ── Load Ezoteryka picks ──
ezo_bouts = []
ezo_seen = set()
ezo_path = (r'C:\Users\micha\OneDrive\Pulpit\ufc_scraper\ezoteryka_picks.csv')
with open(ezo_path, 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        event = row['event']
        pair = frozenset({normalize(row['fighter_picked']),
                          normalize(row['opponent'])})
        key = (event, pair)
        if key not in ezo_seen:
            ezo_seen.add(key)
            ezo_bouts.append({
                'tap_event': event,
                'pair': pair,
                'fighter_picked': row['fighter_picked'],
                'opponent': row['opponent'],
                'actual_winner': row['actual_winner'],
                'correct': row['correct'],
            })

unique_events = sorted(set(b['tap_event'] for b in ezo_bouts))
print(f'Ezoteryka bouts: {len(ezo_bouts)} across {len(unique_events)} events')

# ── Map Tapology event names -> BFO card_keys ──
# Tapology names like "UFC Fight Night: Kape vs. Horiguchi 2"
# BFO card_keys like "UFC Fight Night: Kape vs. Horiguchi"
# Differences: trailing numbers, accent marks, minor spelling

tap_to_ck = {}
all_card_keys = set(bfo_index.keys())

# Hard-coded overrides for known naming mismatches
TAP_TO_CK_OVERRIDES = {
    'UFC Freedom 250: Topuria vs. Gaethje': 'UFC Freedom 250',
}

def event_number(name):
    """Extract UFC event number if present: 'UFC 330' -> 330, else None."""
    m = re.search(r'ufc\s+(\d{3})', normalize(name))
    return int(m.group(1)) if m else None

for te in unique_events:
    # 0. Hard-coded overrides
    if te in TAP_TO_CK_OVERRIDES:
        tap_to_ck[te] = TAP_TO_CK_OVERRIDES[te]
        continue
    norm_te = normalize(te)
    # 1. Exact match
    if te in all_card_keys:
        tap_to_ck[te] = te
        continue
    # 2. Normalised exact
    for ck in all_card_keys:
        if normalize(ck) == norm_te:
            tap_to_ck[te] = ck
            break
    else:
        # 3. Trailing " 2"/" 3" stripped (Tapology appends rematch numbers)
        stripped = re.sub(r'\s+\d+$', '', norm_te)
        for ck in all_card_keys:
            if normalize(ck) == stripped:
                tap_to_ck[te] = ck
                break
        else:
            # 4. Numbered UFC cards: raw uses "UFC 319 Odds" or "UFC 319"
            te_num = event_number(te)
            if te_num:
                for ck in all_card_keys:
                    ck_num = event_number(ck)
                    if ck_num == te_num:
                        tap_to_ck[te] = ck
                        break
            if te not in tap_to_ck:
                # 5. Fight Night: match on BOTH headliner last names
                m = re.search(r':\s*(.+?)\s+vs\.?\s+(.+?)$', norm_te)
                if m:
                    h1 = m.group(1).split()[-1]
                    h2 = m.group(2).split()[-1]
                    for ck in all_card_keys:
                        nck = normalize(ck)
                        # Both last names must appear, and must be a Fight Night
                        if h1 in nck and h2 in nck:
                            # Guard: numbered events must match numbers
                            te_n = event_number(te)
                            ck_n = event_number(ck)
                            if te_n and ck_n and te_n != ck_n:
                                continue
                            tap_to_ck[te] = ck
                            break

print('\n=== Event mapping ===')
for te in unique_events:
    ck = tap_to_ck.get(te, 'UNMAPPED')
    n_bfo = len(bfo_index.get(ck, {})) if ck != 'UNMAPPED' else 0
    flag = ' ***' if ck == 'UNMAPPED' else ''
    print(f'  {te:55s} -> {ck[:55]:55s} ({n_bfo:>3} BFO){flag}')

# ── Join ──
matched = 0
unmatched = 0
join_log = []

for b in ezo_bouts:
    te = b['tap_event']
    ck = tap_to_ck.get(te, '')
    pair = b['pair']

    if not ck or ck not in bfo_index:
        join_log.append({
            'tap_event': te, 'card_key': ck or '?',
            'tap_fighter_a': b['fighter_picked'], 'tap_fighter_b': b['opponent'],
            'issue': 'missing_BFO_event',
            'bfo_fighter_a': '', 'bfo_fighter_b': '',
        })
        unmatched += 1
        continue

    bfo_matchups = bfo_index[ck]

    # Try exact normalized pair (+ overrides)
    all_pairs = apply_overrides_to_pair(pair)
    if any(p in bfo_matchups for p in all_pairs):
        matched += 1
        continue

    # Try token-set matching (handles name-order differences)
    tap_ts = frozenset({token_set(b['fighter_picked']), token_set(b['opponent'])})
    # Also build override-expanded token sets
    tap_ts_variants = {tap_ts}
    for p in all_pairs:
        tap_ts_variants.add(frozenset({frozenset(n.split()) for n in p}))

    ts_match = None
    for bp, detail in bfo_matchups.items():
        bfo_ts = frozenset({token_set(detail['f1']), token_set(detail['f2'])})
        if any(bfo_ts == tv for tv in tap_ts_variants):
            ts_match = detail
            break

    if ts_match:
        matched += 1
        continue

    # Partial match: check if one fighter appears (normalized or token-set or override)
    partial = []
    all_names = set()
    for p in all_pairs:
        all_names.update(p)
    for bp, detail in bfo_matchups.items():
        overlap = all_names & bp
        if not overlap:
            bfo_ts = frozenset({token_set(detail['f1']), token_set(detail['f2'])})
            for tv in tap_ts_variants:
                ts_overlap = tv & bfo_ts
                if ts_overlap:
                    overlap = ts_overlap
                    break
        if overlap:
            partial.append((len(overlap), bp, detail))

    if partial:
        partial.sort(reverse=True)
        best = partial[0]
        bfo_d = best[2]
        # Classify
        if best[0] == 1:
            issue = 'spelling'  # one fighter matched
        else:
            issue = 'replacement_opponent'
        join_log.append({
            'tap_event': te, 'card_key': ck,
            'tap_fighter_a': b['fighter_picked'], 'tap_fighter_b': b['opponent'],
            'issue': issue,
            'bfo_fighter_a': bfo_d['f1'], 'bfo_fighter_b': bfo_d['f2'],
        })
    else:
        join_log.append({
            'tap_event': te, 'card_key': ck,
            'tap_fighter_a': b['fighter_picked'], 'tap_fighter_b': b['opponent'],
            'issue': 'missing_BFO',
            'bfo_fighter_a': '', 'bfo_fighter_b': '',
        })
    unmatched += 1

total = matched + unmatched
print(f'\n=== JOIN RESULTS ===')
print(f'Total Ezoteryka bouts:  {total}')
print(f'Matched (exact):        {matched} ({matched/total*100:.1f}%)')
print(f'Unmatched:              {unmatched} ({unmatched/total*100:.1f}%)')

# Write join log
log_fields = ['tap_event', 'card_key', 'tap_fighter_a', 'tap_fighter_b',
              'issue', 'bfo_fighter_a', 'bfo_fighter_b']
with open('bout_join_log.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=log_fields)
    w.writeheader()
    w.writerows(join_log)
print(f'Wrote bout_join_log.csv: {len(join_log)} entries')

issues = Counter(j['issue'] for j in join_log)
print(f'\nIssue breakdown:')
for issue, count in issues.most_common():
    print(f'  {issue}: {count}')

print('\n=== ALL UNMATCHED ===')
for j in join_log:
    bfo = f'{j["bfo_fighter_a"]} vs {j["bfo_fighter_b"]}' if j['bfo_fighter_a'] else '-'
    print(f'  [{j["issue"]:20s}] {j["tap_event"][:45]:45s} | '
          f'{j["tap_fighter_a"]:22s} vs {j["tap_fighter_b"]:22s} | BFO: {bfo}')

# ── Append NEW candidates to name_overrides.csv (don't overwrite existing) ──
existing_pairs = set()
if os.path.exists('name_overrides.csv'):
    with open('name_overrides.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            existing_pairs.add((row['bfo_name'], row['tapology_name']))

new_overrides = []
for j in join_log:
    if j['issue'] == 'spelling' and j['bfo_fighter_a']:
        tap_pair = frozenset({normalize(j['tap_fighter_a']),
                              normalize(j['tap_fighter_b'])})
        bfo_pair = frozenset({normalize(j['bfo_fighter_a']),
                              normalize(j['bfo_fighter_b'])})
        tap_only = tap_pair - bfo_pair
        bfo_only = bfo_pair - tap_pair
        if len(tap_only) == 1 and len(bfo_only) == 1:
            bfo_n = list(bfo_only)[0]
            tap_n = list(tap_only)[0]
            if (bfo_n, tap_n) not in existing_pairs:
                new_overrides.append({
                    'bfo_name': bfo_n,
                    'tapology_name': tap_n,
                    'note': f'auto-detected from {j["tap_event"][:30]}',
                })
                existing_pairs.add((bfo_n, tap_n))

if new_overrides:
    with open('name_overrides.csv', 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['bfo_name', 'tapology_name', 'note'])
        w.writerows(new_overrides)
    print(f'\nAppended {len(new_overrides)} new overrides to name_overrides.csv')
    for o in new_overrides:
        print(f'  BFO: {o["bfo_name"]:25s} <- Tap: {o["tapology_name"]:25s}')
else:
    print(f'\nNo new override candidates.')
