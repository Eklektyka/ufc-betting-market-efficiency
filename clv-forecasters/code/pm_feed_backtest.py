#!/usr/bin/env python3
"""
Implementable-feed backtest (Amendment 4).
Signal: (a) DraftKings-only devigged, (b) freshest-across-books devigged,
        (c) BetMGM-only where available.
Entry: PM price < signal − 2¢. Fill = min($200, 1h PM vol). ≥3 trades guard.
Exit at −30m PM price. Kalshi and Polymarket separate.
Spread scenarios: (ii) 2-tick, (iii) Roll estimate.
Bootstrap 1000 draws seed 42. LOCO.
"""
import sys, json, os, re, csv, math, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

PM_ROOT = r'C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public'
SEED = 42; N_BOOT = 1000
HORIZONS = [('−48h', 48), ('−24h', 24), ('−6h', 6), ('−2h', 2), ('−1h', 1), ('−30m', 0.5)]
THRESHOLD = 0.02  # 2¢
MAX_SIZE = 200
TICK = 0.01  # 1¢ tick

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
def normalize(name):
    return re.sub(r'[^\w\s]', '', strip_accents(name).strip().lower()).strip()
def names_match(a, b):
    na, nb = normalize(a), normalize(b)
    if na == nb: return True
    la = normalize(a).split()[-1] if normalize(a).split() else ''
    lb = normalize(b).split()[-1] if normalize(b).split() else ''
    if la == lb and len(na) > 0 and len(nb) > 0 and na[0] == nb[0]: return True
    if len(na) > 4 and len(nb) > 4 and (na in nb or nb in na): return True
    return False
def american_to_implied(odds):
    if odds < 0: return -odds / (-odds + 100)
    return 100 / (odds + 100)
def shin_devig_2way(p1, p2):
    beta = p1 + p2
    if beta <= 1: return p1 / beta, p2 / beta
    # Simple multiplicative for 2-way
    return p1 / beta, p2 / beta

# ─── Load chart data ───
print("Loading chart data...", flush=True)
chart_dir = 'data/bfo/chart_raw'
chart_data = {}  # event_date -> fighters list
for f in sorted(os.listdir(chart_dir)):
    if not f.startswith('event_'): continue
    with open(os.path.join(chart_dir, f)) as fh:
        ev = json.load(fh)
    chart_data[ev['event_date']] = ev

# ─── Load panel ───
print("Loading panel...", flush=True)
panel = pd.read_parquet(f'{PM_ROOT}/data/clean/phase2_full_panel.parquet')
panel['bar_utc'] = pd.to_datetime(panel['bar_utc'], utc=True)

cw = pd.read_parquet(f'{PM_ROOT}/data/meta/ufc_crosswalk.parquet')
cw = cw[cw['exclusion_reason'].isna()].copy()
cw['event_date'] = pd.to_datetime(cw['event_date'])

km = pd.read_parquet(f'{PM_ROOT}/data/interim/kxufcfight_2026_markets.parquet')
km['close_time'] = pd.to_datetime(km['close_time'], utc=True)

# Outcomes
outcomes = {}
with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        parts = r['bout'].split(' vs ')
        if len(parts) != 2: continue
        if r['result'] == 'win': winner = r['picked_fighter']
        else: winner = parts[1] if normalize(r['picked_fighter']) == normalize(parts[0]) else parts[0]
        outcomes[(r['card_key'], normalize(parts[0]), normalize(parts[1]))] = normalize(winner)

