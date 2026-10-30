#!/usr/bin/env python3
"""
Cross-venue convergence backtest: Kalshi ↔ Polymarket, UFC.
All local data, no pulls. Uses phase2_full_panel + tick-level trades.
"""
import sys, json, os, re, time, math
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import timedelta

sys.stdout.reconfigure(encoding='utf-8')

PM_ROOT = r'C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public'
SEED = 42; N_BOOT = 1000
GAP_OPEN = 0.05; GAP_CLOSE = 0.02  # Paper's episode thresholds
MAX_SIZE = 200
TICK = 0.01
EVENT_THRESH_PRIMARY = 0.02  # 2¢ move for event definition
EVENT_THRESH_SECONDARY = 0.03

rng = np.random.default_rng(SEED)

def kalshi_fee(p): return 0.07 * p * (1 - p)

print("Loading data...", flush=True)
t0 = time.time()

# Panel
panel = pd.read_parquet(f'{PM_ROOT}/data/clean/phase2_full_panel.parquet')
panel['bar_utc'] = pd.to_datetime(panel['bar_utc'], utc=True)

# Crosswalk
cw = pd.read_parquet(f'{PM_ROOT}/data/meta/ufc_crosswalk.parquet')
cw = cw[cw['exclusion_reason'].isna()].copy()
cw['event_date'] = pd.to_datetime(cw['event_date'])

# Tier map
xw = cw.copy()
xw['tier'] = 'undercard'
# Mark main events — first fight per card (highest billing)
# The crosswalk doesn't have tier, but we can infer from row position
# For now use a simple heuristic: first 2 fights per card = main/co-main

# Build tier from crosswalk order within each event_date
for edate, grp in xw.groupby('event_date'):
    indices = grp.index.tolist()
    for i, idx in enumerate(indices):
        if i == 0: xw.loc[idx, 'tier'] = 'main_event'
        elif i <= 2: xw.loc[idx, 'tier'] = 'co_main'
        else: xw.loc[idx, 'tier'] = 'undercard'

tier_map = xw.set_index('fight_id')['tier'].to_dict()
era_map = dict(zip(panel['fight_id'], panel['era']))

# Kalshi market close times
km = pd.read_parquet(f'{PM_ROOT}/data/interim/kxufcfight_2026_markets.parquet')
km['close_time'] = pd.to_datetime(km['close_time'], utc=True)

# Build anchor per fight
fight_anchors = {}
for _, row in cw.iterrows():
    fid = row['fight_id']
    tickers = json.loads(row['tickers']) if isinstance(row['tickers'], str) else row['tickers']
    if not tickers: continue
    for t in tickers:
        match = km[km['ticker'] == t]
        if len(match) > 0:
            fight_anchors[fid] = match.iloc[0]['close_time'] - timedelta(minutes=60)
            break

# Normalize all timestamps to naive UTC
panel['bar_utc'] = panel['bar_utc'].dt.tz_localize(None)
fight_anchors = {k: v.tz_localize(None) if hasattr(v, 'tz_localize') and v.tzinfo else v
                 for k, v in fight_anchors.items()}

print(f"Panel: {len(panel)} bars, {panel['fight_id'].nunique()} fights")
print(f"Anchors: {len(fight_anchors)} fights")

# ═══════════════════════════════════════════════════════════════════
# STEP 0 — SANITY ANCHOR: reproduce paper's gap-closure numbers
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("STEP 0 — SANITY: reproduce paper gap-closure (5¢ open, 2¢ close)")
print("=" * 80)

df = panel.copy()
df = df.sort_values(['fight_id', 'bar_utc']).reset_index(drop=True)
df['gap'] = df['k_last'] - df['pm_last']
df['abs_gap'] = df['gap'].abs()
df['tier'] = df['fight_id'].map(tier_map).fillna('undercard')

