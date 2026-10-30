#!/usr/bin/env python3
"""
pm_vs_book_v2.py — Corrected side mapping (YES = fighters_pm[0]).
Tail diagnosis + convergence/settlement with and without >=3 trades guard.
"""
import csv, json, os, re, sys, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import timedelta

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PM_ROOT = r'C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public'
SEED = 67; N_BOOT = 5000
HORIZONS = [('−48h', 48), ('−24h', 24), ('−6h', 6), ('−2h', 2), ('−1h', 1), ('−30m', 0.5)]
THRESHOLDS = [0.02, 0.03, 0.05]
MAX_SIZE = 200

def kalshi_fee(p): return 0.07 * p * (1 - p)
PM_FEE = 0.02

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
def american_to_decimal(odds):
    odds = int(odds)
    return 1 + odds / 100 if odds > 0 else 1 + 100 / abs(odds)

# ─── Load ───
print("Loading...", flush=True)
panel = pd.read_parquet(f'{PM_ROOT}/data/clean/phase2_full_panel.parquet')
panel['bar_utc'] = pd.to_datetime(panel['bar_utc'], utc=True)
cw = pd.read_parquet(f'{PM_ROOT}/data/meta/ufc_crosswalk.parquet')
cw = cw[cw['exclusion_reason'].isna()].copy()
cw['event_date'] = pd.to_datetime(cw['event_date'])
km = pd.read_parquet(f'{PM_ROOT}/data/interim/kxufcfight_2026_markets.parquet')
km['close_time'] = pd.to_datetime(km['close_time'], utc=True)

book_all = []
with open('bfo_close_all.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f): book_all.append(r)

outcomes = {}
with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        parts = r['bout'].split(' vs ')
        if len(parts) != 2: continue
        if r['result'] == 'win': winner = r['picked_fighter']
        else: winner = parts[1] if normalize(r['picked_fighter']) == normalize(parts[0]) else parts[0]
        outcomes[(r['card_key'], normalize(parts[0]), normalize(parts[1]))] = normalize(winner)

cw_filtered = cw[cw['event_date'] >= '2025-08-16'].copy()

# ─── Build fight_info: YES = fighters_pm[0] ───
fight_info = {}
for _, row in cw_filtered.iterrows():
    fid = row['fight_id']
    tickers = json.loads(row['tickers']) if isinstance(row['tickers'], str) else row['tickers']
    fighters_k = json.loads(row['fighters_kalshi']) if isinstance(row['fighters_kalshi'], str) else row['fighters_kalshi']
    fighters_pm = json.loads(row['fighters_pm']) if isinstance(row['fighters_pm'], str) and row['fighters_pm'] else []
    if not tickers or not fighters_k or len(fighters_k) < 2: continue
    if not fighters_pm or len(fighters_pm) < 2: continue

    yes_fighter = fighters_pm[0]
    no_fighter = fighters_pm[1]

    anchor = None
    for t in tickers:
        match = km[km['ticker'] == t]
        if len(match) > 0:
            anchor = match.iloc[0]['close_time'] - timedelta(minutes=60)
            break
    if not anchor: continue

    yes_n = normalize(yes_fighter); no_n = normalize(no_fighter)
    bfo_match = None
    for bk in book_all:
        bf1 = normalize(bk['fighter1_name']); bf2 = normalize(bk['fighter2_name'])
        if names_match(yes_n, bf1) and names_match(no_n, bf2):
            bfo_match = {'p_fair_yes': float(bk['p_fair_a']), 'p_fair_no': float(bk['p_fair_b'])}; break
        elif names_match(yes_n, bf2) and names_match(no_n, bf1):
            bfo_match = {'p_fair_yes': float(bk['p_fair_b']), 'p_fair_no': float(bk['p_fair_a'])}; break
    if not bfo_match: continue

    yes_won = None
    for (ck, f1, f2), winner in outcomes.items():
        if (names_match(yes_n, f1) and names_match(no_n, f2)) or \
           (names_match(yes_n, f2) and names_match(no_n, f1)):
            yes_won = names_match(yes_n, winner); break

    fight_info[fid] = {
        'yes_fighter': yes_fighter, 'no_fighter': no_fighter,
        'p_fair_yes': bfo_match['p_fair_yes'], 'p_fair_no': bfo_match['p_fair_no'],
        'yes_won': yes_won, 'anchor': anchor,
        'event_date': str(row['event_date'].date()),
    }

print(f"Fights: {len(fight_info)}")

# ─── Compute horizon snapshots ───
print("Computing snapshots...", flush=True)
results = []
for fid, fi in fight_info.items():
    fp = panel[panel['fight_id'] == fid]
    if fp.empty: continue

    for hz_label, hz_hours in HORIZONS:
        hz_time = fi['anchor'] - timedelta(hours=hz_hours)
        window_start = hz_time - timedelta(hours=1)

        for venue, last_col, vwap_col, n_col, vol_col in [
            ('kalshi', 'k_last', 'k_vwap', 'k_n', 'k_vol'),
            ('polymarket', 'pm_last', 'pm_vwap', 'pm_n', 'pm_vol'),
        ]:
            mask = (fp['bar_utc'] >= window_start) & (fp['bar_utc'] <= hz_time)
            window_bars = fp[mask]
            recent = fp[fp['bar_utc'] <= hz_time].dropna(subset=[last_col])
            last_price = recent[last_col].iloc[-1] if len(recent) > 0 else np.nan
            if np.isnan(last_price): continue

            wb = window_bars.dropna(subset=[last_col])
            trade_count = wb[n_col].sum() if len(wb) > 0 else 0
            volume = wb[vol_col].sum() if len(wb) > 0 else 0

            gap = last_price - fi['p_fair_yes']

            results.append({
                'fight_id': fid, 'card_date': fi['event_date'],
                'venue': venue, 'horizon': hz_label,
                'last_price': last_price, 'trade_count_1h': trade_count,
                'volume_1h': volume, 'p_fair_yes': fi['p_fair_yes'],
                'gap': gap, 'yes_won': fi['yes_won'], 'anchor': fi['anchor'],
            })

df = pd.DataFrame(results)
print(f"Snapshots: {len(df)} rows, {df['fight_id'].nunique()} fights")

# ═══════════════════════════════════════════════════════════════════
# 1. TAIL DIAGNOSIS
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 90)
print("1. TAIL DIAGNOSIS: fights with |gap| > 10c")
print("=" * 90)
print(f"{'Horizon':<8} {'Venue':<12} {'|gap|>10c':>9} {'zero_trades':>11} {'med_count':>9} {'med_vol':>8}")
print("-" * 60)
for hz_label, _ in HORIZONS:
    for venue in ['kalshi', 'polymarket']:
        sub = df[(df['horizon'] == hz_label) & (df['venue'] == venue)]
        tail = sub[sub['gap'].abs() > 0.10]
        if len(tail) == 0:
            print(f"{hz_label:<8} {venue:<12} {0:>9}")
            continue
        zero = (tail['trade_count_1h'] == 0).sum()
        med_ct = tail['trade_count_1h'].median()
        med_vol = tail['volume_1h'].median()
        print(f"{hz_label:<8} {venue:<12} {len(tail):>9} {zero:>11} {med_ct:>9.0f} {med_vol:>8.0f}")

