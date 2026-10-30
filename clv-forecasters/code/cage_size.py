#!/usr/bin/env python3
"""
Octagon-size test: does the 25ft Apex cage change fights and market pricing?
Two-stage: validate mechanism from fight stats, then test market pricing.
"""
import sys, re, warnings, functools
import numpy as np
import pandas as pd
from collections import defaultdict
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.metrics import brier_score_loss

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

# ═══════════════════════════════════════════════════════════════════
# STAGE 0: BUILD CAGE-SIZE FLAG
# ═══════════════════════════════════════════════════════════════════
print(f"{'='*80}")
print("STAGE 0: VENUE LOOKUP — CAGE SIZE FLAG")
print(f"{'='*80}")

events = pd.read_csv(r'C:\Research\mma-paper\data\ufcstats_events.csv')
events['date'] = pd.to_datetime(events['date'], format='mixed')
fights = pd.read_csv(r'C:\Research\mma-paper\data\ufcstats_fights.csv')
fights['date'] = pd.to_datetime(fights['date'], format='mixed')

# UFC Apex opened in Las Vegas, first event May 30 2020.
# ALL Fight Nights at Apex use the 25ft cage.
# PPVs at Apex during COVID (2020-mid 2021) also used 25ft cage.
# Post-COVID PPVs in Las Vegas use T-Mobile Arena (30ft).
# The transition back to big arenas for PPVs was ~UFC 264 (Jul 2021).

# Rule: Las Vegas event + date >= 2020-05-30 + Fight Night = small cage (Apex)
# Las Vegas PPVs 2020-05-30 through ~2021-06-12 = small cage (Apex, COVID era)
# Las Vegas PPVs after UFC 264 (2021-07-10) = big cage (T-Mobile)
# Exception: UFC 306 "Noche UFC" at the Sphere (Sep 2024) = big cage (custom 30ft)

# Non-LV small-cage events: none confirmed. International Fight Nights
# at small venues sometimes use smaller octagons, but this is poorly documented.
# Conservative: only flag confirmed Apex events.

COVID_PPV_END = pd.Timestamp('2021-07-01')  # PPVs returned to arenas around UFC 264
APEX_START = pd.Timestamp('2020-05-30')

def classify_cage(event_name, event_date, location):
    if 'Las Vegas' not in str(location):
        return 'big'  # non-LV = big cage (conservative)
    if event_date < APEX_START:
        return 'big'  # pre-Apex
    is_fn = 'Fight Night' in event_name or 'UFC on' in event_name
    if is_fn:
        return 'small'  # all LV Fight Nights post-Apex = Apex
    # PPV in Las Vegas
    if event_date <= COVID_PPV_END:
        return 'small'  # COVID-era PPV at Apex
    return 'big'  # post-COVID PPV at arena

events['cage'] = events.apply(lambda r: classify_cage(r['event_name'], r['date'], r['location']), axis=1)

# Empty-arena flag: COVID era, roughly May 2020 - April 2021
# UFC had limited/no crowds at Apex through early-mid 2021
# Full crowds returned ~UFC 261 (April 24 2021) in Jacksonville, then gradually to Apex
EMPTY_START = pd.Timestamp('2020-05-30')
EMPTY_END = pd.Timestamp('2021-05-15')  # conservative; some events had limited crowds earlier
events['empty_arena'] = ((events['date'] >= EMPTY_START) & (events['date'] <= EMPTY_END)).astype(int)

# Map to fights
event_cage_map = dict(zip(events['event_url'], events['cage']))
event_empty_map = dict(zip(events['event_url'], events['empty_arena']))
fights['cage'] = fights['event_url'].map(event_cage_map).fillna('big')
fights['empty_arena'] = fights['event_url'].map(event_empty_map).fillna(0).astype(int)

small_events = events[events['cage'] == 'small']
big_events = events[events['cage'] == 'big']
print(f"\n  Small-cage events: {len(small_events)}")
print(f"  Big-cage events:   {len(big_events)}")
print(f"  Empty-arena events: {events['empty_arena'].sum()}")