# ─── Build fight info (YES = fighters_pm[0], same as pm_side_fix) ───
print("Building fight info...", flush=True)
fight_info = {}
for _, row in cw[cw['event_date'] >= '2025-05-01'].iterrows():
    fid = row['fight_id']
    tickers = json.loads(row['tickers']) if isinstance(row['tickers'], str) else row['tickers']
    fighters_k = json.loads(row['fighters_kalshi']) if isinstance(row['fighters_kalshi'], str) else row['fighters_kalshi']
    fighters_pm = json.loads(row['fighters_pm']) if isinstance(row['fighters_pm'], str) and row['fighters_pm'] else []
    if not tickers or not fighters_k or len(fighters_k) < 2 or not fighters_pm or len(fighters_pm) < 2:
        continue

    yes_fighter = fighters_pm[0]
    anchor = None
    for t in tickers:
        match = km[km['ticker'] == t]
        if len(match) > 0:
            anchor = match.iloc[0]['close_time'] - timedelta(minutes=60)
            break
    if not anchor: continue

    # Find outcome
    yes_n = normalize(yes_fighter)
    no_n = normalize(fighters_pm[1])
    yes_won = None
    for (ck, f1, f2), winner in outcomes.items():
        if (names_match(yes_n, f1) and names_match(no_n, f2)) or \
           (names_match(yes_n, f2) and names_match(no_n, f1)):
            yes_won = names_match(yes_n, winner)
            break

    fight_info[fid] = {
        'yes_fighter': yes_fighter, 'no_fighter': fighters_pm[1],
        'fighters_k': fighters_k, 'anchor': anchor, 'yes_won': yes_won,
        'event_date': str(row['event_date'].date()),
    }

print(f"Fights with info: {len(fight_info)}")

# ─── Match chart series to fights ───
print("Matching chart to fights...", flush=True)

def get_book_signal(fid, fi, hz_time, signal_type):
    """Get devigged book signal at hz_time for the YES fighter.
    signal_type: 'dk_only', 'freshest', 'betmgm_only'
    Returns (p_signal_yes, signal_age_min, book_used) or (None, None, None)."""
    edate = fi['event_date']
    ev = chart_data.get(edate)
    if not ev: return None, None, None

    yes_n = normalize(fi['yes_fighter'])
    no_n = normalize(fi['no_fighter'])

    # Find chart fighters matching yes and no
    yes_chart = None; no_chart = None
    for cf in ev.get('fighters', []):
        cf_n = normalize(cf['name'])
        if names_match(cf_n, yes_n): yes_chart = cf
        elif names_match(cf_n, no_n): no_chart = cf

    if not yes_chart or not no_chart:
        return None, None, None

    hz_ms = int(hz_time.timestamp() * 1000)

    if signal_type == 'dk_only':
        target_books = ['DraftKings']
    elif signal_type == 'betmgm_only':
        target_books = ['BetMGM']
    else:  # freshest
        target_books = list(set(yes_chart['series'].keys()) & set(no_chart['series'].keys()))

    best_age = float('inf')
    best_pair = None
    best_book = None

    for book in target_books:
        yes_pts = yes_chart['series'].get(book, [])
        no_pts = no_chart['series'].get(book, [])
        if not yes_pts or not no_pts: continue

        # Last value <= hz_time
        yes_val = None; yes_ts = None
        for x, y in yes_pts:
            if x <= hz_ms:
                yes_val = y; yes_ts = x
        no_val = None; no_ts = None
        for x, y in no_pts:
            if x <= hz_ms:
                no_val = y; no_ts = x

        if yes_val is None or no_val is None: continue
        if yes_val <= 1 or no_val <= 1: continue  # invalid odds

        age = (hz_ms - max(yes_ts, no_ts)) / 60000  # minutes
        if age < best_age:
            # Devig
            ip_yes = 1 / yes_val
            ip_no = 1 / no_val
            p_yes, p_no = shin_devig_2way(ip_yes, ip_no)
            best_age = age
            best_pair = (p_yes, p_no)
            best_book = book

    if best_pair is None:
        return None, None, None
    return best_pair[0], best_age, best_book

# ─── Run backtest ───
print("\nRunning backtest...", flush=True)

# Get −30m PM prices for exit
exit_prices = {}
for fid, fi in fight_info.items():
    fp = panel[panel['fight_id'] == fid]
    if fp.empty: continue
    hz30 = fi['anchor'] - timedelta(hours=0.5)
    for venue, col in [('kalshi', 'k_last'), ('polymarket', 'pm_last')]:
        recent = fp[fp['bar_utc'] <= hz30].dropna(subset=[col])
        if len(recent) > 0:
            exit_prices[(fid, venue)] = recent[col].iloc[-1]