# ═══════════════════════════════════════════════════════════════════
# 2. TRADING STRATEGIES
# ═══════════════════════════════════════════════════════════════════
rng = np.random.RandomState(SEED)

# Get −30m prices for convergence
exit_prices = {}
for _, row in df[df['horizon'] == '−30m'].iterrows():
    exit_prices[(row['fight_id'], row['venue'])] = row['last_price']

def run_strategy(label_prefix, min_trades, settlement=True):
    print(f"\n{'=' * 90}")
    print(f"{'SETTLEMENT' if settlement else 'CONVERGENCE (exit at -30m)'} — "
          f"{'no trade guard' if min_trades == 0 else f'>={min_trades} trades guard'}")
    print(f"{'=' * 90}")

    for threshold in THRESHOLDS:
        print(f"\n  Threshold = {threshold*100:.0f}c")
        print(f"  {'Horizon':<8} {'Venue':<12} {'Bets':>5} {'mFill':>7} {'ROI':>7} {'CLV':>7} {'CI_lo':>7} {'CI_hi':>7}")
        print("  " + "-" * 65)

        for hz_label, hz_hours in HORIZONS:
            if not settlement and hz_hours <= 0.5: continue
            for venue in ['kalshi', 'polymarket']:
                sub = df[(df['horizon'] == hz_label) & (df['venue'] == venue)]
                if min_trades > 0:
                    sub = sub[sub['trade_count_1h'] >= min_trades]
                if len(sub) == 0: continue

                bets = []
                for _, row in sub.iterrows():
                    pm_p = row['last_price']
                    fair = row['p_fair_yes']
                    vol = row['volume_1h']
                    size = min(MAX_SIZE, vol) if vol > 0 else 0
                    if size <= 0: continue

                    if pm_p < fair - threshold:
                        # Buy Yes at pm_p
                        if settlement:
                            profit = (1 - pm_p) * size if row['yes_won'] else -pm_p * size
                        else:
                            exit_p = exit_prices.get((row['fight_id'], venue))
                            if exit_p is None: continue
                            profit = (exit_p - pm_p) * size
                        clv = fair - pm_p
                        bets.append({'profit': profit, 'size': size * pm_p, 'clv': clv,
                                     'card': row['card_date'], 'fight': row['fight_id']})
                    elif pm_p > fair + threshold:
                        # Buy No at (1-pm_p)
                        pm_no = 1 - pm_p
                        fair_no = 1 - fair
                        if settlement:
                            profit = (1 - pm_no) * size if not row['yes_won'] else -pm_no * size
                        else:
                            exit_p = exit_prices.get((row['fight_id'], venue))
                            if exit_p is None: continue
                            profit = (pm_p - exit_p) * size  # = ((1-exit_p) - (1-pm_p)) * size
                        clv = fair_no - pm_no
                        bets.append({'profit': profit, 'size': size * pm_no, 'clv': clv,
                                     'card': row['card_date'], 'fight': row['fight_id']})

                if not bets: continue

                total_profit = sum(b['profit'] for b in bets)
                total_staked = sum(b['size'] for b in bets)
                roi = total_profit / total_staked if total_staked > 0 else 0
                mean_clv = np.mean([b['clv'] for b in bets])
                mean_fill = total_staked / len(bets)

                # Bootstrap
                fights = list(set(b['fight'] for b in bets))
                fight_bets = defaultdict(list)
                for b in bets: fight_bets[b['fight']].append(b)
                boot_rois = []
                for _ in range(N_BOOT):
                    sf = rng.choice(fights, size=len(fights), replace=True)
                    sp = ss = 0
                    for f in sf:
                        for b in fight_bets[f]:
                            sp += b['profit']; ss += b['size']
                    boot_rois.append(sp / ss if ss > 0 else 0)
                ci = (np.percentile(boot_rois, 2.5), np.percentile(boot_rois, 97.5))

                print(f"  {hz_label:<8} {venue:<12} {len(bets):>5} ${mean_fill:>5.0f} "
                      f"{roi:>+6.1%} {mean_clv:>+6.4f} {ci[0]:>+6.1%} {ci[1]:>+6.1%}")