small_fights = fights[fights['cage'] == 'small']
big_fights = fights[fights['cage'] == 'big']
# Fights are double-counted (2 rows per fight), divide by 2 for bout count
print(f"\n  Small-cage fight-rows: {len(small_fights)} (~{len(small_fights)//2} bouts)")
print(f"  Big-cage fight-rows:   {len(big_fights)} (~{len(big_fights)//2} bouts)")

# ═══════════════════════════════════════════════════════════════════
# STAGE 1: MECHANISM VALIDATION — DOES THE CAGE CHANGE THE FIGHT?
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("STAGE 1: MECHANISM VALIDATION")
print("Does the small cage physically change fight dynamics?")
print(f"{'='*80}")

# Only use winner rows (result == 'W') to avoid double-counting methods
# But for per-fighter stats, use all rows
# For finish rate: use one row per fight (winner row)

winner_rows = fights[fights['result'] == 'W'].copy()
winner_rows['is_finish'] = winner_rows['method'].apply(
    lambda m: 0 if 'DEC' in str(m).upper() else 1)

# Parse numeric columns safely
for col in ['td_landed', 'td_att', 'ctrl_sec', 'sig_str_landed', 'sig_str_att',
            'total_str_landed', 'total_str_att', 'kd', 'sub_att']:
    fights[col] = pd.to_numeric(fights[col], errors='coerce')

# Per-fighter-per-fight stats (all rows, not just winners)
# Normalize to per-15-minutes using round and time
def parse_fight_duration(row):
    """Total fight duration in minutes from round + time."""
    try:
        rd = int(row['round'])
        parts = str(row['time']).split(':')
        mins = int(parts[0])
        secs = int(parts[1]) if len(parts) > 1 else 0
        return (rd - 1) * 5 + mins + secs / 60
    except:
        return None

winner_rows['duration_min'] = winner_rows.apply(parse_fight_duration, axis=1)
# Map duration to all fight rows via fight_url
fight_duration = dict(zip(winner_rows['fight_url'], winner_rows['duration_min']))
fights['duration_min'] = fights['fight_url'].map(fight_duration)

# Filter to post-2020 (when small cage exists) for fair comparison
modern = fights[(fights['date'] >= '2020-05-30') & (fights['date'] <= '2025-12-31')].copy()
modern = modern[modern['duration_min'].notna() & (modern['duration_min'] > 0)].copy()

# Per-15-min rates
modern['td_landed_r'] = modern['td_landed'] / modern['duration_min'] * 15
modern['td_att_r'] = modern['td_att'] / modern['duration_min'] * 15
modern['ctrl_sec_r'] = modern['ctrl_sec'] / modern['duration_min'] * 15
modern['sig_str_r'] = modern['sig_str_landed'] / modern['duration_min'] * 15

# Fight-level stats (average both fighters per bout)
bout_stats = modern.groupby(['fight_url', 'cage', 'empty_arena']).agg({
    'td_landed_r': 'sum',  # total TDs in fight
    'td_att_r': 'sum',
    'ctrl_sec_r': 'sum',  # total control time
    'sig_str_r': 'sum',
}).reset_index()

# Finish rate from winner rows
modern_winners = winner_rows[(winner_rows['date'] >= '2020-05-30') &
                              (winner_rows['date'] <= '2025-12-31')].copy()
finish_by_cage = modern_winners.groupby('cage')['is_finish'].agg(['mean', 'count'])

print(f"\n  Fight stats comparison (2020-2025, per 15 min, fight-level sums):")
print(f"  Excluding empty-arena era for clean comparison:")

# Exclude empty arena for the clean comparison
clean_bouts = bout_stats[bout_stats['empty_arena'] == 0]
clean_winners = modern_winners[modern_winners['empty_arena'] == 0]

metrics = [
    ('Finish rate', 'is_finish', clean_winners, 'cage', True),
]