episodes = []
for fid, grp in df.groupby('fight_id', sort=False):
    grp = grp.sort_values('bar_utc').reset_index(drop=True)
    abs_g = grp['abs_gap'].values
    times = grp['bar_utc'].values
    k_n = grp['k_n'].values; pm_n = grp['pm_n'].values
    valid = grp['k_last'].notna().values & grp['pm_last'].notna().values
    n = len(grp)

    in_ep = False; ep_start_i = None

    for i in range(n):
        if not valid[i]: continue
        ag = abs_g[i]

        if not in_ep:
            prev_ag = None
            for j in range(i-1, -1, -1):
                if valid[j]: prev_ag = abs_g[j]; break
            if ag >= GAP_OPEN and (prev_ag is None or prev_ag < GAP_OPEN):
                in_ep = True; ep_start_i = i
                ep_k = [int(k_n[i])]; ep_pm = [int(pm_n[i])]
        else:
            ep_k.append(int(k_n[i])); ep_pm.append(int(pm_n[i]))
            if ag <= GAP_CLOSE:
                dur = (pd.Timestamp(times[i]) - pd.Timestamp(times[ep_start_i])).total_seconds() / 60
                k_active = any(v > 0 for v in ep_k)
                pm_active = any(v > 0 for v in ep_pm)
                ep_type = 'ACTIVE' if (k_active and pm_active) else 'STALE-SIDE'
                episodes.append({
                    'fight_id': fid, 'tier': tier_map.get(fid, 'undercard'),
                    'era': era_map.get(fid, '2025_lychee'),
                    'duration_min': dur, 'censored': False, 'type': ep_type,
                })
                in_ep = False

    if in_ep:
        k_active = any(v > 0 for v in ep_k)
        pm_active = any(v > 0 for v in ep_pm)
        episodes.append({
            'fight_id': fid, 'tier': tier_map.get(fid, 'undercard'),
            'era': era_map.get(fid, '2025_lychee'),
            'duration_min': np.nan, 'censored': True,
            'type': 'ACTIVE' if (k_active and pm_active) else 'STALE-SIDE',
        })

eps_df = pd.DataFrame(episodes)
active = eps_df[(eps_df['type'] == 'ACTIVE') & (~eps_df['censored'])]

print(f"\nTotal episodes: {len(eps_df)}")
print(f"Active, closed: {len(active)}")

for tier in ['main_event', 'undercard']:
    sub = active[active['tier'] == tier]
    if len(sub) > 0:
        med = sub['duration_min'].median()
        print(f"  {tier}: n={len(sub)}, median={med:.0f} min (paper: {'32' if tier=='main_event' else '118'})")

# ═══════════════════════════════════════════════════════════════════
# STEP 1 — GATE: −30m cross-venue gap
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("STEP 1 — GATE: −30m cross-venue gap (K − PM)")
print("=" * 80)

gaps_30m = []
for fid in fight_anchors:
    anchor = fight_anchors[fid]
    hz = anchor - timedelta(minutes=30)
    fp = df[df['fight_id'] == fid]
    if fp.empty: continue
    recent = fp[(fp['bar_utc'] <= hz) & fp['k_last'].notna() & fp['pm_last'].notna()]
    if len(recent) == 0: continue
    last = recent.iloc[-1]
    gaps_30m.append(last['k_last'] - last['pm_last'])

g = np.array(gaps_30m)
print(f"\nn={len(g)}, mean={g.mean():+.4f}, median={np.median(g):+.4f}, SD={g.std():.4f}")
print(f"|gap| > 5c: {(np.abs(g) > 0.05).sum()}/{len(g)} ({(np.abs(g) > 0.05).mean():.1%})")
print(f"|gap| > 10c: {(np.abs(g) > 0.10).sum()}/{len(g)} ({(np.abs(g) > 0.10).mean():.1%})")
if g.std() > 0.10:
    print("GATE FAIL: SD > 10c")
    sys.exit(1)
else:
    print("GATE PASS")

# ═══════════════════════════════════════════════════════════════════
# STEP 2 — EVENT DEFINITION (on 5-min bars)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("STEP 2 — EVENT DEFINITION (2¢ move, anti-bounce, cross-venue)")
print("=" * 80)