# Run all variants
run_strategy("Settlement, no guard", min_trades=0, settlement=True)
run_strategy("Settlement, >=3 trades", min_trades=3, settlement=True)
run_strategy("Convergence, no guard", min_trades=0, settlement=False)
run_strategy("Convergence, >=3 trades", min_trades=3, settlement=False)

# ─── Leave-one-card-out (3c, -6h, settlement, >=3 trades) ───
print(f"\n{'=' * 90}")
print("LEAVE-ONE-CARD-OUT (3c, -6h, settlement, >=3 trades)")
print(f"{'=' * 90}")
for venue in ['kalshi', 'polymarket']:
    sub = df[(df['horizon'] == '−6h') & (df['venue'] == venue)]
    sub = sub[sub['trade_count_1h'] >= 3]
    bets = []
    for _, row in sub.iterrows():
        pm_p = row['last_price']; fair = row['p_fair_yes']
        vol = row['volume_1h']; size = min(MAX_SIZE, vol) if vol > 0 else 0
        if size <= 0: continue
        if pm_p < fair - 0.03:
            profit = (1 - pm_p) * size if row['yes_won'] else -pm_p * size
            bets.append({'profit': profit, 'size': size * pm_p, 'card': row['card_date']})
        elif pm_p > fair + 0.03:
            pm_no = 1 - pm_p
            profit = (1 - pm_no) * size if not row['yes_won'] else -pm_no * size
            bets.append({'profit': profit, 'size': size * pm_no, 'card': row['card_date']})
    if not bets: continue
    cards = sorted(set(b['card'] for b in bets))
    full_roi = sum(b['profit'] for b in bets) / sum(b['size'] for b in bets)
    print(f"\n  {venue} ({len(bets)} bets, {len(cards)} cards, full ROI={full_roi:+.1%}):")
    for card in cards:
        subset = [b for b in bets if b['card'] != card]
        if not subset: continue
        roi = sum(b['profit'] for b in subset) / sum(b['size'] for b in subset)
        n_drop = sum(1 for b in bets if b['card'] == card)
        print(f"    drop {card}: ROI={roi:>+6.1%} (-{n_drop} bets)")

print("\nDone.")
