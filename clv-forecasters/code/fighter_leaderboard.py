#!/usr/bin/env python3
"""
Fighter leaderboard: most underrated and overrated by the closing line.
Empirical-Bayes shrinkage, min 10 fights.
"""
import sys, re, warnings, functools, unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000
MIN_FIGHTS = 10
K_SHRINK = 8  # shrinkage parameter

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

# ── Load ──
panel = pd.read_csv(r'C:\Research\mma-paper\data\analysis_panel_cc.csv')
panel['date'] = pd.to_datetime(panel['date'])
panel = panel[panel['year'] <= 2025].copy()
panel['excess'] = panel['win'] - panel['p_close_hi']

# Wikidata for region tagging
wiki = pd.read_csv(r'C:\Research\mma-paper\data\wikidata_mma_fighters.csv')
wiki_lookup = {}
for _, row in wiki.iterrows():
    nn = norm_name(row['name'])
    if nn not in wiki_lookup or (str(row.get('lat','')).strip() not in ('', 'nan')):
        wiki_lookup[nn] = row.to_dict()

matched = {}
for f in set(panel['fighter'].unique()):
    nn = norm_name(f)
    if nn in wiki_lookup:
        matched[f] = wiki_lookup[nn]
    else:
        parts = nn.split()
        if len(parts) >= 2:
            rev = ' '.join(parts[1:] + parts[:1])
            if rev in wiki_lookup:
                matched[f] = wiki_lookup[rev]

def get_country(f):
    d = matched.get(f, {})
    return d.get('country', '?')

# ── Per-fighter stats ──
fighters = []
for fighter, grp in panel.groupby('fighter'):
    n = len(grp)
    if n < MIN_FIGHTS:
        continue
    wins = grp['win'].sum()
    losses = n - wins
    wr = grp['win'].mean()
    mkt = grp['p_close_hi'].mean()
    raw_excess = wr - mkt
    shrunk = raw_excess * n / (n + K_SHRINK)

    # Bootstrap CI on raw excess
    exc_vals = grp['excess'].values
    boots = [exc_vals[rng.choice(n, n, True)].mean() for _ in range(N_BOOT)]
    lo, hi = np.percentile(boots, [2.5, 97.5])

    # Biggest upset (for underrated): largest positive excess in a single fight
    best_fight = grp.loc[grp['excess'].idxmax()]
    # Biggest fav loss (for overrated): largest negative excess in a single fight
    worst_fight = grp.loc[grp['excess'].idxmin()]

    fighters.append({
        'fighter': fighter, 'n': n, 'wins': int(wins), 'losses': int(losses),
        'record': f"{int(wins)}-{int(losses)}",
        'mkt': mkt, 'wr': wr,
        'raw_excess': raw_excess, 'shrunk': shrunk,
        'ci_lo': lo, 'ci_hi': hi,
        'country': get_country(fighter),
        'best_opp': best_fight['opponent'],
        'best_mkt': best_fight['p_close_hi'],
        'best_won': int(best_fight['win']),
        'worst_opp': worst_fight['opponent'],
        'worst_mkt': worst_fight['p_close_hi'],
        'worst_won': int(worst_fight['win']),
    })

df = pd.DataFrame(fighters)

# ═══════════════════════════════════════════════════════════════════
# TOP 10 UNDERRATED
# ═══════════════════════════════════════════════════════════════════
print(f"{'='*120}")
print("TOP 10 MOST UNDERRATED FIGHTERS (market kept underrating them)")
print(f"Ranked by empirical-Bayes shrunken excess, min {MIN_FIGHTS} fights, k={K_SHRINK}")
print(f"{'='*120}")

under = df.nlargest(10, 'shrunk')

print(f"\n  {'#':>2} {'Fighter':<25s} {'Country':<15s} {'N':>3} {'Rec':>6} {'Mkt':>5} {'WR':>5} "
      f"{'Raw':>6} {'Shrunk':>6} {'95% CI':>17} {'Biggest upset'}")
print("  " + "-" * 130)

for i, (_, r) in enumerate(under.iterrows(), 1):
    ci = f"[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}]"
    # Biggest upset: won as biggest underdog
    if r['best_won'] == 1:
        upset = f"beat {r['best_opp'][:18]} at {r['best_mkt']:.0%}"
    else:
        # Find their biggest win-as-underdog
        fg = panel[(panel['fighter'] == r['fighter']) & (panel['win'] == 1)]
        if len(fg) > 0:
            biggest = fg.loc[fg['p_close_hi'].idxmin()]
            upset = f"beat {biggest['opponent'][:18]} at {biggest['p_close_hi']:.0%}"
        else:
            upset = "no wins"
    print(f"  {i:>2} {r['fighter'][:24]:<25s} {r['country'][:14]:<15s} {r['n']:>3} {r['record']:>6} "
          f"{r['mkt']:>4.0%} {r['wr']:>4.0%} {r['raw_excess']:>+5.3f} {r['shrunk']:>+5.3f} "
          f"{ci:>17} {upset}")

# ═══════════════════════════════════════════════════════════════════
# TOP 10 OVERRATED
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*120}")
print("TOP 10 MOST OVERRATED FIGHTERS (market kept overrating them)")
print(f"{'='*120}")

over = df.nsmallest(10, 'shrunk')