print(f"\n  {'Metric':<25s} {'Small cage':>12s} {'Big cage':>12s} {'Diff':>8s} {'95% CI':>18s} {'Sig':>4s}")
print("  " + "-" * 82)

stage1_pass = False

# Finish rate
for cage_val, label in [('small', 'Small'), ('big', 'Big')]:
    pass

small_w = clean_winners[clean_winners['cage'] == 'small']
big_w = clean_winners[clean_winners['cage'] == 'big']
fin_s = small_w['is_finish'].mean()
fin_b = big_w['is_finish'].mean()
diff_fin = fin_s - fin_b
# Bootstrap
boots = []
for _ in range(N_BOOT):
    bs = small_w['is_finish'].values[rng.choice(len(small_w), len(small_w), True)].mean()
    bb = big_w['is_finish'].values[rng.choice(len(big_w), len(big_w), True)].mean()
    boots.append(bs - bb)
lo, hi = np.percentile(boots, [2.5, 97.5])
sig = 'YES' if (lo > 0 or hi < 0) else 'no'
print(f"  {'Finish rate':<25s} {fin_s:>11.1%} {fin_b:>11.1%} {diff_fin:>+7.1%} [{lo:>+.3f},{hi:>+.3f}] {sig:>4s}")
print(f"  {'  (N bouts)':<25s} {len(small_w):>12} {len(big_w):>12}")
if sig == 'YES':
    stage1_pass = True

# Per-fight stats
clean_s = clean_bouts[clean_bouts['cage'] == 'small']
clean_b = clean_bouts[clean_bouts['cage'] == 'big']

for metric_name, col in [('TD landed / 15min', 'td_landed_r'),
                           ('TD attempted / 15min', 'td_att_r'),
                           ('Control time (s) / 15min', 'ctrl_sec_r'),
                           ('Sig strikes / 15min', 'sig_str_r')]:
    vs = clean_s[col].dropna().values
    vb = clean_b[col].dropna().values
    ms, mb = vs.mean(), vb.mean()
    diff = ms - mb
    boots = []
    for _ in range(N_BOOT):
        bs = vs[rng.choice(len(vs), len(vs), True)].mean()
        bb = vb[rng.choice(len(vb), len(vb), True)].mean()
        boots.append(bs - bb)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    sig = 'YES' if (lo > 0 or hi < 0) else 'no'
    print(f"  {metric_name:<25s} {ms:>12.1f} {mb:>12.1f} {diff:>+8.1f} [{lo:>+.1f},{hi:>+.1f}] {sig:>4s}")
    if sig == 'YES':
        stage1_pass = True

# Also show WITH empty arena for completeness
print(f"\n  Including empty-arena era (for reference):")
all_s = bout_stats[bout_stats['cage'] == 'small']
all_b = bout_stats[bout_stats['cage'] == 'big']
all_sw = modern_winners[modern_winners['cage'] == 'small']
all_bw = modern_winners[modern_winners['cage'] == 'big']

fin_s_all = all_sw['is_finish'].mean()
fin_b_all = all_bw['is_finish'].mean()
print(f"  Finish rate: small={fin_s_all:.1%} (N={len(all_sw)}), big={fin_b_all:.1%} (N={len(all_bw)}), diff={fin_s_all-fin_b_all:+.1%}")
for metric_name, col in [('TD landed/15', 'td_landed_r'), ('Ctrl time(s)/15', 'ctrl_sec_r'),
                           ('Sig str/15', 'sig_str_r')]:
    print(f"  {metric_name}: small={all_s[col].mean():.1f}, big={all_b[col].mean():.1f}, diff={all_s[col].mean()-all_b[col].mean():+.1f}")


# ═══════════════════════════════════════════════════════════════════
# STAGE 1 VERDICT
# ═══════════════════════════════════════════════════════════════════
print(f"\n  STAGE 1 VERDICT: {'MECHANISM VALIDATED -- proceed to Stage 2' if stage1_pass else 'NO MECHANISM DETECTED -- STOP. Cage size does not measurably change fight dynamics.'}")

