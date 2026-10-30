#!/usr/bin/env python3
"""
TASK 1-3: Metric reconciliation — reproduce paper's gap-closure (M1)
inside the backtest machinery, compare with M2 and M3.

PAPER DEFINITION (verbatim from bb5d695:code/exhibit_freeze.py):
  - Bar resolution: 5-min bars from phase2_full_panel.parquet
  - Gap: abs(k_last - pm_last), computed per bar
  - Episode OPENS when: abs_gap crosses UP through GAP_OPEN (0.05 = 5¢)
    on a bar where previous valid bar was < GAP_OPEN
  - Episode CLOSES when: abs_gap falls to <= GAP_CLOSE (0.02 = 2¢)
  - Duration = timestamp difference (open bar → close bar) in minutes
  - If episode never closes by end of data → censored (duration = NaN)
  - ACTIVE type: both venues have ≥1 trade during the episode
  - STALE-SIDE: one venue has zero trades throughout
  - Tier: top-decile combined volume (Kalshi + Polymarket) = "main_event",
    rest = "undercard". Combined volume from crosswalk.
  - Bootstrap: two-stage (per-episode resample), B=1000, seed=42
  - Clock anchor: none (natural bar time). No T-30m cap.
  - PM_FLIP_EXCLUDE: {"20250906_HARFER"} excluded from all analysis
"""
import sys, time, json
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

PM_ROOT = r'C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public'
GAP_OPEN = 0.05; GAP_CLOSE = 0.02
B_BOOT = 1000; SEED = 42
PM_FLIP_EXCLUDE = {"20250906_HARFER"}

rng = np.random.default_rng(SEED)

print("Loading...", flush=True)
panel = pd.read_parquet(f'{PM_ROOT}/data/clean/phase2_full_panel.parquet')
panel['bar_utc'] = pd.to_datetime(panel['bar_utc'], utc=True)

# Exclude pm_flip fight
panel = panel[~panel['fight_id'].isin(PM_FLIP_EXCLUDE)].copy()

# Tier: top-decile combined volume from crosswalk
xw = pd.read_parquet(f'{PM_ROOT}/data/meta/ufc_crosswalk.parquet',
                     columns=['fight_id', 'kalshi_volume', 'pm_volume'])
xw = xw[~xw['fight_id'].isin(PM_FLIP_EXCLUDE)].copy()
xw['combined_vol'] = xw['kalshi_volume'].fillna(0) + xw['pm_volume'].fillna(0)
top_thresh = xw['combined_vol'].quantile(0.90)
xw['tier'] = np.where(xw['combined_vol'] >= top_thresh, 'main_event', 'undercard')
tier_map = xw.set_index('fight_id')['tier'].to_dict()
n_main = (xw['tier'] == 'main_event').sum()
print(f"Tier threshold (90th pct): {top_thresh:,.0f}  ({n_main} main events)")

# Era
era_map = dict(zip(panel['fight_id'], panel['era']))

# ═══════════════════════════════════════════════════════════════════
# TASK 2: Run paper's EXACT gap-closure definition
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TASK 2: Paper gap-closure (M1) on panel data")
print(f"GAP_OPEN={GAP_OPEN}, GAP_CLOSE={GAP_CLOSE}, tier=top-decile volume")
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
    k_n = grp['k_n'].values
    pm_n = grp['pm_n'].values
    valid = grp['k_last'].notna().values & grp['pm_last'].notna().values
    n = len(grp)

    in_ep = False
    ep_start_i = None
    ep_bars_k = []; ep_bars_pm = []

    for i in range(n):
        if not valid[i]:
            if in_ep:
                ep_bars_k.append(0); ep_bars_pm.append(0)
            continue
        ag = abs_g[i]

        if not in_ep:
            prev_ag = None
            for j in range(i - 1, -1, -1):
                if valid[j]: prev_ag = abs_g[j]; break
            if ag >= GAP_OPEN and (prev_ag is None or prev_ag < GAP_OPEN):
                in_ep = True; ep_start_i = i
                ep_bars_k = [int(k_n[i])]
                ep_bars_pm = [int(pm_n[i])]
        else:
            ep_bars_k.append(int(k_n[i]))
            ep_bars_pm.append(int(pm_n[i]))

            if ag <= GAP_CLOSE:
                dur_min = (pd.Timestamp(times[i]) - pd.Timestamp(times[ep_start_i])
                           ).total_seconds() / 60
                k_active = any(v > 0 for v in ep_bars_k)
                pm_active = any(v > 0 for v in ep_bars_pm)
                ep_type = 'ACTIVE' if (k_active and pm_active) else 'STALE-SIDE'
                episodes.append({
                    'fight_id': fid, 'tier': tier_map.get(fid, 'undercard'),
                    'era': era_map.get(fid, '2025_lychee'),
                    'duration_min': dur_min, 'censored': False, 'type': ep_type,
                })
                in_ep = False; ep_bars_k = []; ep_bars_pm = []

    if in_ep:
        k_active = any(v > 0 for v in ep_bars_k)
        pm_active = any(v > 0 for v in ep_bars_pm)
        ep_type = 'ACTIVE' if (k_active and pm_active) else 'STALE-SIDE'
        episodes.append({
            'fight_id': fid, 'tier': tier_map.get(fid, 'undercard'),
            'era': era_map.get(fid, '2025_lychee'),
            'duration_min': np.nan, 'censored': True, 'type': ep_type,
        })

eps_df = pd.DataFrame(episodes)
active = eps_df[(eps_df['type'] == 'ACTIVE') & (~eps_df['censored'])]

print(f"\nTotal episodes: {len(eps_df)}")
print(f"Active closed: {len(active)}")
print(f"Censored: {eps_df['censored'].sum()}")
print(f"STALE-SIDE: {(eps_df['type'] == 'STALE-SIDE').sum()}")