print(f"\n  {'#':>2} {'Fighter':<25s} {'Country':<15s} {'N':>3} {'Rec':>6} {'Mkt':>5} {'WR':>5} "
      f"{'Raw':>6} {'Shrunk':>6} {'95% CI':>17} {'Biggest fav loss'}")
print("  " + "-" * 130)

for i, (_, r) in enumerate(over.iterrows(), 1):
    ci = f"[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}]"
    # Biggest favorite loss: lost as biggest favorite
    if r['worst_won'] == 0:
        floss = f"lost to {r['worst_opp'][:18]} at {r['worst_mkt']:.0%}"
    else:
        fg = panel[(panel['fighter'] == r['fighter']) & (panel['win'] == 0)]
        if len(fg) > 0:
            biggest = fg.loc[fg['p_close_hi'].idxmax()]
            floss = f"lost to {biggest['opponent'][:18]} at {biggest['p_close_hi']:.0%}"
        else:
            floss = "no losses"
    print(f"  {i:>2} {r['fighter'][:24]:<25s} {r['country'][:14]:<15s} {r['n']:>3} {r['record']:>6} "
          f"{r['mkt']:>4.0%} {r['wr']:>4.0%} {r['raw_excess']:>+5.3f} {r['shrunk']:>+5.3f} "
          f"{ci:>17} {floss}")

# ═══════════════════════════════════════════════════════════════════
# PATTERN ANALYSIS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("PATTERN ANALYSIS")
print(f"{'='*80}")

print(f"\n  UNDERRATED — country/region breakdown:")
for country, cnt in under['country'].value_counts().items():
    names = under[under['country'] == country]['fighter'].tolist()
    print(f"    {country}: {cnt} ({', '.join(n[:20] for n in names)})")

print(f"\n  OVERRATED — country/region breakdown:")
for country, cnt in over['country'].value_counts().items():
    names = over[over['country'] == country]['fighter'].tolist()
    print(f"    {country}: {cnt} ({', '.join(n[:20] for n in names)})")

# Style proxy: are underrated fighters more wrestling-heavy?
fights_raw = pd.read_csv(r'C:\Research\mma-paper\data\ufcstats_fights.csv')
fighter_td = defaultdict(lambda: {'td': 0, 'ctrl': 0, 'n': 0})
for _, row in fights_raw.iterrows():
    try:
        fighter_td[row['fighter_name']]['td'] += int(row['td_landed']) if pd.notna(row['td_landed']) else 0
        fighter_td[row['fighter_name']]['ctrl'] += int(row['ctrl_sec']) if pd.notna(row['ctrl_sec']) else 0
        fighter_td[row['fighter_name']]['n'] += 1
    except:
        pass

def wrestling_score(name):
    s = fighter_td.get(name, {'td': 0, 'ctrl': 0, 'n': 0})
    if s['n'] == 0:
        return 0
    return s['td'] / s['n'] + s['ctrl'] / s['n'] / 60

under_wrestling = [wrestling_score(r['fighter']) for _, r in under.iterrows()]
over_wrestling = [wrestling_score(r['fighter']) for _, r in over.iterrows()]
all_wrestling = [wrestling_score(r['fighter']) for _, r in df.iterrows()]

print(f"\n  Wrestling score (TD/fight + ctrl_min/fight):")
print(f"    Underrated avg: {np.mean(under_wrestling):.1f}")
print(f"    Overrated avg:  {np.mean(over_wrestling):.1f}")
print(f"    All fighters:   {np.mean(all_wrestling):.1f}")

# ═══════════════════════════════════════════════════════════════════
# EZOTERYKA CHECK
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("EZOTERYKA CHECK")
print(f"{'='*80}")

import os, csv
ezo_path = r'C:\Research\ufc\picks\users\Ezoteryka.csv'
if os.path.exists(ezo_path):
    with open(ezo_path, encoding='utf-8') as f:
        ezo_picks = list(csv.DictReader(f))

    ezo_fighters = set()
    ezo_correct = defaultdict(list)
    for p in ezo_picks:
        fp = p['fighter_picked']
        ezo_fighters.add(norm_name(fp))
        ezo_correct[norm_name(fp)].append(p.get('correct', '') == 'YES')

    under_names = set(norm_name(r['fighter']) for _, r in under.iterrows())
    over_names = set(norm_name(r['fighter']) for _, r in over.iterrows())

    print(f"\n  Underrated fighters I correctly backed:")
    for _, r in under.iterrows():
        nn = norm_name(r['fighter'])
        if nn in ezo_fighters:
            picks = ezo_correct[nn]
            correct = sum(picks)
            total = len(picks)
            print(f"    {r['fighter'][:25]:<26s} picked {total}x, correct {correct}/{total}")

    print(f"\n  Underrated fighters I never picked:")
    for _, r in under.iterrows():
        nn = norm_name(r['fighter'])
        if nn not in ezo_fighters:
            print(f"    {r['fighter']}")

    print(f"\n  Overrated fighters I wrongly trusted:")
    for _, r in over.iterrows():
        nn = norm_name(r['fighter'])
        if nn in ezo_fighters:
            picks = ezo_correct[nn]
            correct = sum(picks)
            total = len(picks)
            print(f"    {r['fighter'][:25]:<26s} picked {total}x, correct {correct}/{total}")

    print(f"\n  Overrated fighters I correctly avoided:")
    for _, r in over.iterrows():
        nn = norm_name(r['fighter'])
        if nn not in ezo_fighters:
            print(f"    {r['fighter']}")
else:
    print("  Ezoteryka picks file not found")
