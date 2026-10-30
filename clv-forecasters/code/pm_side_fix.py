#!/usr/bin/env python3
"""
Side fix v2: k_last/pm_last tracks fighters_pm[0] (PM's first outcome).
Align p_fair_yes to that fighter via BFO name match.
"""
import csv, json, os, re, sys, unicodedata
import numpy as np
import pandas as pd
from datetime import timedelta

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PM_ROOT = r'C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public'

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
def normalize(name):
    return re.sub(r'[^\w\s]', '', strip_accents(name).strip().lower()).strip()
def last_name(name):
    parts = normalize(name).split()
    return parts[-1] if parts else ''
def names_match(a, b):
    na, nb = normalize(a), normalize(b)
    if na == nb: return True
    la, lb = last_name(a), last_name(b)
    if la == lb and len(na) > 0 and len(nb) > 0 and na[0] == nb[0]: return True
    if len(na) > 4 and len(nb) > 4 and (na in nb or nb in na): return True
    return False

# Load
panel = pd.read_parquet(f'{PM_ROOT}/data/clean/phase2_full_panel.parquet')
panel['bar_utc'] = pd.to_datetime(panel['bar_utc'], utc=True)
cw = pd.read_parquet(f'{PM_ROOT}/data/meta/ufc_crosswalk.parquet')
cw = cw[cw['exclusion_reason'].isna()].copy()
cw['event_date'] = pd.to_datetime(cw['event_date'])
km = pd.read_parquet(f'{PM_ROOT}/data/interim/kxufcfight_2026_markets.parquet')
km['close_time'] = pd.to_datetime(km['close_time'], utc=True)