events_list = []
for fid in sorted(df['fight_id'].unique()):
    if fid not in fight_anchors: continue
    anchor = fight_anchors[fid]
    fp = df[df['fight_id'] == fid].sort_values('bar_utc')
    if len(fp) < 12: continue

    # Only bars ≥2h before fight
    cutoff = pd.Timestamp(anchor - timedelta(hours=2))

    for venue_a, col_a, venue_b, col_b, n_col_b, vol_col_b in [
        ('kalshi', 'k_last', 'polymarket', 'pm_last', 'pm_n', 'pm_vol'),
        ('polymarket', 'pm_last', 'kalshi', 'k_last', 'k_n', 'k_vol'),
    ]:
        vals_a = fp[[col_a, 'bar_utc']].dropna(subset=[col_a])
        vals_b = fp[[col_b, 'bar_utc', n_col_b, vol_col_b]].dropna(subset=[col_b])
        if len(vals_a) < 7 or len(vals_b) < 7: continue

        prices_a = vals_a[col_a].values
        times_a = vals_a['bar_utc'].values

        for i in range(6, len(prices_a)):
            t = pd.Timestamp(times_a[i])
            if t > cutoff: break

            # Trailing 30-min median on A (6 bars at 5-min)
            window = prices_a[max(0, i-6):i]
            trail_med = np.median(window)
            move = prices_a[i] - trail_med

            if abs(move) < EVENT_THRESH_PRIMARY: continue

            # Anti-bounce: ≥2 prints at/beyond new level within 10 min (2 bars)
            confirms = 0
            for j in range(i, min(i+3, len(prices_a))):
                if move > 0 and prices_a[j] >= prices_a[i] - 0.005: confirms += 1
                elif move < 0 and prices_a[j] <= prices_a[i] + 0.005: confirms += 1
            if confirms < 2: continue

            # B pre-drift < 1¢ over prior 30 min
            b_recent = vals_b[vals_b['bar_utc'] <= t]
            if len(b_recent) < 2: continue
            b_window = b_recent[col_b].values[-7:-1] if len(b_recent) >= 7 else b_recent[col_b].values[:-1]
            if len(b_window) < 2: continue
            b_drift = abs(b_recent[col_b].values[-1] - np.median(b_window))
            if b_drift >= 0.01: continue

            # B entry price
            b_price = b_recent[col_b].values[-1]

            # B trailing-1h volume and trade count
            b_1h = vals_b[(vals_b['bar_utc'] >= t - timedelta(hours=1)) & (vals_b['bar_utc'] <= t)]
            b_trades = b_1h[n_col_b].sum() if len(b_1h) > 0 else 0
            b_vol = b_1h[vol_col_b].sum() if len(b_1h) > 0 else 0

            # Find exit: |B - A| ≤ 1¢, or T-30m
            exit_price = None; exit_time = None; convergence_min = None
            t30m = pd.Timestamp(anchor - timedelta(minutes=30))

            remaining_b = vals_b[vals_b['bar_utc'] > t]
            remaining_a = vals_a.set_index('bar_utc')[col_a]

            for _, brow in remaining_b.iterrows():
                bt = brow['bar_utc']
                bp = brow[col_b]
                # Find contemporaneous A price
                a_at_t = remaining_a[remaining_a.index <= bt]
                if len(a_at_t) == 0: continue
                ap = a_at_t.iloc[-1]

                if abs(bp - ap) <= 0.01:
                    exit_price = bp; exit_time = bt
                    convergence_min = (bt - t).total_seconds() / 60
                    break
                if bt >= t30m:
                    exit_price = bp; exit_time = bt
                    convergence_min = (bt - t).total_seconds() / 60
                    break

            if exit_price is None: continue

            events_list.append({
                'fight_id': fid, 'venue_a': venue_a, 'venue_b': venue_b,
                'event_time': t, 'move': move, 'direction': 'up' if move > 0 else 'down',
                'b_entry': b_price, 'b_exit': exit_price,
                'b_trades_1h': b_trades, 'b_vol_1h': b_vol,
                'convergence_min': convergence_min,
                'tier': tier_map.get(fid, 'undercard'),
                'era': era_map.get(fid, '2025_lychee'),
                'card_date': str(pd.Timestamp(t).date()),
            })

