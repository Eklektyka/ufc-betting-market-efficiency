#!/usr/bin/env python3
"""Steps 3, 5, 6: Derive consensus odds, join to UFCStats, coverage report."""

import csv, re, os, math, unicodedata
from collections import defaultdict
from statistics import median

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── Step 3: Derived table ───────────────────────────────────────────────

def american_to_decimal(american):
    """Convert American odds to decimal odds."""
    a = int(american)
    if a > 0:
        return 1 + a / 100
    else:
        return 1 + 100 / abs(a)

def decimal_to_american(decimal_odds):
    """Convert decimal odds to American odds."""
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1) * 100)
    else:
        return round(-100 / (decimal_odds - 1))

def implied_prob(american):
    d = american_to_decimal(american)
    return 1 / d

def devig_multiplicative(p1, p2):
    """Multiplicative de-vig: scale each implied prob so they sum to 1."""
    total = p1 + p2
    return p1 / total, p2 / total

print("=== STEP 3: Deriving consensus odds ===")

# Load scraped odds (exclude Step 4 event 4107)
odds_by_matchup = defaultdict(lambda: {'f1': {}, 'f2': {}, 'meta': {}})
with open('bfo_odds_ext_2026.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['bfo_event_id'] == '4107':
            continue
        mid = row['bfo_matchup_id']
        side = row['fighter_side']
        key = 'f1' if side == '1' else 'f2'
        odds_by_matchup[mid][key][row['book']] = int(row['odds_american'])
        odds_by_matchup[mid]['meta'] = {
            'bfo_event_id': row['bfo_event_id'],
            'event_name': row['event_name'],
            'event_date': row['event_date'],
            'bfo_matchup_id': mid,
            'f1_name': row['fighter_name'] if side == '1' else odds_by_matchup[mid]['meta'].get('f1_name', ''),
            'f2_name': row['fighter_name'] if side == '2' else odds_by_matchup[mid]['meta'].get('f2_name', ''),
            'f1_slug': row['fighter_slug'] if side == '1' else odds_by_matchup[mid]['meta'].get('f1_slug', ''),
            'f2_slug': row['fighter_slug'] if side == '2' else odds_by_matchup[mid]['meta'].get('f2_slug', ''),
        }

# Build derived table
derived_rows = []
for mid, data in odds_by_matchup.items():
    meta = data['meta']
    f1_books = {b: o for b, o in data['f1'].items() if b not in ('Polymarket', 'Kalshi')}
    f2_books = {b: o for b, o in data['f2'].items() if b not in ('Polymarket', 'Kalshi')}

    if not f1_books or not f2_books:
        continue

    # Consensus = median across is_book=1 (sportsbooks only)
    f1_med = median(f1_books.values())
    f2_med = median(f2_books.values())

    # Implied probs from consensus
    f1_ip = implied_prob(f1_med)
    f2_ip = implied_prob(f2_med)

    # De-vig (multiplicative)
    f1_dv, f2_dv = devig_multiplicative(f1_ip, f2_ip)

    # Best line per side (most favorable to bettor)
    f1_best = max(f1_books.values())  # highest positive or least negative
    f2_best = max(f2_books.values())

    derived_rows.append({
        'bfo_event_id': meta['bfo_event_id'],
        'event_name': meta['event_name'],
        'event_date': meta['event_date'],
        'bfo_matchup_id': mid,
        'fighter1_name': meta.get('f1_name', ''),
        'fighter1_slug': meta.get('f1_slug', ''),
        'fighter2_name': meta.get('f2_name', ''),
        'fighter2_slug': meta.get('f2_slug', ''),
        'f1_consensus_american': round(f1_med),
        'f2_consensus_american': round(f2_med),
        'f1_implied_prob': round(f1_ip, 4),
        'f2_implied_prob': round(f2_ip, 4),
        'f1_devigged_prob': round(f1_dv, 4),
        'f2_devigged_prob': round(f2_dv, 4),
        'f1_best_line': f1_best,
        'f2_best_line': f2_best,
        'n_books': len(f1_books),
    })

derived_rows.sort(key=lambda r: (r['event_date'], r['bfo_matchup_id']))

with open('bfo_close_ext_2026.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(derived_rows[0].keys()))
    w.writeheader()
    w.writerows(derived_rows)

print(f"  Wrote bfo_close_ext_2026.csv: {len(derived_rows)} matchups")


# ── Step 5: Join to UFCStats ────────────────────────────────────────────

print("\n=== STEP 5: Joining to UFCStats ===")

def normalize_name(name):
    """Strip accents, lowercase, remove suffixes."""
    # NFKD decomposition to strip accents
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [' jr', ' jr.', ' sr', ' sr.', ' ii', ' iii', ' iv']:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    return name

def last_name(name):
    parts = name.strip().split()
    return parts[-1].lower() if parts else ''

# Load UFCStats bouts
ufcpath = r'C:\Users\micha\OneDrive\Pulpit\Research for Academic Papers\UFC Post-KO Analysis\ufcstats_raw\fight_totals_clean.csv'
ufcstats_bouts = {}  # {(event_name, fight_url): {fighter, opponent, result, ...}}
ufcstats_events = defaultdict(set)  # {event_name: set of fight_urls}

with open(ufcpath, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        fight_url = row['fight_url']
        event = row['event_name']
        fighter = row['fighter']

        key = (event, fight_url, fighter)
        ufcstats_bouts[key] = row
        ufcstats_events[event].add(fight_url)

# Build UFCStats name index: normalized_name -> [(event, fight_url, fighter_name)]
ufc_name_idx = defaultdict(list)
for (event, furl, fighter), row in ufcstats_bouts.items():
    norm = normalize_name(fighter)
    ufc_name_idx[norm].append((event, furl, fighter))

# Load card_map for event mapping
card_map = {}
with open('card_map.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        card_map[row['bfo_event_id']] = row

# Load name overrides
overrides = {}
if os.path.exists('name_overrides.csv'):
    with open('name_overrides.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['bfo_name'] and row['ufcstats_name']:
                overrides[normalize_name(row['bfo_name'])] = row['ufcstats_name']

# Match derived matchups to UFCStats
join_log = []
matched = 0
unmatched = 0

for drow in derived_rows:
    eid = drow['bfo_event_id']
    cm = card_map.get(eid, {})
    card_key = cm.get('card_key', '')

    for side in ['1', '2']:
        bfo_name = drow[f'fighter{side}_name']
        norm_bfo = normalize_name(bfo_name)

        # Check override first
        if norm_bfo in overrides:
            norm_bfo = normalize_name(overrides[norm_bfo])

        # Exact normalized match
        candidates = ufc_name_idx.get(norm_bfo, [])

        # Filter to matching card_key
        card_matches = [c for c in candidates if c[0] == card_key]

        if len(card_matches) == 1:
            matched += 1
        elif len(card_matches) == 0:
            # Try broader: any event
            if candidates:
                join_log.append({
                    'bfo_event_id': eid,
                    'bfo_name': bfo_name,
                    'normalized': norm_bfo,
                    'card_key': card_key,
                    'issue': 'name_found_wrong_event',
                    'candidates': '; '.join(f'{c[0]}' for c in candidates[:3]),
                })
            else:
                join_log.append({
                    'bfo_event_id': eid,
                    'bfo_name': bfo_name,
                    'normalized': norm_bfo,
                    'card_key': card_key,
                    'issue': 'no_match',
                    'candidates': '',
                })
            unmatched += 1
        else:
            # Multiple matches in same event (shouldn't happen for moneylines)
            join_log.append({
                'bfo_event_id': eid,
                'bfo_name': bfo_name,
                'normalized': norm_bfo,
                'card_key': card_key,
                'issue': 'multi_match',
                'candidates': '; '.join(f'{c[2]}' for c in card_matches),
            })
            matched += 1  # still usable

print(f"  Matched: {matched}, Unmatched: {unmatched}")

# Write join log
with open('name_join_log.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['bfo_event_id', 'bfo_name', 'normalized', 'card_key', 'issue', 'candidates'])
    w.writeheader()
    w.writerows(join_log)
print(f"  Wrote name_join_log.csv: {len(join_log)} issues")


# ── Step 6: Coverage report ─────────────────────────────────────────────

print("\n=== STEP 6: Coverage report ===")

# Load card_map for canonical grouping
event_cards = defaultdict(list)  # card_key -> list of bfo_event_ids
for eid, cm in card_map.items():
    if eid == '4107':
        continue
    event_cards[cm['card_key']].append(eid)

# Count bouts in UFCStats per card_key
ufcstats_bout_count = {}
for event_name, fight_urls in ufcstats_events.items():
    ufcstats_bout_count[event_name] = len(fight_urls)

# Count bouts in BFO per card_key
bfo_bout_count = defaultdict(lambda: {'total': 0, 'ge1_book': 0, 'ge3_books': 0, 'matchups': set()})
for drow in derived_rows:
    eid = drow['bfo_event_id']
    cm = card_map.get(eid, {})
    ck = cm.get('card_key', drow['event_name'])
    n = drow['n_books']
    mid = drow['bfo_matchup_id']
    if mid not in bfo_bout_count[ck]['matchups']:
        bfo_bout_count[ck]['matchups'].add(mid)
        bfo_bout_count[ck]['total'] += 1
        if n >= 1:
            bfo_bout_count[ck]['ge1_book'] += 1
        if n >= 3:
            bfo_bout_count[ck]['ge3_books'] += 1

# Write coverage report
lines = ["# BFO Odds Extension Coverage Report\n"]
lines.append(f"Generated: 2026-08-20\n")
lines.append(f"Coverage window: 2026-04-18 to 2026-08-15\n\n")
lines.append("| Card | Canonical Date | UFCStats Bouts | BFO Matchups (>=1 book) | BFO Matchups (>=3 books) | Missing |\n")
lines.append("|------|---------------|----------------|------------------------|------------------------|---------|\n")

cards_sorted = sorted(event_cards.keys(), key=lambda ck: card_map[event_cards[ck][0]]['canonical_date'])

total_ufc = 0
total_bfo1 = 0
total_bfo3 = 0
missing_bouts = []

for ck in cards_sorted:
    eids = event_cards[ck]
    cdate = card_map[eids[0]]['canonical_date']

    ufc_n = ufcstats_bout_count.get(ck, 0)
    bfo = bfo_bout_count.get(ck, {'ge1_book': 0, 'ge3_books': 0})

    # Find missing fighters (in UFCStats but not matched in BFO)
    miss = ''
    if ufc_n > 0 and bfo['ge1_book'] < ufc_n:
        miss = f"{ufc_n - bfo['ge1_book']} missing"
    elif ufc_n == 0:
        miss = 'no UFCStats data'

    total_ufc += ufc_n
    total_bfo1 += bfo['ge1_book']
    total_bfo3 += bfo['ge3_books']

    lines.append(f"| {ck[:45]} | {cdate} | {ufc_n} | {bfo['ge1_book']} | {bfo['ge3_books']} | {miss} |\n")

    if miss and ufc_n > 0:
        missing_bouts.append((ck, cdate, ufc_n, bfo['ge1_book']))

lines.append(f"\n**Totals**: {total_ufc} UFCStats bouts, {total_bfo1} BFO matchups (>=1 book), {total_bfo3} (>=3 books)\n\n")

lines.append("## Notes\n\n")
lines.append("- UFCStats coverage ends ~June 27, 2026. Events after that date show 0 UFCStats bouts and need UFCStats extension.\n")
lines.append("- BFO event_date is UTC-based and unreliable for split cards; canonical_date from card_map.csv is authoritative.\n")
lines.append("- BFO matchup count may exceed UFCStats bout count due to cancelled/replaced bouts kept as separate entries.\n")
lines.append("- Burns-Malott (4130) overlaps with bfo_odds_raw.csv — convention check confirms identical closing lines.\n")
lines.append(f"- Books with data: FanDuel, Caesars, BetRivers, BetWay, Unibet (sportsbooks); Polymarket, Kalshi (prediction markets).\n")
lines.append(f"- BetMGM and DraftKings columns exist but have no odds for any event in this window.\n")

if missing_bouts:
    lines.append("\n## Missing Bouts Detail\n\n")
    for ck, cdate, ufc_n, bfo_n in missing_bouts:
        lines.append(f"- **{ck}** ({cdate}): {ufc_n} UFCStats bouts vs {bfo_n} BFO matchups\n")

with open('coverage_report.md', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("  Wrote coverage_report.md")
print(f"  Summary: {total_ufc} UFCStats bouts, {total_bfo1} BFO (>=1), {total_bfo3} BFO (>=3)")
