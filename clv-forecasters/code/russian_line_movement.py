#!/usr/bin/env python3
"""
Line movement test: do ethnic-Russian fighters lose value between open and close?
If sentiment-driven money flows against them, closing odds should be worse than opening.
"""
import sys, re, warnings, functools, unicodedata, math
import numpy as np
import pandas as pd
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')
print = functools.partial(print, flush=True)
SEED = 67; rng = np.random.RandomState(SEED); N_BOOT = 2000

def norm_name(n):
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c))
    return re.sub(r'[^\w\s]', '', s.strip().lower()).strip()

def american_to_prob(odds):
    """Convert American odds to implied probability (with vig)."""
    if odds is None or math.isnan(odds):
        return None
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return -odds / (-odds + 100)

def devig_pair(p1, p2):
    """Simple multiplicative de-vig."""
    total = p1 + p2
    if total <= 0:
        return None, None
    return p1 / total, p2 / total

# ── Load data ──
wiki = pd.read_csv(r'C:\Research\mma-paper\data\wikidata_mma_fighters.csv')
wiki_lookup = {}
for _, row in wiki.iterrows():
    nn = norm_name(row['name'])
    if nn not in wiki_lookup or (str(row.get('lat','')).strip() not in ('', 'nan')):
        wiki_lookup[nn] = row.to_dict()

panel = pd.read_csv(r'C:\Research\mma-paper\data\analysis_panel_cc.csv')
panel['date'] = pd.to_datetime(panel['date'])