# Bootstrap median CI per tier
for tier in ['main_event', 'undercard']:
    sub = active[active['tier'] == tier]
    if len(sub) == 0:
        print(f"\n  {tier}: n=0")
        continue
    durations = sub['duration_min'].values
    med = np.median(durations)

    # Fight-clustered bootstrap
    fights = sub['fight_id'].unique()
    fight_eps = {f: sub[sub['fight_id'] == f]['duration_min'].values for f in fights}
    boot_meds = []
    for _ in range(B_BOOT):
        sf = rng.choice(fights, size=len(fights), replace=True)
        boot_durs = np.concatenate([fight_eps[f] for f in sf])
        if len(boot_durs) > 0:
            boot_meds.append(np.median(boot_durs))
    ci = (np.percentile(boot_meds, 2.5), np.percentile(boot_meds, 97.5))

    paper_val = 32 if tier == 'main_event' else 118
    inside = ci[0] <= paper_val <= ci[1]
    print(f"\n  {tier}: n={len(sub)}, median={med:.0f} min, CI=[{ci[0]:.0f},{ci[1]:.0f}]")
    print(f"    Paper value ({paper_val}): {'INSIDE CI → PASS' if inside else 'OUTSIDE CI → FAIL'}")

# ═══════════════════════════════════════════════════════════════════
# TASK 3: Three-metric documentation table
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("TASK 3: METRIC DOCUMENTATION TABLE")
print("=" * 80)

# M2: full convergence to ≤1¢ (my first-pass backtest used |B-A| ≤ 1¢ exit)
# This is strictly longer than M1 because:
#   M1 closes at |gap| ≤ 2¢ (looser)
#   M2 closes at |gap| ≤ 1¢ (tighter)
# So M2 ≥ M1 always.

# M3: trade-sim exit clock: |B-A| ≤ 1¢ OR T-30m cap (whichever first)
# M3 ≤ M2 because of the cap. M3 can be < M1 if the T-30m cap fires
# before the gap even reaches 2¢.

# From my convergence backtest: median M3 = 60 min for PM entries
# My first-pass Step 0 showed "195 min" for main events — but that used
# wrong tier assignment. Let me compute M2 with correct tier:

# M2: full convergence to ≤1¢, no time cap, paper tier definition
m2_episodes = []
for fid, grp in df.groupby('fight_id', sort=False):
    grp = grp.sort_values('bar_utc').reset_index(drop=True)
    abs_g = grp['abs_gap'].values
    times = grp['bar_utc'].values
    valid = grp['k_last'].notna().values & grp['pm_last'].notna().values
    k_n_a = grp['k_n'].values; pm_n_a = grp['pm_n'].values
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
                ep_k = [int(k_n_a[i])]; ep_pm = [int(pm_n_a[i])]
        else:
            ep_k.append(int(k_n_a[i])); ep_pm.append(int(pm_n_a[i]))
            if ag <= 0.01:  # M2: ≤1¢ closure
                dur = (pd.Timestamp(times[i]) - pd.Timestamp(times[ep_start_i])).total_seconds() / 60
                k_act = any(v > 0 for v in ep_k)
                pm_act = any(v > 0 for v in ep_pm)
                if k_act and pm_act:
                    m2_episodes.append({
                        'fight_id': fid, 'tier': tier_map.get(fid, 'undercard'),
                        'duration_min': dur,
                    })
                in_ep = False

m2_df = pd.DataFrame(m2_episodes)

print(f"""
| Metric | Definition | Main event | Undercard | Source |
|--------|-----------|-----------|----------|--------|""")

# M1
m1_main = active[active['tier'] == 'main_event']['duration_min']
m1_under = active[active['tier'] == 'undercard']['duration_min']
print(f"| M1: Paper gap-closure | |K-PM| opens ≥5¢, closes ≤2¢, ACTIVE, 5-min bars | "
      f"{m1_main.median():.0f} min (n={len(m1_main)}) | {m1_under.median():.0f} min (n={len(m1_under)}) | "
      f"frozen code bb5d695 |")

# M2
if len(m2_df) > 0:
    m2_main = m2_df[m2_df['tier'] == 'main_event']['duration_min']
    m2_under = m2_df[m2_df['tier'] == 'undercard']['duration_min']
    m2_main_str = f"{m2_main.median():.0f} min (n={len(m2_main)})" if len(m2_main) > 0 else "n=0"
    m2_under_str = f"{m2_under.median():.0f} min (n={len(m2_under)})" if len(m2_under) > 0 else "n=0"
    print(f"| M2: Full convergence | Same open ≥5¢, closes ≤1¢, ACTIVE | "
          f"{m2_main_str} | {m2_under_str} | this script |")
else:
    print(f"| M2: Full convergence | Same open ≥5¢, closes ≤1¢ | n=0 | n=0 | this script |")

# M3: from the convergence backtest (60 min median for PM entries)
print(f"| M3: Trade-sim exit | |B-A|≤1¢ OR T-30m cap, whichever first | — | — | "
      f"crossvenue_convergence.py, median=60 min |")

# Ordering check
print(f"""
Ordering check:
  M1 (≤2¢ closure): main={m1_main.median():.0f}, undercard={m1_under.median():.0f}""")
if len(m2_df) > 0 and len(m2_main) > 0:
    print(f"  M2 (≤1¢ closure): main={m2_main.median():.0f}, undercard={m2_under.median():.0f}")
print(f"  M3 (≤1¢ or T-30m cap): 60 min (censored)")
print(f"\n  Expected: M1 < M2 (tighter threshold = longer)")
print(f"  Expected: M3 ≤ M2 (cap truncates)")
print(f"  M1 < M3 is possible if the cap fires before 2¢ closure")
