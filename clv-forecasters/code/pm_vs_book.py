#!/usr/bin/env python3
"""
pm_vs_book.py — PM vs Book Close analysis for UFC prediction markets.
"Book close as benchmark = upper bound on edge"

Sample: phase2 panel fights from 2025-08-16 with bfo_close_all match.
Anchor: Kalshi close_time − 60 min.
Horizons: −48h, −24h, −6h, −2h, −1h, −30m before anchor.
"""

import csv, json, os, re, sys, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import timedelta

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
PM_ROOT = r'C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public'
HORIZONS = [('−48h', 48), ('−24h', 24), ('−6h', 6), ('−2h', 2), ('−1h', 1), ('−30m', 0.5)]
THRESHOLDS = [0.02, 0.03, 0.05]
MAX_SIZE = 200  # $ cap per bet

# Fees
def kalshi_fee(p): return 0.07 * p * (1 - p)  # per side, round trip = 2x
def pm_taker_fee(): return 0.02  # Polymarket current taker fee (2%)

# ─── helpers ───
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

# ─── Load data ───
print("Loading data...", flush=True)

# 1. Phase2 panel (5-min bars, both venues)
panel = pd.read_parquet(f'{PM_ROOT}/data/clean/phase2_full_panel.parquet')
panel['bar_utc'] = pd.to_datetime(panel['bar_utc'], utc=True)

# 2. Crosswalk (fight_id → event_date, fighters, tickers)
cw = pd.read_parquet(f'{PM_ROOT}/data/meta/ufc_crosswalk.parquet')
cw = cw[cw['exclusion_reason'].isna()].copy()
cw['event_date'] = pd.to_datetime(cw['event_date'])

# 3. Kalshi market metadata (for close_time)
km = pd.read_parquet(f'{PM_ROOT}/data/interim/kxufcfight_2026_markets.parquet')
km['close_time'] = pd.to_datetime(km['close_time'], utc=True)

