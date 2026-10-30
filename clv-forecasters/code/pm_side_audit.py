#!/usr/bin/env python3
"""Side audit: verify PM/K price maps to the correct fighter before any ROI."""
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

book = {}
with open('bfo_close_all.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        book[(r['bfo_event_id'], r['bfo_matchup_id'])] = {
            'f1': r['fighter1_name'], 'f2': r['fighter2_name'],
            'p_fair_a': float(r['p_fair_a']), 'p_fair_b': float(r['p_fair_b']),
        }

cw_filtered = cw[cw['event_date'] >= '2025-08-16'].copy()

# Build fight info
fight_info = {}
for _, row in cw_filtered.iterrows():
    fid = row['fight_id']
    tickers = json.loads(row['tickers']) if isinstance(row['tickers'], str) else row['tickers']
    fighters_k = json.loads(row['fighters_kalshi']) if isinstance(row['fighters_kalshi'], str) else row['fighters_kalshi']
    pm_slug = row['pm_slug'] if pd.notna(row['pm_slug']) else ''
    fighters_pm = json.loads(row['fighters_pm']) if isinstance(row['fighters_pm'], str) and row['fighters_pm'] else []

    if not tickers or not fighters_k or len(fighters_k) < 2:
        continue

    anchor = None
    for t in tickers:
        match = km[km['ticker'] == t]
        if len(match) > 0:
            anchor = match.iloc[0]['close_time'] - timedelta(minutes=60)
            break
    if not anchor:
        continue

    fa_n = normalize(fighters_k[0])
    fb_n = normalize(fighters_k[1])
    book_match = None
    for (eid, mid), bk in book.items():
        bf1 = normalize(bk['f1'])
        bf2 = normalize(bk['f2'])
        if (names_match(fa_n, bf1) and names_match(fb_n, bf2)) or \
           (names_match(fa_n, bf2) and names_match(fb_n, bf1)):
            if names_match(fa_n, bf1):
                book_match = {'p_fair_a': bk['p_fair_a'], 'p_fair_b': bk['p_fair_b']}
            else:
                book_match = {'p_fair_a': bk['p_fair_b'], 'p_fair_b': bk['p_fair_a']}
            break
    if not book_match:
        continue

    # The panel tracks fighter_a (first in crosswalk) as the "Yes" side
    # k_last and pm_last are the price for fighter_a winning
    # Ticker suffix confirms: KXUFCFIGHT-26JUL11BASGAR-BAS means BAS (Basharat) is Yes
    # But the panel normalises to fight_id level where fighter order = crosswalk order

    ticker_suffix = tickers[0].split('-')[-1] if tickers else '?'
    # Which fighter does the ticker suffix refer to?
    suffix_lower = ticker_suffix.lower()
    # Match suffix to fighter last names
    fa_last = last_name(fighters_k[0])
    fb_last = last_name(fighters_k[1])
    ticker_is_a = suffix_lower[:3] == fa_last[:3] if len(fa_last) >= 3 and len(suffix_lower) >= 3 else False
    ticker_is_b = suffix_lower[:3] == fb_last[:3] if len(fb_last) >= 3 and len(suffix_lower) >= 3 else False

    fight_info[fid] = {
        'fighters_k': fighters_k, 'tickers': tickers,
        'ticker_suffix': ticker_suffix,
        'ticker_is_a': ticker_is_a, 'ticker_is_b': ticker_is_b,
        'pm_slug': pm_slug, 'fighters_pm': fighters_pm,
        'anchor': anchor,
        'p_fair_a': book_match['p_fair_a'],
        'p_fair_b': book_match['p_fair_b'],
    }

print(f"Fights with full info: {len(fight_info)}")