if not stage1_pass:
    print(f"\n  The small cage does not significantly alter finish rate, takedowns,")
    print(f"  control time, or striking rate vs the big cage (excluding empty-arena era).")
    print(f"  Without a physical mechanism, a market-pricing test is pointless.")
    print(f"  STOPPING.")
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════════
# STAGE 2: MARKET PRICING
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("STAGE 2: MARKET PRICING")
print(f"{'='*80}")

panel = pd.read_csv(r'C:\Research\mma-paper\data\analysis_panel_cc.csv')
panel['date'] = pd.to_datetime(panel['date'])

# Map cage size to panel via fight_url -> event_url -> cage
fight_to_event = dict(zip(fights['fight_url'], fights['event_url']))
panel['event_url'] = panel['fight_url'].map(fight_to_event)
event_cage = dict(zip(events['event_url'], events['cage']))
event_empty = dict(zip(events['event_url'], events['empty_arena']))
panel['cage'] = panel['event_url'].map(event_cage).fillna('big')
panel['empty_arena'] = panel['event_url'].map(event_empty).fillna(0).astype(int)

# Build style proxy per fighter: expanding-window grappling index
# From ufcstats fights, compute career-average TD rate + control time
print("\nBuilding style proxies...")
fighter_style_cum = defaultdict(lambda: {'td_l': 0, 'td_a': 0, 'ctrl': 0, 'sig_l': 0, 'n': 0})

style_at_fight = {}
for _, row in fights.sort_values('date').iterrows():
    fighter = row['fighter_name']
    fight_url = row['fight_url']

    # Record CURRENT cumulative style BEFORE this fight
    s = fighter_style_cum[fighter]
    if s['n'] > 0:
        grapple = s['td_l'] / s['n'] + s['ctrl'] / s['n'] / 60
        strike = s['sig_l'] / s['n']
        style_at_fight[(fighter, fight_url)] = {'grapple': grapple, 'strike': strike}
    else:
        style_at_fight[(fighter, fight_url)] = {'grapple': 0, 'strike': 0}

    # Update cumulative
    try:
        s['td_l'] += int(row['td_landed']) if pd.notna(row['td_landed']) else 0
        s['ctrl'] += int(row['ctrl_sec']) if pd.notna(row['ctrl_sec']) else 0
        s['sig_l'] += int(row['sig_str_landed']) if pd.notna(row['sig_str_landed']) else 0
        s['td_a'] += int(row['td_att']) if pd.notna(row['td_att']) else 0
    except (ValueError, TypeError):
        pass
    s['n'] += 1

# Build bout-level dataset for market test
paired = panel.groupby('fight_id').filter(lambda x: len(x) == 2)
paired_post_apex = paired[paired['date'] >= APEX_START].copy()
paired_post_apex = paired_post_apex[paired_post_apex['date'].dt.year <= 2025]

bouts_mkt = []
for fid, grp in paired_post_apex.groupby('fight_id'):
    grp = grp.sort_values('fighter')
    r1, r2 = grp.iloc[0], grp.iloc[1]
    cage = r1['cage']
    empty = r1['empty_arena']

    # Style for each fighter
    s1 = style_at_fight.get((r1['fighter'], r1['fight_url']), {'grapple': 0, 'strike': 0})
    s2 = style_at_fight.get((r2['fighter'], r2['fight_url']), {'grapple': 0, 'strike': 0})
    # Avoid division by zero
    denom1 = max(s1['grapple'] + s1['strike'], 0.01)
    denom2 = max(s2['grapple'] + s2['strike'], 0.01)
    # Grappling share: grapple / (grapple + strike)
    grap_share_a = s1['grapple'] / denom1
    grap_share_b = s2['grapple'] / denom2
    style_diff = grap_share_a - grap_share_b  # positive = a is more grappling-oriented

    bouts_mkt.append({
        'fight_id': fid, 'date': r1['date'], 'year': r1['year'],
        'fa': r1['fighter'], 'fb': r1['opponent'],
        'p_mkt_a': r1['p_close_hi'], 'win_a': int(r1['win']),
        'cage': cage, 'small': 1 if cage == 'small' else 0,
        'empty': empty,
        'style_diff': style_diff,
        'grap_a': grap_share_a, 'grap_b': grap_share_b,
    })