bfo = pd.read_csv(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\bfo_odds_raw.csv')

ufc_fighters = set(panel['fighter'].unique()) | set(panel['opponent'].unique())
matched = {}
for f in ufc_fighters:
    nn = norm_name(f)
    if nn in wiki_lookup:
        matched[f] = wiki_lookup[nn]
    else:
        parts = nn.split()
        if len(parts) >= 2:
            rev = ' '.join(parts[1:] + parts[:1])
            if rev in wiki_lookup:
                matched[f] = wiki_lookup[rev]

def assign_region(fighter_name):
    d = matched.get(fighter_name, {})
    country = d.get('country', '')
    if not country:
        return None
    if country == 'Russia':
        try:
            lat, lon = float(d.get('lat', 0)), float(d.get('lon', 0))
            if 41 < lat < 45 and 43 < lon < 49:
                return 'Caucasus'
        except (ValueError, TypeError):
            pass
        bp = str(d.get('birthplace', '')).lower()
        cauc = ['dagestan','chechnya','chechen','grozny','makhachkala','ingush',
                'kabardino','ossetia','nalchik','khasavyurt','buynaksk','derbent',
                'kizlyar','kaspiysk','kizilyurt','sildi','sunzha','teletl',
                'vladikavkaz','babugent','goksuv','batayurt','gvardeyskoe',
                'achkhoy','aymaki','dylym','madzhalis','mekegi','kasumkent','kamysh-kutan']
        if any(m in bp for m in cauc):
            return 'Caucasus'
        return 'Russia (ethnic)'
    if country == 'United States':
        return 'USA'
    return 'Other'

# ── Build BFO lookup: norm(fighter) + norm(opponent) -> row ──
# BFO has one row per fighter, so both sides are represented
bfo_lookup = {}
for _, row in bfo.iterrows():
    fn = norm_name(row['fighter_name'])
    on = norm_name(row['opponent_name'])
    bfo_lookup[(fn, on)] = row

# ── Match ethnic-Russian post-war fights to BFO ──
print("Matching ethnic-Russian post-war fights to BFO opening/closing odds...")

eth_rus_panel = panel[panel['date'] >= '2022-02-24']
eth_rus_panel = eth_rus_panel[eth_rus_panel['year'] <= 2025]

# Get ethnic Russian fighters
eth_rus_fighters = set()
for f in ufc_fighters:
    if assign_region(f) == 'Russia (ethnic)':
        eth_rus_fighters.add(f)

eth_rows = eth_rus_panel[eth_rus_panel['fighter'].isin(eth_rus_fighters)].copy()
print(f"  Ethnic Russian post-war panel rows: {len(eth_rows)}")

results = []
for _, r in eth_rows.sort_values('date').iterrows():
    fighter = r['fighter']
    opponent = r['opponent']
    fn = norm_name(fighter)
    on = norm_name(opponent)

    # Try both orderings in BFO
    bfo_row = bfo_lookup.get((fn, on))
    flipped = False
    if bfo_row is None:
        bfo_row = bfo_lookup.get((on, fn))
        flipped = True
    if bfo_row is None:
        # Try last-name matching
        for (bfn, bon), br in bfo_lookup.items():
            if (fn.split()[-1] in bfn and on.split()[-1] in bon) or \
               (on.split()[-1] in bfn and fn.split()[-1] in bon):
                bfo_row = br
                flipped = on.split()[-1] in norm_name(br['fighter_name'])
                break
    if bfo_row is None:
        results.append({
            'date': r['date'], 'fighter': fighter, 'opponent': opponent,
            'matched': False,
        })
        continue

    # Extract opening and closing odds for the Russian fighter
    if not flipped:
        f_open = bfo_row['fighter_open']
        f_close_lo = bfo_row['fighter_close_lo']
        f_close_hi = bfo_row['fighter_close_hi']
        o_open = bfo_row['opponent_open']
        o_close_lo = bfo_row['opponent_close_lo']
        o_close_hi = bfo_row['opponent_close_hi']
    else:
        f_open = bfo_row['opponent_open']
        f_close_lo = bfo_row['opponent_close_lo']
        f_close_hi = bfo_row['opponent_close_hi']
        o_open = bfo_row['fighter_open']
        o_close_lo = bfo_row['fighter_close_lo']
        o_close_hi = bfo_row['fighter_close_hi']

    # Convert to implied probs
    p_open_raw = american_to_prob(f_open)
    p_opp_open_raw = american_to_prob(o_open)
    # Use midpoint of close range
    f_close_mid = (f_close_lo + f_close_hi) / 2 if pd.notna(f_close_lo) and pd.notna(f_close_hi) else None
    o_close_mid = (o_close_lo + o_close_hi) / 2 if pd.notna(o_close_lo) and pd.notna(o_close_hi) else None
    p_close_raw = american_to_prob(f_close_mid) if f_close_mid is not None else None
    p_opp_close_raw = american_to_prob(o_close_mid) if o_close_mid is not None else None

    # Devig
    p_open = p_close = None
    if p_open_raw and p_opp_open_raw:
        p_open, _ = devig_pair(p_open_raw, p_opp_open_raw)
    if p_close_raw and p_opp_close_raw:
        p_close, _ = devig_pair(p_close_raw, p_opp_close_raw)

    movement = None
    if p_open is not None and p_close is not None:
        movement = p_close - p_open  # negative = line moved against Russian

    results.append({
        'date': r['date'], 'fighter': fighter, 'opponent': opponent,
        'matched': True,
        'open_american': f_open, 'close_american': f_close_mid,
        'p_open': p_open, 'p_close': p_close,
        'p_panel_close': r['p_close_hi'],  # from the panel for reference
        'movement': movement,
        'win': int(r['win']),
    })

df = pd.DataFrame(results)
matched_df = df[df['matched']].copy()
unmatched = df[~df['matched']]

print(f"  Matched to BFO: {len(matched_df)}/{len(df)}")
print(f"  Unmatched: {len(unmatched)}")
if len(unmatched) > 0:
    for _, r in unmatched.iterrows():
        print(f"    {str(r['date'])[:10]} {r['fighter']} vs {r['opponent']}")

# Filter to those with valid movement
valid = matched_df[matched_df['movement'].notna()].copy()
print(f"  With valid open+close: {len(valid)}")

# ═══════════════════════════════════════════════════════════════════
# FIGHT-LEVEL TABLE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*110}")
print("LINE MOVEMENT: ETHNIC-RUSSIAN FIGHTERS POST-WAR (open -> close)")
print("Negative movement = line moved AGAINST the Russian (sentiment signal)")
print(f"{'='*110}")

print(f"\n  {'Date':<12s} {'Russian fighter':<25s} {'Opponent':<22s} {'Open%':>6s} {'Close%':>7s} "
      f"{'Move':>6s} {'Won':>4s}")
print("  " + "-" * 90)

for _, r in valid.sort_values('date').iterrows():
    won = 'YES' if r['win'] == 1 else 'no'
    print(f"  {str(r['date'])[:10]:<12s} {r['fighter'][:24]:<25s} {r['opponent'][:21]:<22s} "
          f"{r['p_open']:>5.1%} {r['p_close']:>6.1%} {r['movement']:>+5.1%} {won:>4s}")

# ═══════════════════════════════════════════════════════════════════
# AGGREGATE
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("AGGREGATE LINE MOVEMENT")
print(f"{'='*80}")

mean_move = valid['movement'].mean()
median_move = valid['movement'].median()
n_against = (valid['movement'] < 0).sum()
n_toward = (valid['movement'] > 0).sum()
n_flat = (valid['movement'] == 0).sum()

print(f"\n  N fights with open+close: {len(valid)}")
print(f"  Mean movement:   {mean_move:+.4f} ({mean_move*100:+.2f}pp)")
print(f"  Median movement: {median_move:+.4f} ({median_move*100:+.2f}pp)")
print(f"  Moved against Russian: {n_against}/{len(valid)} ({n_against/len(valid):.0%})")
print(f"  Moved toward Russian:  {n_toward}/{len(valid)} ({n_toward/len(valid):.0%})")

# Bootstrap CI
n_v = len(valid)
boots = [valid['movement'].values[rng.choice(n_v, n_v, True)].mean() for _ in range(N_BOOT)]
lo, hi = np.percentile(boots, [2.5, 97.5])
sig = 'YES' if (lo > 0 or hi < 0) else 'no'
print(f"  95% CI: [{lo:+.4f}, {hi:+.4f}]  sig={sig}")

# ═══════════════════════════════════════════════════════════════════
# COMPARISON: CAUCASUS + USA CONTROLS
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("COMPARISON: CAUCASUS AND USA LINE MOVEMENT (same period)")
print(f"{'='*80}")

for region_name, region_check in [('Caucasus', 'Caucasus'), ('USA', 'USA')]:
    region_fighters = set(f for f in ufc_fighters if assign_region(f) == region_check)
    region_panel = panel[(panel['date'] >= '2022-02-24') & (panel['year'] <= 2025) &
                         (panel['fighter'].isin(region_fighters))].copy()

    moves = []
    for _, r in region_panel.iterrows():
        fn = norm_name(r['fighter'])
        on = norm_name(r['opponent'])
        bfo_row = bfo_lookup.get((fn, on))
        flipped = False
        if bfo_row is None:
            bfo_row = bfo_lookup.get((on, fn))
            flipped = True
        if bfo_row is None:
            continue

        if not flipped:
            f_open = bfo_row['fighter_open']
            f_close_lo, f_close_hi = bfo_row['fighter_close_lo'], bfo_row['fighter_close_hi']
            o_open = bfo_row['opponent_open']
            o_close_lo, o_close_hi = bfo_row['opponent_close_lo'], bfo_row['opponent_close_hi']
        else:
            f_open = bfo_row['opponent_open']
            f_close_lo, f_close_hi = bfo_row['opponent_close_lo'], bfo_row['opponent_close_hi']
            o_open = bfo_row['fighter_open']
            o_close_lo, o_close_hi = bfo_row['fighter_close_lo'], bfo_row['fighter_close_hi']

        p_open_raw = american_to_prob(f_open)
        p_opp_open_raw = american_to_prob(o_open)
        f_close_mid = (f_close_lo + f_close_hi) / 2 if pd.notna(f_close_lo) and pd.notna(f_close_hi) else None
        o_close_mid = (o_close_lo + o_close_hi) / 2 if pd.notna(o_close_lo) and pd.notna(o_close_hi) else None
        p_close_raw = american_to_prob(f_close_mid) if f_close_mid is not None else None
        p_opp_close_raw = american_to_prob(o_close_mid) if o_close_mid is not None else None

        if p_open_raw and p_opp_open_raw and p_close_raw and p_opp_close_raw:
            p_open, _ = devig_pair(p_open_raw, p_opp_open_raw)
            p_close, _ = devig_pair(p_close_raw, p_opp_close_raw)
            if p_open and p_close:
                moves.append(p_close - p_open)

    if moves:
        moves = np.array(moves)
        m_mean = moves.mean()
        n_ag = (moves < 0).sum()
        boots_c = [moves[rng.choice(len(moves), len(moves), True)].mean() for _ in range(N_BOOT)]
        lo_c, hi_c = np.percentile(boots_c, [2.5, 97.5])
        sig_c = 'YES' if (lo_c > 0 or hi_c < 0) else 'no'
        print(f"\n  {region_name}: N={len(moves)}, mean movement={m_mean:+.4f} ({m_mean*100:+.2f}pp)")
        print(f"    Against: {n_ag}/{len(moves)} ({n_ag/len(moves):.0%})")
        print(f"    CI: [{lo_c:+.4f}, {hi_c:+.4f}] sig={sig_c}")

# ═══════════════════════════════════════════════════════════════════
# VERDICT
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("VERDICT")
print(f"{'='*80}")

print(f"""
  Ethnic Russian post-war line movement: {mean_move:+.2%} ({mean_move*100:+.2f}pp)
  Against Russian: {n_against}/{len(valid)} fights ({n_against/len(valid):.0%})
  CI: [{lo:+.4f}, {hi:+.4f}] sig={sig}

  INTERPRETATION:
  {'Negative = lines moved AGAINST Russians between open and close.' if mean_move < 0 else 'Positive/flat = no evidence of anti-Russian money flow.'}
  {'This is consistent with sentiment-driven betting: the public' if mean_move < -0.005 else 'The line movement does not clearly support the sentiment story.'}
  {'under-backs Russians, moving the line against them.' if mean_move < -0.005 else ''}
  {'The market OPENS with information and CLOSES with sentiment + information.' if mean_move < -0.005 else ''}

  {'Alternatively: sharp money may have already corrected by close (arbed the' if mean_move >= -0.005 else ''}
  {'sentiment), leaving no net movement. The excess would then come from the' if mean_move >= -0.005 else ''}
  {'opening line itself being too low, not from close-to-open drift.' if mean_move >= -0.005 else ''}
""")