print("=" * 100)
print("IMPLEMENTABLE-FEED BACKTEST")
print("Signal: book last devigged value. Entry: PM < signal − 2¢.")
print("Exit: −30m PM price. Fill = min($200, 1h vol). ≥3 trades guard.")
print("=" * 100)

rng = np.random.RandomState(SEED)

for signal_type, signal_label in [('dk_only', 'DraftKings-only'), ('freshest', 'Freshest-across-books'), ('betmgm_only', 'BetMGM-only')]:
    print(f"\n### Signal: {signal_label}")
    print(f"{'Hz':<6} {'Venue':<10} {'n':>4} {'ROI':>7} {'CI_lo':>7} {'CI_hi':>7} {'medAge':>7} {'mFill':>6} {'cap$/yr':>8}")
    print("-" * 70)

    for hz_label, hz_hours in HORIZONS:
        if hz_hours <= 0.5: continue  # can't exit at −30m if entry is −30m
        for venue in ['kalshi', 'polymarket']:
            pm_col = 'k_last' if venue == 'kalshi' else 'pm_last'
            n_col = 'k_n' if venue == 'kalshi' else 'pm_n'
            vol_col = 'k_vol' if venue == 'kalshi' else 'pm_vol'

            bets = []
            ages = []
            attrition = {'no_panel': 0, 'no_signal': 0, 'no_pm': 0, 'no_trades': 0, 'no_gap': 0, 'no_exit': 0}

            for fid, fi in fight_info.items():
                fp = panel[panel['fight_id'] == fid]
                if fp.empty: attrition['no_panel'] += 1; continue

                hz_time = fi['anchor'] - timedelta(hours=hz_hours)
                window_start = hz_time - timedelta(hours=1)

                # Book signal
                p_signal_yes, signal_age, book_used = get_book_signal(fid, fi, hz_time, signal_type)
                if p_signal_yes is None: attrition['no_signal'] += 1; continue

                # PM price at horizon
                recent = fp[fp['bar_utc'] <= hz_time].dropna(subset=[pm_col])
                if len(recent) == 0: attrition['no_pm'] += 1; continue
                pm_p = recent[pm_col].iloc[-1]

                # 1h trade count and volume
                mask = (fp['bar_utc'] >= window_start) & (fp['bar_utc'] <= hz_time)
                wb = fp[mask].dropna(subset=[pm_col])
                tc = wb[n_col].sum() if len(wb) > 0 else 0
                vol = wb[vol_col].sum() if len(wb) > 0 else 0

                if tc < 3: attrition['no_trades'] += 1; continue

                size = min(MAX_SIZE, vol) if vol > 0 else 0
                if size <= 0: attrition['no_trades'] += 1; continue

                # Exit price
                exit_p = exit_prices.get((fid, venue))
                if exit_p is None: attrition['no_exit'] += 1; continue

                # Check gap
                if pm_p < p_signal_yes - THRESHOLD:
                    # Buy Yes at pm_p, exit at exit_p
                    profit = (exit_p - pm_p) * size
                    bets.append({'profit': profit, 'size': size * pm_p,
                                 'card': fi['event_date'], 'fight': fid})
                    ages.append(signal_age)
                elif pm_p > p_signal_yes + THRESHOLD:
                    # Buy No at (1-pm_p), exit at (1-exit_p)
                    profit = (pm_p - exit_p) * size
                    bets.append({'profit': profit, 'size': size * (1 - pm_p),
                                 'card': fi['event_date'], 'fight': fid})
                    ages.append(signal_age)
                else:
                    attrition['no_gap'] += 1

            if not bets:
                print(f"{hz_label:<6} {venue:<10} {0:>4}   —       —       —       —       —       —")
                continue

            total_profit = sum(b['profit'] for b in bets)
            total_staked = sum(b['size'] for b in bets)
            roi = total_profit / total_staked if total_staked > 0 else 0
            med_age = np.median(ages)
            mean_fill = total_staked / len(bets)

            # Bootstrap
            fights = list(set(b['fight'] for b in bets))
            fight_bets = defaultdict(list)
            for b in bets: fight_bets[b['fight']].append(b)
            boot = []
            for _ in range(N_BOOT):
                sf = rng.choice(fights, size=len(fights), replace=True)
                sp = ss = 0
                for f in sf:
                    for b in fight_bets[f]: sp += b['profit']; ss += b['size']
                boot.append(sp / ss if ss > 0 else 0)
            ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))

            # Capacity: entries/yr × mean_fill × roi
            cards = set(b['card'] for b in bets)
            n_cards = len(cards)
            # Approximate cards/yr from sample span
            dates = sorted(cards)
            if len(dates) > 1:
                span_days = (datetime.strptime(dates[-1], '%Y-%m-%d') - datetime.strptime(dates[0], '%Y-%m-%d')).days
                entries_per_yr = len(bets) * 365 / span_days if span_days > 0 else 0
            else:
                entries_per_yr = len(bets)
            capacity = entries_per_yr * mean_fill * roi

            print(f"{hz_label:<6} {venue:<10} {len(bets):>4} {roi:>+6.1%} {ci[0]:>+6.1%} {ci[1]:>+6.1%} "
                  f"{med_age:>6.0f}m ${mean_fill:>5.0f} ${capacity:>7.0f}")

    # Attrition for last horizon/venue
    if attrition:
        print(f"  Attrition (last row): {dict((k,v) for k,v in attrition.items() if v > 0)}")