ev_df = pd.DataFrame(events_list)
print(f"\nEvents found: {len(ev_df)}")
if len(ev_df) > 0:
    print(f"By direction A→B:")
    for va in ['kalshi', 'polymarket']:
        for vb in ['kalshi', 'polymarket']:
            if va == vb: continue
            sub = ev_df[(ev_df['venue_a'] == va) & (ev_df['venue_b'] == vb)]
            print(f"  {va}→{vb}: {len(sub)} events")
    print(f"By tier: {ev_df['tier'].value_counts().to_dict()}")
    print(f"By era: {ev_df['era'].value_counts().to_dict()}")

# ═══════════════════════════════════════════════════════════════════
# STEP 3 — TRADE SIM
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("STEP 3+4 — TRADE SIM + INFERENCE")
print("=" * 80)

if len(ev_df) == 0:
    print("No events — STRATEGY-DEAD (no signal)")
    sys.exit(0)

# Apply guards
guarded = ev_df[ev_df['b_trades_1h'] >= 3].copy()
print(f"\nAttrition: {len(ev_df)} events → {len(guarded)} after ≥3-trades guard")

filled = guarded.copy()
filled['fill'] = filled.apply(lambda r: min(MAX_SIZE, r['b_vol_1h']) if r['b_vol_1h'] > 0 else 0, axis=1)
filled = filled[filled['fill'] > 0]
print(f"  → {len(filled)} after fill > 0")

# Compute P&L
def compute_pnl(row, spread_ticks=0):
    move = row['move']
    entry = row['b_entry']
    exit_p = row['b_exit']
    fill = row['fill']
    venue_b = row['venue_b']

    # Entry: buy B toward A's move direction
    if move > 0:
        # A moved up → buy B (Yes side)
        buy_p = entry + spread_ticks * TICK  # adverse fill
        sell_p = exit_p - spread_ticks * TICK
    else:
        # A moved down → sell B (buy No = buy at 1-entry)
        buy_p = (1 - entry) + spread_ticks * TICK
        sell_p = (1 - exit_p) - spread_ticks * TICK

    gross_profit = (sell_p - buy_p) * fill

    # Fees
    if venue_b == 'kalshi':
        fee = kalshi_fee(buy_p) + kalshi_fee(sell_p)
        net_profit = gross_profit - fee * fill
    else:  # polymarket
        net_profit = gross_profit

    staked = buy_p * fill
    return gross_profit, net_profit, staked