# ─── CHECK 2: 5 fights side by side ───
print("\n" + "=" * 100)
print("CHECK 2: SIDE MAPPING — 5 fights")
print("=" * 100)
hdr = f"{'fight_id':<22} {'K_a (Yes?)':<18} {'K_b':<18} {'suffix':<8} {'sfx->a?':<7} {'sfx->b?':<7} {'PM_slug':<28} {'p_fair_a':>8} {'p_fair_b':>8}"
print(hdr)
print("-" * len(hdr))
for fid in list(fight_info.keys())[:5]:
    fi = fight_info[fid]
    print(f"{fid:<22} {fi['fighters_k'][0][:17]:<18} {fi['fighters_k'][1][:17]:<18} "
          f"{fi['ticker_suffix']:<8} {'YES' if fi['ticker_is_a'] else 'no':<7} "
          f"{'YES' if fi['ticker_is_b'] else 'no':<7} {fi['pm_slug'][:27]:<28} "
          f"{fi['p_fair_a']:>8.4f} {fi['p_fair_b']:>8.4f}")

# ─── Get −30m prices ───
gaps_k = []
gaps_pm = []
side_wrong_k = 0
side_wrong_pm = 0
total_k = 0
total_pm = 0
details = []

for fid, fi in fight_info.items():
    fp = panel[panel['fight_id'] == fid]
    if fp.empty:
        continue

    hz_time = fi['anchor'] - timedelta(hours=0.5)
    recent_k = fp[fp['bar_utc'] <= hz_time].dropna(subset=['k_last'])
    recent_pm = fp[fp['bar_utc'] <= hz_time].dropna(subset=['pm_last'])

    k_last = recent_k['k_last'].iloc[-1] if len(recent_k) > 0 else np.nan
    pm_last = recent_pm['pm_last'].iloc[-1] if len(recent_pm) > 0 else np.nan

    if not np.isnan(k_last):
        total_k += 1
        gap = k_last - fi['p_fair_a']
        gaps_k.append(gap)
        if abs(k_last - fi['p_fair_b']) < abs(k_last - fi['p_fair_a']):
            side_wrong_k += 1

    if not np.isnan(pm_last):
        total_pm += 1
        gap = pm_last - fi['p_fair_a']
        gaps_pm.append(gap)
        if abs(pm_last - fi['p_fair_b']) < abs(pm_last - fi['p_fair_a']):
            side_wrong_pm += 1

    details.append({
        'fid': fid, 'k_last': k_last, 'pm_last': pm_last,
        'p_fair_a': fi['p_fair_a'], 'p_fair_b': fi['p_fair_b'],
        'ticker': fi['tickers'][0] if fi['tickers'] else '',
        'slug': fi['pm_slug'],
        'fighter_a': fi['fighters_k'][0], 'fighter_b': fi['fighters_k'][1],
    })

# ─── CHECK 2b: Print 10 fights with prices ───
print("\n" + "=" * 100)
print("CHECK 2b: PM/K last prices at -30m vs p_fair")
print("=" * 100)
hdr2 = f"{'fight_id':<22} {'fighter_a':<18} {'K_last':>7} {'PM_last':>7} {'p_fair_a':>8} {'p_fair_b':>8} {'K_closer_to':>12}"
print(hdr2)
print("-" * len(hdr2))
for d in details[:10]:
    if np.isnan(d['k_last']) and np.isnan(d['pm_last']):
        continue
    k_closer = 'a' if not np.isnan(d['k_last']) and abs(d['k_last'] - d['p_fair_a']) < abs(d['k_last'] - d['p_fair_b']) else 'B(!)'
    if np.isnan(d['k_last']):
        k_closer = '?'
    print(f"{d['fid']:<22} {d['fighter_a'][:17]:<18} {d['k_last']:>7.4f} {d['pm_last']:>7.4f} "
          f"{d['p_fair_a']:>8.4f} {d['p_fair_b']:>8.4f} {k_closer:>12}")

# ─── CHECK 1: −30m gap distribution ───
print("\n" + "=" * 100)
print("CHECK 1: GAP AT -30m (price - p_fair_a)")
print("=" * 100)