# 4. Book close reference
book = {}
with open('bfo_close_all.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        key = (r['bfo_event_id'], r['bfo_matchup_id'])
        book[key] = {
            'f1': r['fighter1_name'], 'f2': r['fighter2_name'],
            'p_fair_a': float(r['p_fair_a']), 'p_fair_b': float(r['p_fair_b']),
            'date': r['event_date'],
        }

# 5. ezoteryka_scored for outcomes
outcomes = {}
with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        parts = r['bout'].split(' vs ')
        if len(parts) != 2: continue
        key = (r['card_key'], normalize(parts[0]), normalize(parts[1]))
        outcomes[key] = {
            'winner': normalize(r['picked_fighter']) if r['result'] == 'win' else normalize(parts[1] if normalize(r['picked_fighter']) == normalize(parts[0]) else parts[0]),
            'p_fair_picked': float(r['p_fair_picked']),
            'result': r['result'],
            'card_key': r['card_key'],
            'canonical_date': r['canonical_date'],
        }

print(f"Panel: {len(panel)} bars, {panel['fight_id'].nunique()} fights")
print(f"Crosswalk: {len(cw)} fights")
print(f"Book close: {len(book)} bouts")

# ─── Build fight-level dataset ───
# Filter to fights from 2025-08-16 onwards
cw_filtered = cw[cw['event_date'] >= '2025-08-16'].copy()
print(f"Fights from 2025-08-16: {len(cw_filtered)}")

# For each fight: get anchor time (close_time - 60min)
# Map via tickers to Kalshi market close_time
fight_anchors = {}
for _, row in cw_filtered.iterrows():
    fid = row['fight_id']
    tickers = json.loads(row['tickers']) if isinstance(row['tickers'], str) else row['tickers']
    if not tickers: continue
    # Find close_time from Kalshi markets
    for t in tickers:
        match = km[km['ticker'] == t]
        if len(match) > 0:
            ct = match.iloc[0]['close_time']
            fight_anchors[fid] = ct - timedelta(minutes=60)
            break

print(f"Fights with anchor time: {len(fight_anchors)}")

# Match fights to book close
# fight_id format: 20250510_GRASIL -> need to match to bfo_close_all by fighter names
fight_book = {}
for _, row in cw_filtered.iterrows():
    fid = row['fight_id']
    fighters_k = json.loads(row['fighters_kalshi']) if isinstance(row['fighters_kalshi'], str) else row['fighters_kalshi']
    if not fighters_k or len(fighters_k) < 2: continue

    fa_n = normalize(fighters_k[0])
    fb_n = normalize(fighters_k[1])

    for (eid, mid), bk in book.items():
        bf1 = normalize(bk['f1']); bf2 = normalize(bk['f2'])
        if (names_match(fa_n, bf1) and names_match(fb_n, bf2)) or \
           (names_match(fa_n, bf2) and names_match(fb_n, bf1)):
            # Align: which kalshi fighter is f1 in book?
            if names_match(fa_n, bf1):
                fight_book[fid] = {'p_fair_a': bk['p_fair_a'], 'p_fair_b': bk['p_fair_b'],
                                   'fighter_a': fighters_k[0], 'fighter_b': fighters_k[1],
                                   'date': bk['date']}
            else:
                fight_book[fid] = {'p_fair_a': bk['p_fair_b'], 'p_fair_b': bk['p_fair_a'],
                                   'fighter_a': fighters_k[0], 'fighter_b': fighters_k[1],
                                   'date': bk['date']}
            break

# Match to outcomes
fight_outcome = {}
for fid, fb in fight_book.items():
    fa_n = normalize(fb['fighter_a']); fb_n = normalize(fb['fighter_b'])
    for (ck, f1, f2), oc in outcomes.items():
        if (names_match(fa_n, f1) and names_match(fb_n, f2)) or \
           (names_match(fa_n, f2) and names_match(fb_n, f1)):
            # Did fighter_a win?
            winner_n = oc['winner']
            a_won = names_match(fa_n, winner_n)
            fight_outcome[fid] = a_won
            break

valid_fights = set(fight_anchors.keys()) & set(fight_book.keys()) & set(fight_outcome.keys())
print(f"Fights with anchor + book + outcome: {len(valid_fights)}")

# ─── Compute horizon snapshots ───
print("\nComputing horizon snapshots...", flush=True)

results = []  # one row per fight × venue × horizon

for fid in sorted(valid_fights):
    anchor = fight_anchors[fid]
    fb = fight_book[fid]
    a_won = fight_outcome[fid]
    p_fair_a = fb['p_fair_a']

    fight_panel = panel[panel['fight_id'] == fid].copy()
    if fight_panel.empty: continue

    card_date = fb['date']

    for hz_label, hz_hours in HORIZONS:
        hz_time = anchor - timedelta(hours=hz_hours)
        window_start = hz_time - timedelta(hours=1)

        for venue, last_col, vwap_col, n_col, vol_col in [
            ('kalshi', 'k_last', 'k_vwap', 'k_n', 'k_vol'),
            ('polymarket', 'pm_last', 'pm_vwap', 'pm_n', 'pm_vol'),
        ]:
            # Bars in the 1h window before horizon
            mask = (fight_panel['bar_utc'] >= window_start) & (fight_panel['bar_utc'] <= hz_time)
            window_bars = fight_panel[mask]

            # Last price: most recent non-null
            recent = fight_panel[fight_panel['bar_utc'] <= hz_time].dropna(subset=[last_col])
            last_price = recent[last_col].iloc[-1] if len(recent) > 0 else np.nan

            # 1h stats
            wb = window_bars.dropna(subset=[last_col])
            trade_count = wb[n_col].sum() if len(wb) > 0 else 0
            volume = wb[vol_col].sum() if len(wb) > 0 else 0
            vwap = wb[vwap_col].dropna().mean() if len(wb) > 0 and wb[vwap_col].notna().any() else np.nan

            if np.isnan(last_price): continue

            # Gap = PM price − book fair prob (for fighter_a side)
            gap = last_price - p_fair_a

            results.append({
                'fight_id': fid, 'card_date': card_date,
                'venue': venue, 'horizon': hz_label,
                'last_price': last_price, 'vwap_1h': vwap,
                'trade_count_1h': trade_count, 'volume_1h': volume,
                'p_fair_a': p_fair_a, 'gap': gap, 'a_won': a_won,
                'anchor': anchor,
            })

df = pd.DataFrame(results)
print(f"Horizon snapshots: {len(df)} rows, {df['fight_id'].nunique()} fights")

# ─── Report ───
print("\n" + "=" * 90)
print("PM vs BOOK CLOSE — book close as benchmark = upper bound on edge")
print("=" * 90)

# Gap distribution by horizon × venue
print("\n## Gap distribution (PM price − book fair prob)")
print(f"{'Horizon':<8} {'Venue':<12} {'n':>5} {'mean':>7} {'|gap|':>7} {'SD':>7} {'|gap|>fee%':>10}")
print("-" * 60)

for hz_label, _ in HORIZONS:
    for venue in ['kalshi', 'polymarket']:
        sub = df[(df['horizon'] == hz_label) & (df['venue'] == venue)]
        if len(sub) == 0: continue
        gaps = sub['gap'].values
        abs_gaps = np.abs(gaps)
        # Fee threshold
        if venue == 'kalshi':
            fees = sub['last_price'].apply(lambda p: kalshi_fee(p) * 2).values  # round trip
        else:
            fees = np.full(len(sub), pm_taker_fee())
        above_fee = (abs_gaps > fees).mean()
        print(f"{hz_label:<8} {venue:<12} {len(sub):>5} {gaps.mean():>+7.4f} {abs_gaps.mean():>7.4f} "
              f"{gaps.std():>7.4f} {above_fee:>9.1%}")

# ─── Trading strategy ───
print("\n## Trading strategy: buy PM side where PM < book fair − threshold")
print("Book close as benchmark = upper bound on edge")

rng = np.random.RandomState(SEED)

for threshold in THRESHOLDS:
    print(f"\n### Threshold = {threshold:.0%} ({threshold*100:.0f}¢)")
    print(f"{'Horizon':<8} {'Venue':<12} {'Bets':>5} {'meanFill':>8} {'ROI':>7} {'CLV':>7} {'CI_lo':>7} {'CI_hi':>7}")
    print("-" * 70)

    for hz_label, _ in HORIZONS:
        for venue in ['kalshi', 'polymarket']:
            sub = df[(df['horizon'] == hz_label) & (df['venue'] == venue)].copy()
            if len(sub) == 0: continue

            # Strategy: buy fighter_a side if PM_price < p_fair_a - threshold
            #           buy fighter_b side if (1-PM_price) < (1-p_fair_a) - threshold
            #           i.e. PM_price > p_fair_a + threshold
            bets = []
            for _, row in sub.iterrows():
                pm_p = row['last_price']
                fair_a = row['p_fair_a']
                vol = row['volume_1h']
                size = min(MAX_SIZE, vol) if vol > 0 else 0
                if size <= 0: continue

                if pm_p < fair_a - threshold:
                    # Buy A side at pm_p, settles at 1 if A wins
                    profit = (1 - pm_p) * size if row['a_won'] else -pm_p * size
                    clv = fair_a - pm_p
                    bets.append({'profit': profit, 'size': size * pm_p, 'clv': clv,
                                 'card': row['card_date'], 'fight': row['fight_id']})
                elif pm_p > fair_a + threshold:
                    # Buy B side at (1-pm_p), settles at 1 if B wins
                    pm_b = 1 - pm_p; fair_b = 1 - fair_a
                    profit = (1 - pm_b) * size if not row['a_won'] else -pm_b * size
                    clv = fair_b - pm_b
                    bets.append({'profit': profit, 'size': size * pm_b, 'clv': clv,
                                 'card': row['card_date'], 'fight': row['fight_id']})

            if not bets: continue

            total_profit = sum(b['profit'] for b in bets)
            total_staked = sum(b['size'] for b in bets)
            roi = total_profit / total_staked if total_staked > 0 else 0
            mean_clv = np.mean([b['clv'] for b in bets])
            mean_fill = total_staked / len(bets)

            # Fight-clustered bootstrap
            fights = list(set(b['fight'] for b in bets))
            boot_rois = []
            for _ in range(N_BOOT):
                sample_fights = rng.choice(fights, size=len(fights), replace=True)
                s_profit = 0; s_staked = 0
                for sf in sample_fights:
                    for b in bets:
                        if b['fight'] == sf:
                            s_profit += b['profit']; s_staked += b['size']
                boot_rois.append(s_profit / s_staked if s_staked > 0 else 0)
            ci = (np.percentile(boot_rois, 2.5), np.percentile(boot_rois, 97.5))

            print(f"{hz_label:<8} {venue:<12} {len(bets):>5} ${mean_fill:>6.0f} {roi:>+6.1%} "
                  f"{mean_clv:>+6.4f} {ci[0]:>+6.1%} {ci[1]:>+6.1%}")

# ─── Convergence variant ───
print("\n## Convergence variant: exit at −30m PM price (not settlement)")
for threshold in THRESHOLDS:
    print(f"\n### Threshold = {threshold:.0%}")
    print(f"{'Horizon':<8} {'Venue':<12} {'Bets':>5} {'ROI':>7} {'CI_lo':>7} {'CI_hi':>7}")
    print("-" * 55)

    # Get −30m prices for each fight
    exit_prices = {}
    for _, row in df[(df['horizon'] == '−30m')].iterrows():
        exit_prices[(row['fight_id'], row['venue'])] = row['last_price']

    for hz_label, hz_hours in HORIZONS:
        if hz_hours <= 0.5: continue  # can't exit at −30m if entry is at −30m
        for venue in ['kalshi', 'polymarket']:
            sub = df[(df['horizon'] == hz_label) & (df['venue'] == venue)].copy()
            if len(sub) == 0: continue

            bets = []
            for _, row in sub.iterrows():
                pm_p = row['last_price']
                fair_a = row['p_fair_a']
                vol = row['volume_1h']
                size = min(MAX_SIZE, vol) if vol > 0 else 0
                if size <= 0: continue

                exit_p = exit_prices.get((row['fight_id'], venue))
                if exit_p is None: continue

                if pm_p < fair_a - threshold:
                    # Buy A at pm_p, sell at exit_p
                    profit = (exit_p - pm_p) * size
                    bets.append({'profit': profit, 'size': size * pm_p,
                                 'card': row['card_date'], 'fight': row['fight_id']})
                elif pm_p > fair_a + threshold:
                    # Buy B at (1-pm_p), sell at (1-exit_p)
                    profit = ((1 - exit_p) - (1 - pm_p)) * size  # = (pm_p - exit_p) * size
                    bets.append({'profit': profit, 'size': size * (1 - pm_p),
                                 'card': row['card_date'], 'fight': row['fight_id']})

            if not bets: continue

            total_profit = sum(b['profit'] for b in bets)
            total_staked = sum(b['size'] for b in bets)
            roi = total_profit / total_staked if total_staked > 0 else 0

            fights = list(set(b['fight'] for b in bets))
            boot_rois = []
            for _ in range(N_BOOT):
                sf = rng.choice(fights, size=len(fights), replace=True)
                sp = ss = 0
                for f in sf:
                    for b in bets:
                        if b['fight'] == f: sp += b['profit']; ss += b['size']
                boot_rois.append(sp / ss if ss > 0 else 0)
            ci = (np.percentile(boot_rois, 2.5), np.percentile(boot_rois, 97.5))

            print(f"{hz_label:<8} {venue:<12} {len(bets):>5} {roi:>+6.1%} {ci[0]:>+6.1%} {ci[1]:>+6.1%}")

# ─── Leave-one-card-out (3¢ threshold, −6h, both venues) ───
print("\n## Leave-one-card-out (3¢ threshold, −6h horizon)")
for venue in ['kalshi', 'polymarket']:
    sub = df[(df['horizon'] == '−6h') & (df['venue'] == venue)]
    if len(sub) == 0: continue

    all_bets = []
    for _, row in sub.iterrows():
        pm_p = row['last_price']; fair_a = row['p_fair_a']
        vol = row['volume_1h']; size = min(MAX_SIZE, vol) if vol > 0 else 0
        if size <= 0: continue
        if pm_p < fair_a - 0.03:
            profit = (1 - pm_p) * size if row['a_won'] else -pm_p * size
            all_bets.append({'profit': profit, 'size': size * pm_p, 'card': row['card_date']})
        elif pm_p > fair_a + 0.03:
            pm_b = 1 - pm_p
            profit = (1 - pm_b) * size if not row['a_won'] else -pm_b * size
            all_bets.append({'profit': profit, 'size': size * pm_b, 'card': row['card_date']})

    if not all_bets: continue

    cards = sorted(set(b['card'] for b in all_bets))
    print(f"\n  {venue} ({len(all_bets)} bets across {len(cards)} cards):")
    full_roi = sum(b['profit'] for b in all_bets) / sum(b['size'] for b in all_bets)
    print(f"  Full ROI: {full_roi:+.1%}")
    for card in cards:
        subset = [b for b in all_bets if b['card'] != card]
        if not subset: continue
        roi = sum(b['profit'] for b in subset) / sum(b['size'] for b in subset)
        n_dropped = sum(1 for b in all_bets if b['card'] == card)
        print(f"    drop {card}: ROI={roi:>+6.1%} (−{n_dropped} bets)")

print(f"\nDone.")


if __name__ == '__main__':
    main() if 'main' in dir() else None