results = {}
for spread_label, spread_ticks in [('0-tick', 0), ('2-tick', 1), ('roll-est', 1.5)]:
    filled_copy = filled.copy()
    pnl = filled_copy.apply(lambda r: compute_pnl(r, spread_ticks), axis=1, result_type='expand')
    filled_copy[['gross', 'net', 'staked']] = pnl

    # PRIMARY CELL: B=Polymarket, pooled
    for venue_b in ['polymarket', 'kalshi']:
        sub = filled_copy[filled_copy['venue_b'] == venue_b]
        if len(sub) == 0: continue

        total_net = sub['net'].sum()
        total_staked = sub['staked'].sum()
        roi = total_net / total_staked if total_staked > 0 else 0
        mean_fill = total_staked / len(sub)
        med_conv = sub['convergence_min'].median()

        # Bootstrap
        fights = sub['fight_id'].unique().tolist()
        fight_bets = {f: sub[sub['fight_id'] == f] for f in fights}
        boot = []
        for _ in range(N_BOOT):
            sf = rng.choice(fights, size=len(fights), replace=True)
            sp = ss = 0
            for f in sf:
                fb = fight_bets[f]
                sp += fb['net'].sum(); ss += fb['staked'].sum()
            boot.append(sp / ss if ss > 0 else 0)
        ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))

        # Capacity
        cards = sub['card_date'].unique()
        if len(cards) > 1:
            span = (pd.Timestamp(max(cards)) - pd.Timestamp(min(cards))).days
            entries_yr = len(sub) * 365 / span if span > 0 else len(sub)
        else:
            entries_yr = len(sub)
        cap = entries_yr * mean_fill * roi

        primary_tag = " *** PRIMARY" if venue_b == 'polymarket' else ""
        print(f"\n  B={venue_b}, spread={spread_label}: n={len(sub)}, "
              f"ROI={roi:+.1%} CI=[{ci[0]:+.1%},{ci[1]:+.1%}], "
              f"med_conv={med_conv:.0f}m, fill=${mean_fill:.0f}, cap=${cap:.0f}/yr{primary_tag}")

        # Tier split
        for tier in ['main_event', 'co_main', 'undercard']:
            ts = sub[sub['tier'] == tier]
            if len(ts) > 0:
                tr = ts['net'].sum() / ts['staked'].sum() if ts['staked'].sum() > 0 else 0
                print(f"    {tier}: n={len(ts)}, ROI={tr:+.1%}")

        # Era split
        for era_label, era_cut in [('pre-2026', lambda d: d < '2026-01-01'), ('post-2026', lambda d: d >= '2026-01-01')]:
            es = sub[sub['card_date'].apply(era_cut)]
            if len(es) > 0:
                er = es['net'].sum() / es['staked'].sum() if es['staked'].sum() > 0 else 0
                print(f"    {era_label}: n={len(es)}, ROI={er:+.1%}")

        # LOCO
        if len(cards) > 1:
            full_roi = roi
            loco_range = []
            for card in sorted(cards):
                loco = sub[sub['card_date'] != card]
                if loco['staked'].sum() > 0:
                    lr = loco['net'].sum() / loco['staked'].sum()
                    loco_range.append(lr)
            if loco_range:
                print(f"    LOCO: [{min(loco_range):+.1%}, {max(loco_range):+.1%}]")

        results[(venue_b, spread_label)] = {
            'n': len(sub), 'roi': roi, 'ci': ci, 'cap': cap,
        }

# ═══════════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("VERDICT")
print("=" * 80)

pm_2tick = results.get(('polymarket', '2-tick'), {})
pm_roll = results.get(('polymarket', 'roll-est'), {})

if pm_2tick and pm_roll:
    ci_ok_2 = pm_2tick['ci'][0] > 0
    ci_ok_r = pm_roll['ci'][0] > 0
    cap_ok = pm_2tick['cap'] >= 100 or pm_roll['cap'] >= 100

    print(f"\nPRIMARY CELL (B=Polymarket, pooled):")
    print(f"  2-tick: ROI={pm_2tick['roi']:+.1%} CI=[{pm_2tick['ci'][0]:+.1%},{pm_2tick['ci'][1]:+.1%}] cap=${pm_2tick['cap']:.0f}/yr")
    print(f"  Roll:   ROI={pm_roll['roi']:+.1%} CI=[{pm_roll['ci'][0]:+.1%},{pm_roll['ci'][1]:+.1%}] cap=${pm_roll['cap']:.0f}/yr")
    print(f"  CI>0 both: {'YES' if ci_ok_2 and ci_ok_r else 'NO'}")
    print(f"  Capacity ≥$100/yr: {'YES' if cap_ok else 'NO'}")

    if ci_ok_2 and ci_ok_r and cap_ok:
        print("\n  → STRATEGY-SIGNAL")
    else:
        print("\n  → STRATEGY-DEAD")
else:
    print("\n  No data in primary cell → STRATEGY-DEAD")

elapsed = time.time() - t0
print(f"\nRuntime: {elapsed:.0f}s")