bm = pd.DataFrame(bouts_mkt).sort_values('date').reset_index(drop=True)
bm['excess'] = bm['win_a'] - bm['p_mkt_a']

# Exclude empty-arena for clean test
bm_clean = bm[bm['empty'] == 0].copy()

print(f"\n  Post-Apex bouts (excl empty-arena): {len(bm_clean)}")
print(f"    Small cage: {bm_clean['small'].sum()}")
print(f"    Big cage: {(~bm_clean['small'].astype(bool)).sum()}")

# 2a. Main effect: small cage alone
print(f"\n  2a. MAIN EFFECT: small_cage alone, net of closing line")
small_exc = bm_clean[bm_clean['small'] == 1]['excess'].mean()
big_exc = bm_clean[bm_clean['small'] == 0]['excess'].mean()
diff_exc = small_exc - big_exc
boots = []
s_vals = bm_clean[bm_clean['small'] == 1]['excess'].values
b_vals = bm_clean[bm_clean['small'] == 0]['excess'].values
for _ in range(N_BOOT):
    bs = s_vals[rng.choice(len(s_vals), len(s_vals), True)].mean()
    bb = b_vals[rng.choice(len(b_vals), len(b_vals), True)].mean()
    boots.append(bs - bb)
lo, hi = np.percentile(boots, [2.5, 97.5])
sig = 'YES' if (lo > 0 or hi < 0) else 'no'
print(f"    Small excess: {small_exc:+.3f}, Big excess: {big_exc:+.3f}")
print(f"    Diff: {diff_exc:+.3f} [{lo:+.3f}, {hi:+.3f}] sig={sig}")

# 2b. THE INTERACTION: small_cage x style_differential
print(f"\n  2b. INTERACTION: small_cage x style_diff, net of market")
print(f"  (Does the more grappling-oriented fighter beat the market MORE in small cages?)")

def neg_ll(params, X_list, y):
    z = params[0]
    for i, x in enumerate(X_list):
        z = z + params[i+1] * x
    p = np.clip(expit(z), 1e-10, 1-1e-10)
    return -np.sum(y * np.log(p) + (1-y) * np.log(1-p))

y_c = bm_clean['win_a'].values
interaction = bm_clean['small'].values * bm_clean['style_diff'].values

X_int = [bm_clean['p_mkt_a'].values, bm_clean['style_diff'].values,
         bm_clean['small'].values.astype(float), interaction]
labels_int = ['mkt_prob', 'style_diff', 'small_cage', 'small x style']

res_int = minimize(neg_ll, [0]*(1+len(X_int)), args=(X_int, y_c),
                   method='Nelder-Mead', options={'maxiter': 10000})

print(f"\n    Logistic coefficients:")
print(f"      intercept:     {res_int.x[0]:+.4f}")
for i, l in enumerate(labels_int):
    print(f"      {l:<16s} {res_int.x[i+1]:+.4f}")

# Bootstrap CI on the interaction coefficient
print(f"    Bootstrapping interaction (N={N_BOOT})...")
n_c = len(y_c)
int_boots = []
for _ in range(N_BOOT):
    bi = rng.choice(n_c, n_c, replace=True)
    yb = y_c[bi]
    Xb = [x[bi] for x in X_int]
    try:
        rb = minimize(neg_ll, list(res_int.x), args=(Xb, yb),
                      method='Nelder-Mead', options={'maxiter': 3000, 'xatol': 1e-3, 'fatol': 1e-3})
        int_boots.append(rb.x[4])  # small x style
    except:
        pass