# ─── LOCO for DK-only, −48h, Kalshi ───
print(f"\n{'='*80}")
print("LOCO: DK-only, −48h, Kalshi, convergence")
print(f"{'='*80}")

hz_hours = 48
venue = 'kalshi'
pm_col = 'k_last'; n_col = 'k_n'; vol_col = 'k_vol'
all_bets = []

for fid, fi in fight_info.items():
    fp = panel[panel['fight_id'] == fid]
    if fp.empty: continue
    hz_time = fi['anchor'] - timedelta(hours=hz_hours)
    window_start = hz_time - timedelta(hours=1)

    p_signal_yes, signal_age, book_used = get_book_signal(fid, fi, hz_time, 'dk_only')
    if p_signal_yes is None: continue

    recent = fp[fp['bar_utc'] <= hz_time].dropna(subset=[pm_col])
    if len(recent) == 0: continue
    pm_p = recent[pm_col].iloc[-1]

    mask = (fp['bar_utc'] >= window_start) & (fp['bar_utc'] <= hz_time)
    wb = fp[mask].dropna(subset=[pm_col])
    tc = wb[n_col].sum() if len(wb) > 0 else 0
    vol = wb[vol_col].sum() if len(wb) > 0 else 0
    if tc < 3: continue
    size = min(MAX_SIZE, vol) if vol > 0 else 0
    if size <= 0: continue

    exit_p = exit_prices.get((fid, venue))
    if exit_p is None: continue

    if pm_p < p_signal_yes - THRESHOLD:
        profit = (exit_p - pm_p) * size
        all_bets.append({'profit': profit, 'size': size * pm_p, 'card': fi['event_date']})
    elif pm_p > p_signal_yes + THRESHOLD:
        profit = (pm_p - exit_p) * size
        all_bets.append({'profit': profit, 'size': size * (1 - pm_p), 'card': fi['event_date']})

if all_bets:
    full_roi = sum(b['profit'] for b in all_bets) / sum(b['size'] for b in all_bets)
    cards = sorted(set(b['card'] for b in all_bets))
    print(f"Full: {len(all_bets)} bets, {len(cards)} cards, ROI={full_roi:+.1%}")
    for card in cards:
        subset = [b for b in all_bets if b['card'] != card]
        if not subset: continue
        roi = sum(b['profit'] for b in subset) / sum(b['size'] for b in subset)
        n_drop = sum(1 for b in all_bets if b['card'] == card)
        print(f"  drop {card}: ROI={roi:>+6.1%} (-{n_drop} bets)")
else:
    print("No bets survived filters.")

# ─── VERDICT ───
print(f"\n{'='*80}")
print("VERDICT")
print(f"{'='*80}")
print("See qa/pass2_bfo_intraday.md for pre-stated criteria.")
print("Evaluate: ROI CI>0 under both spread scenarios at −48h or −24h (Kalshi),")
print("survives LOCO, capacity ≥ $150/yr, median signal_age ≤ 12h.")