book_all = []
with open('bfo_close_all.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        book_all.append(r)

outcomes = {}
with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        parts = r['bout'].split(' vs ')
        if len(parts) != 2: continue
        if r['result'] == 'win':
            winner = r['picked_fighter']
        else:
            winner = parts[1] if normalize(r['picked_fighter']) == normalize(parts[0]) else parts[0]
        outcomes[(r['card_key'], normalize(parts[0]), normalize(parts[1]))] = normalize(winner)

cw_filtered = cw[cw['event_date'] >= '2025-08-16'].copy()

# ─── Build fight info: YES fighter = fighters_pm[0] ───
fight_info = {}
no_book = 0
no_anchor = 0

for _, row in cw_filtered.iterrows():
    fid = row['fight_id']
    tickers = json.loads(row['tickers']) if isinstance(row['tickers'], str) else row['tickers']
    fighters_k = json.loads(row['fighters_kalshi']) if isinstance(row['fighters_kalshi'], str) else row['fighters_kalshi']
    fighters_pm = json.loads(row['fighters_pm']) if isinstance(row['fighters_pm'], str) and row['fighters_pm'] else []

    if not tickers or not fighters_k or len(fighters_k) < 2:
        continue

    # YES fighter = fighters_pm[0] (what k_last/pm_last tracks)
    if fighters_pm and len(fighters_pm) >= 2:
        yes_fighter = fighters_pm[0]
        no_fighter = fighters_pm[1]
    else:
        # No PM data; skip
        continue

    # Anchor
    anchor = None
    for t in tickers:
        match = km[km['ticker'] == t]
        if len(match) > 0:
            anchor = match.iloc[0]['close_time'] - timedelta(minutes=60)
            break
    if not anchor:
        no_anchor += 1
        continue

    # Match YES fighter to BFO
    yes_n = normalize(yes_fighter)
    no_n = normalize(no_fighter)
    bfo_match = None
    for bk in book_all:
        bf1 = normalize(bk['fighter1_name'])
        bf2 = normalize(bk['fighter2_name'])
        if (names_match(yes_n, bf1) and names_match(no_n, bf2)):
            bfo_match = {'p_fair_yes': float(bk['p_fair_a']), 'p_fair_no': float(bk['p_fair_b'])}
            break
        elif (names_match(yes_n, bf2) and names_match(no_n, bf1)):
            bfo_match = {'p_fair_yes': float(bk['p_fair_b']), 'p_fair_no': float(bk['p_fair_a'])}
            break
    if not bfo_match:
        no_book += 1
        continue

    # Outcome
    yes_won = None
    for (ck, f1, f2), winner in outcomes.items():
        if (names_match(yes_n, f1) and names_match(no_n, f2)) or \
           (names_match(yes_n, f2) and names_match(no_n, f1)):
            yes_won = names_match(yes_n, winner)
            break

    fight_info[fid] = {
        'yes_fighter': yes_fighter, 'no_fighter': no_fighter,
        'p_fair_yes': bfo_match['p_fair_yes'], 'p_fair_no': bfo_match['p_fair_no'],
        'yes_won': yes_won, 'anchor': anchor,
        'event_date': str(row['event_date'].date()),
    }

print(f"Matched: {len(fight_info)}, no_book: {no_book}, no_anchor: {no_anchor}")

# ─── STEP 2: Sample fights ───
print("\n" + "=" * 90)
print("STEP 2: 10 sample fights (YES = fighters_pm[0])")
print("=" * 90)
print(f"{'fid':<22} {'yes_fighter':<20} {'no_fighter':<20} {'p_fair_yes':>10} {'p_fair_no':>10}")
print("-" * 85)
for fid in list(fight_info.keys())[:10]:
    fi = fight_info[fid]
    print(f"{fid:<22} {fi['yes_fighter'][:19]:<20} {fi['no_fighter'][:19]:<20} "
          f"{fi['p_fair_yes']:>10.4f} {fi['p_fair_no']:>10.4f}")

# ─── STEP 3: Side audit ───
print("\n" + "=" * 90)
print("STEP 3: SIDE AUDIT (price path vs p_fair_yes)")
print("=" * 90)

flagged = []
total_checked = 0
for fid, fi in fight_info.items():
    fp = panel[panel['fight_id'] == fid]
    if len(fp) < 10: continue
    for venue, col in [('kalshi', 'k_last'), ('polymarket', 'pm_last')]:
        prices = fp[col].dropna()
        if len(prices) < 5: continue
        total_checked += 1
        mean_p = prices.mean()
        dist_yes = abs(mean_p - fi['p_fair_yes'])
        dist_no = abs(mean_p - fi['p_fair_no'])
        if dist_no < dist_yes:
            flagged.append({'fid': fid, 'venue': venue, 'mean_p': mean_p,
                            'p_yes': fi['p_fair_yes'], 'p_no': fi['p_fair_no'],
                            'yes_fighter': fi['yes_fighter']})

print(f"Total checked: {total_checked}")
print(f"Flagged (closer to p_no): {len(flagged)} ({len(flagged)/total_checked:.1%})")
if flagged:
    print(f"\n{'fid':<22} {'venue':<10} {'mean_p':>7} {'p_yes':>7} {'p_no':>7} {'yes_fighter':<20}")
    for f in flagged[:5]:
        print(f"{f['fid']:<22} {f['venue']:<10} {f['mean_p']:>7.3f} {f['p_yes']:>7.3f} "
              f"{f['p_no']:>7.3f} {f['yes_fighter'][:19]:<20}")

# ─── STEP 4: −30m gap distribution ───
print("\n" + "=" * 90)
print("STEP 4: -30m GAP (price - p_fair_yes)")
print("=" * 90)

gaps_k = []; gaps_pm = []
sample_rows = []

for fid, fi in fight_info.items():
    fp = panel[panel['fight_id'] == fid]
    if fp.empty: continue
    hz_time = fi['anchor'] - timedelta(hours=0.5)

    for venue, col, gaps_list in [('kalshi', 'k_last', gaps_k), ('polymarket', 'pm_last', gaps_pm)]:
        recent = fp[fp['bar_utc'] <= hz_time].dropna(subset=[col])
        if len(recent) == 0: continue
        last_p = recent[col].iloc[-1]
        gap = last_p - fi['p_fair_yes']
        gaps_list.append(gap)
        if venue == 'kalshi' and len(sample_rows) < 10:
            sample_rows.append({
                'fid': fid, 'yes': fi['yes_fighter'], 'k_last': last_p,
                'p_fair_yes': fi['p_fair_yes'], 'gap': gap,
            })

for label, gaps in [('Kalshi', np.array(gaps_k)), ('Polymarket', np.array(gaps_pm))]:
    print(f"\n  {label} (n={len(gaps)}):")
    print(f"    mean={gaps.mean():+.4f}, median={np.median(gaps):+.4f}, SD={gaps.std():.4f}")
    print(f"    |gap| > 2c:  {(np.abs(gaps) > 0.02).sum()}/{len(gaps)} ({(np.abs(gaps) > 0.02).mean():.1%})")
    print(f"    |gap| > 5c:  {(np.abs(gaps) > 0.05).sum()}/{len(gaps)} ({(np.abs(gaps) > 0.05).mean():.1%})")
    print(f"    |gap| > 10c: {(np.abs(gaps) > 0.10).sum()}/{len(gaps)} ({(np.abs(gaps) > 0.10).mean():.1%})")

    bins = np.arange(-0.15, 0.16, 0.01)
    hist, _ = np.histogram(gaps, bins=bins)
    print(f"    Histogram (1c bins):")
    for i, h in enumerate(hist):
        if h > 0:
            bar = '#' * min(h * 2, 80)
            print(f"      [{bins[i]:+.2f},{bins[i+1]:+.2f}) {h:>3} {bar}")

    # Out of range
    out_lo = (gaps < -0.15).sum()
    out_hi = (gaps > 0.15).sum()
    if out_lo or out_hi:
        print(f"    Out of range: {out_lo} below -15c, {out_hi} above +15c")

print(f"\n  Sample (Kalshi −30m):")
print(f"  {'fid':<22} {'yes_fighter':<20} {'K_last':>7} {'p_fair_yes':>10} {'gap':>7}")
for s in sample_rows:
    print(f"  {s['fid']:<22} {s['yes'][:19]:<20} {s['k_last']:>7.4f} {s['p_fair_yes']:>10.4f} {s['gap']:>+7.4f}")