int_boots = np.array(int_boots)
lo_i, hi_i = np.percentile(int_boots, [2.5, 97.5])
sig_i = 'YES' if (lo_i > 0 or hi_i < 0) else 'no'
print(f"    small x style: {res_int.x[4]:+.4f} [{lo_i:+.4f}, {hi_i:+.4f}] sig={sig_i}")

# 2c. Robustness: Fight Night vs Fight Night only
print(f"\n  2c. ROBUSTNESS: Fight Night vs Fight Night (tier-matched)")
# All small-cage events are Fight Nights (post-COVID). Filter big-cage to FN only.
fn_events = events[events['event_name'].str.contains('Fight Night', na=False)]['event_url'].tolist()
bm_fn = bm_clean[bm_clean.apply(lambda r: r['small'] == 1 or
                                  panel[panel['fight_id'] == r['fight_id']].iloc[0]['event_url'] in fn_events
                                  if len(panel[panel['fight_id'] == r['fight_id']]) > 0 else False, axis=1)].copy()
# Simpler: just check if the fight's event is a Fight Night
fight_event_map = dict(zip(panel['fight_id'], panel['event_url']))
bm_clean['event_url'] = bm_clean['fight_id'].map(fight_event_map)
bm_clean['is_fn'] = bm_clean['event_url'].isin(fn_events).astype(int)
bm_fn = bm_clean[(bm_clean['small'] == 1) | (bm_clean['is_fn'] == 1)].copy()

fn_small_exc = bm_fn[bm_fn['small'] == 1]['excess'].mean()
fn_big_exc = bm_fn[bm_fn['small'] == 0]['excess'].mean()
print(f"    FN-only: small excess={fn_small_exc:+.3f} (N={bm_fn['small'].sum()}), "
      f"big excess={fn_big_exc:+.3f} (N={(~bm_fn['small'].astype(bool)).sum()}), "
      f"diff={fn_small_exc - fn_big_exc:+.3f}")

# Re-run including empty arena
print(f"\n  2c. Including empty-arena era:")
bm_all = bm.copy()
y_all = bm_all['win_a'].values
int_all = bm_all['small'].values * bm_all['style_diff'].values
X_all = [bm_all['p_mkt_a'].values, bm_all['style_diff'].values,
         bm_all['small'].values.astype(float), int_all,
         bm_all['empty'].values.astype(float)]
labels_all = ['mkt_prob', 'style_diff', 'small_cage', 'small x style', 'empty_arena']
res_all = minimize(neg_ll, [0]*(1+len(X_all)), args=(X_all, y_all),
                   method='Nelder-Mead', options={'maxiter': 10000})
print(f"    With empty_arena control:")
for i, l in enumerate(labels_all):
    print(f"      {l:<16s} {res_all.x[i+1]:+.4f}")


# ═══════════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VERDICT")
print(f"{'='*80}")

print(f"""
  STAGE 1 (mechanism):
    Does the small cage change fight dynamics? {'YES' if stage1_pass else 'NO'}
    Key shifts (small vs big, excl empty-arena):
      Finish rate: {fin_s:.1%} vs {fin_b:.1%} ({fin_s-fin_b:+.1%})

  STAGE 2 (market pricing):
    2a. Main effect (small cage): {diff_exc:+.3f} [{lo:+.3f},{hi:+.3f}] -- {'significant' if sig == 'YES' else 'null'}
    2b. Interaction (small x style): {res_int.x[4]:+.4f} [{lo_i:+.4f},{hi_i:+.4f}] -- {'significant' if sig_i == 'YES' else 'null'}

  INTERPRETATION:
    {'The cage changes fight dynamics but the market prices it.' if stage1_pass and sig_i == 'no' else
     'The cage changes fights AND the style interaction is unpriced.' if stage1_pass and sig_i == 'YES' else
     'No mechanism detected. Nothing to price.'}
""")