for label, gaps, wrong, total in [
    ('Kalshi', np.array(gaps_k), side_wrong_k, total_k),
    ('Polymarket', np.array(gaps_pm), side_wrong_pm, total_pm),
]:
    print(f"\n  {label} (n={len(gaps)}):")
    print(f"    mean={gaps.mean():+.4f}, median={np.median(gaps):+.4f}, SD={gaps.std():.4f}")
    print(f"    |gap| > 5c:  {(np.abs(gaps) > 0.05).sum()}/{len(gaps)} ({(np.abs(gaps) > 0.05).mean():.1%})")
    print(f"    |gap| > 10c: {(np.abs(gaps) > 0.10).sum()}/{len(gaps)} ({(np.abs(gaps) > 0.10).mean():.1%})")
    print(f"    |gap| > 20c: {(np.abs(gaps) > 0.20).sum()}/{len(gaps)} ({(np.abs(gaps) > 0.20).mean():.1%})")
    print(f"    Closer to p_fair_b: {wrong}/{total} — {'SIDE MAPPING ISSUE' if wrong > total * 0.1 else 'OK'}")

    # Histogram
    bins = np.arange(-0.50, 0.55, 0.05)
    hist, _ = np.histogram(gaps, bins=bins)
    print(f"    Histogram:")
    for i, h in enumerate(hist):
        bar = '#' * min(h * 2, 60)
        lo = bins[i]
        hi = bins[i + 1]
        if h > 0:
            print(f"      [{lo:+.2f},{hi:+.2f}) {h:>3} {bar}")

# ─── CHECK 3: Side audit via price path ───
print("\n" + "=" * 100)
print("CHECK 3: SIDE AUDIT — mean price vs p_fair_a/p_fair_b")
print("=" * 100)

flagged = []
for fid, fi in fight_info.items():
    fp = panel[panel['fight_id'] == fid]
    if len(fp) < 10:
        continue

    for venue, col in [('kalshi', 'k_last'), ('polymarket', 'pm_last')]:
        prices = fp[col].dropna()
        if len(prices) < 5:
            continue
        mean_p = prices.mean()
        dist_a = abs(mean_p - fi['p_fair_a'])
        dist_b = abs(mean_p - fi['p_fair_b'])
        if dist_b < dist_a:
            flagged.append({
                'fid': fid, 'venue': venue, 'mean_p': mean_p,
                'p_fair_a': fi['p_fair_a'], 'p_fair_b': fi['p_fair_b'],
                'fighter_a': fi['fighters_k'][0], 'fighter_b': fi['fighters_k'][1],
                'ticker': fi['tickers'][0] if fi['tickers'] else '',
                'slug': fi['pm_slug'],
            })

print(f"\nFights where mean price closer to p_fair_b (wrong side?): {len(flagged)}")
total_venue_pairs = sum(1 for fi in fight_info.values() for _ in ['k', 'pm'] if len(panel[panel['fight_id'] == list(fight_info.keys())[0]]) > 0)
# Simpler count
n_k = sum(1 for fid in fight_info if len(panel[(panel['fight_id'] == fid)].dropna(subset=['k_last'])) >= 5)
n_pm = sum(1 for fid in fight_info if len(panel[(panel['fight_id'] == fid)].dropna(subset=['pm_last'])) >= 5)
print(f"Total venue-fight pairs checked: K={n_k}, PM={n_pm}")
print(f"Flagged: {len(flagged)} ({len(flagged)/(n_k+n_pm):.1%} of pairs)")

if flagged:
    print(f"\n{'fid':<22} {'venue':<10} {'mean_p':>7} {'p_a':>7} {'p_b':>7} {'fighter_a':<18} {'ref':<25}")
    print("-" * 95)
    for f in flagged[:20]:
        ref = f['ticker'] if f['venue'] == 'kalshi' else f['slug']
        print(f"{f['fid']:<22} {f['venue']:<10} {f['mean_p']:>7.3f} {f['p_fair_a']:>7.3f} "
              f"{f['p_fair_b']:>7.3f} {f['fighter_a'][:17]:<18} {ref[:24]:<25}")
