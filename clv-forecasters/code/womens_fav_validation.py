#!/usr/bin/env python3
"""
Women's-favorite mispricing: fight-level validation against consensus close.
Gate: women's vs men's favorites, de-vigged consensus (not best-line).
"""
import csv, os, re, sys, unicodedata
import numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
rng = np.random.RandomState(SEED)

def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
def normalize(name):
    return re.sub(r'[^\w\s]', '', strip_accents(name).strip().lower()).strip()
def names_match(a, b):
    na, nb = normalize(a), normalize(b)
    if na == nb: return True
    la = na.split()[-1] if na.split() else ''
    lb = nb.split()[-1] if nb.split() else ''
    if la == lb and len(na) > 0 and len(nb) > 0 and na[0] == nb[0]: return True
    if len(na) > 4 and len(nb) > 4 and (na in nb or nb in na): return True
    return False
def american_to_decimal(odds):
    odds = int(odds)
    return 1 + odds / 100 if odds > 0 else 1 + 100 / abs(odds)
def american_to_implied(odds):
    odds = int(odds)
    return -odds / (-odds + 100) if odds < 0 else 100 / (odds + 100)

# Women fighters
women_fighters = set()
with open(r'C:\Users\micha\mma_line_efficiency_paper\data\raw\ufcstats_fights.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if 'women' in r.get('division', '').lower():
            women_fighters.add(normalize(r['fighter_name']))

# ─── Load bfo_close_all: CONSENSUS de-vigged probabilities ───
# p_fair_a / p_fair_b are Shin-devigged from consensus closing odds
# These are NOT best-line — they're the normalized consensus pair
fights = []
with open('bfo_close_all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        f1 = r['fighter1_name']; f2 = r['fighter2_name']
        f1_n = normalize(f1); f2_n = normalize(f2)
        p_a = float(r['p_fair_a']); p_b = float(r['p_fair_b'])
        date = r['event_date']
        event = r['event_name']

        # Also load CONSENSUS American odds for the proper implied check
        cons_a = float(r['f1_consensus_american'])
        cons_b = float(r['f2_consensus_american'])
        # Implied from consensus (with vig)
        ip_a = float(r['f1_implied_prob']); ip_b = float(r['f2_implied_prob'])
        # De-vigged from consensus
        dv_a = float(r['f1_devigged_prob']); dv_b = float(r['f2_devigged_prob'])

        # Also get best-line for comparison
        best_a = int(r['best_line_a']); best_b = int(r['best_line_b'])

        # Determine gender
        is_women = f1_n in women_fighters and f2_n in women_fighters

        # Determine favorite (by de-vigged consensus)
        if dv_a >= dv_b:
            fav = f1; fav_p = dv_a; dog = f2; dog_p = dv_b
            fav_best = best_a; dog_best = best_b
            fav_cons = cons_a; dog_cons = cons_b
        else:
            fav = f2; fav_p = dv_b; dog = f1; dog_p = dv_a
            fav_best = best_b; dog_best = best_a
            fav_cons = cons_b; dog_cons = cons_a

        fights.append({
            'f1': f1, 'f2': f2, 'date': date, 'event': event,
            'is_women': is_women,
            'fav': fav, 'fav_devig_consensus': fav_p, 'dog_devig_consensus': dog_p,
            'fav_best_line': fav_best, 'dog_best_line': dog_best,
            'fav_consensus_american': fav_cons,
        })

# ─── Load outcomes from ezoteryka_scored ───
outcomes = {}
with open('ezoteryka_scored.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        parts = r['bout'].split(' vs ')
        if len(parts) != 2: continue
        if r['result'] == 'win': winner = r['picked_fighter']
        else: winner = parts[1] if normalize(r['picked_fighter']) == normalize(parts[0]) else parts[0]
        key = (normalize(parts[0]), normalize(parts[1]))
        outcomes[key] = normalize(winner)
        outcomes[(key[1], key[0])] = normalize(winner)

# Match fights to outcomes
for fight in fights:
    f1_n = normalize(fight['f1']); f2_n = normalize(fight['f2'])
    winner = outcomes.get((f1_n, f2_n))
    if not winner:
        # Fuzzy match
        for (a, b), w in outcomes.items():
            if (names_match(f1_n, a) and names_match(f2_n, b)) or \
               (names_match(f1_n, b) and names_match(f2_n, a)):
                winner = w; break
    fight['fav_won'] = names_match(normalize(fight['fav']), winner) if winner else None

matched = [f for f in fights if f['fav_won'] is not None]
women = [f for f in matched if f['is_women']]
men = [f for f in matched if not f['is_women']]

print(f"Total fights in bfo_close_all: {len(fights)}")
print(f"Matched to outcomes: {len(matched)}")
print(f"Women's fights: {len(women)}, Men's fights: {len(men)}")

# ═══════════════════════════════════════════════════════════════════
# GATE: fight-level favorite edge, consensus de-vigged
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("GATE: FAVORITE WIN RATE vs DE-VIGGED CONSENSUS CLOSE")
print("(fight-level, independent of user picks)")
print(f"{'='*80}")

def analyze_favs(fights_list, label):
    n = len(fights_list)
    if n == 0:
        print(f"\n  {label}: n=0"); return
    fav_wins = sum(f['fav_won'] for f in fights_list)
    win_rate = fav_wins / n
    mean_implied = np.mean([f['fav_devig_consensus'] for f in fights_list])
    edge = win_rate - mean_implied

    # Fight-clustered bootstrap
    events = list(set(f['event'] for f in fights_list))
    eb = defaultdict(list)
    for f in fights_list: eb[f['event']].append(f)
    boot = []
    for _ in range(N_BOOT):
        se = rng.choice(events, size=len(events), replace=True)
        sw = si = sn = 0
        for e in se:
            for f in eb[e]:
                sn += 1; sw += f['fav_won']; si += f['fav_devig_consensus']
        if sn > 0: boot.append(sw/sn - si/sn)
    ci = (np.percentile(boot, 2.5), np.percentile(boot, 97.5))
    excl = 'YES' if ci[0] > 0 else 'NO'

    # Also compute best-line implied for comparison
    # Convert best fav line to implied, de-vig with complement
    best_implieds = []
    for f in fights_list:
        ip_fav = american_to_implied(f['fav_best_line'])
        ip_dog = american_to_implied(f['dog_best_line'])
        # Shin-devig (simple multiplicative for comparison)
        total = ip_fav + ip_dog
        best_implieds.append(ip_fav / total if total > 0 else 0.5)
    mean_best_implied = np.mean(best_implieds)
    edge_best = win_rate - mean_best_implied

    print(f"\n  {label} (n={n} fights):")
    print(f"    Favorite win rate:           {win_rate:.1%} ({fav_wins}/{n})")
    print(f"    Consensus de-vig implied:    {mean_implied:.1%}")
    print(f"    Edge (vs consensus):         {edge:+.1%}pp  CI=[{ci[0]:+.1%},{ci[1]:+.1%}]  excl_0={excl}")
    print(f"    Best-line de-vig implied:    {mean_best_implied:.1%}")
    print(f"    Edge (vs best-line):         {edge_best:+.1%}pp")
    return edge, ci

print("\n  Using: p_fair = f1_devigged_prob / f2_devigged_prob from bfo_close_all.csv")
print("  These are Shin-devigged from CONSENSUS closing American odds,")
print("  NOT from best-line. Best-line shown for comparison only.\n")

w_edge, w_ci = analyze_favs(women, "WOMEN'S FAVORITES")
m_edge, m_ci = analyze_favs(men, "MEN'S FAVORITES")

# Difference
if w_edge is not None and m_edge is not None:
    diff = w_edge - m_edge
    print(f"\n  DIFFERENCE (women − men): {diff:+.1%}pp")

    # Bootstrap the difference
    w_events = list(set(f['event'] for f in women))
    m_events = list(set(f['event'] for f in men))
    w_eb = defaultdict(list); m_eb = defaultdict(list)
    for f in women: w_eb[f['event']].append(f)
    for f in men: m_eb[f['event']].append(f)
    boot_diff = []
    for _ in range(N_BOOT):
        # Women
        sw_e = rng.choice(w_events, size=len(w_events), replace=True)
        ww = wi = wn = 0
        for e in sw_e:
            for f in w_eb[e]: wn += 1; ww += f['fav_won']; wi += f['fav_devig_consensus']
        w_val = (ww/wn - wi/wn) if wn > 0 else 0
        # Men
        sm_e = rng.choice(m_events, size=len(m_events), replace=True)
        mw = mi = mn = 0
        for e in sm_e:
            for f in m_eb[e]: mn += 1; mw += f['fav_won']; mi += f['fav_devig_consensus']
        m_val = (mw/mn - mi/mn) if mn > 0 else 0
        boot_diff.append(w_val - m_val)
    diff_ci = (np.percentile(boot_diff, 2.5), np.percentile(boot_diff, 97.5))
    print(f"  Difference CI: [{diff_ci[0]:+.1%},{diff_ci[1]:+.1%}]")
    print(f"  CI excludes zero: {'YES' if diff_ci[0] > 0 else 'NO'}")

# ─── GATE DECISION ───
print(f"\n{'='*80}")
print("GATE DECISION")
print(f"{'='*80}")

men_also_tilted = m_edge is not None and m_ci is not None and m_ci[0] > 0
women_edge_real = w_edge is not None and w_ci is not None and w_ci[0] > 0
women_collapsed = w_edge is not None and abs(w_edge) < 0.02

if women_collapsed:
    print("\n  Women's edge collapsed to <2pp on consensus close.")
    print("  → ARTIFACT of best-line convention. No women's-specific anomaly.")
    print("  STOP.")
elif men_also_tilted and women_edge_real:
    # Check if similar magnitude
    if w_edge is not None and m_edge is not None and abs(w_edge - m_edge) < 0.03:
        print(f"\n  Both men's ({m_edge:+.1%}pp) and women's ({w_edge:+.1%}pp) favs")
        print(f"  beat consensus close by similar amounts.")
        print(f"  → GENERAL de-vig/convention artifact, not women's-specific.")
        print(f"  STOP.")
    else:
        print(f"\n  Women's ({w_edge:+.1%}pp) beats consensus by MORE than men's ({m_edge:+.1%}pp).")
        print(f"  Difference: {diff:+.1%}pp CI=[{diff_ci[0]:+.1%},{diff_ci[1]:+.1%}]")
        if diff_ci[0] > 0:
            print(f"  → WOMEN'S-SPECIFIC anomaly SURVIVES. Proceed to characterization.")
        else:
            print(f"  → Difference CI includes zero. Cannot confirm women's-specific anomaly.")
            print(f"  STOP.")
elif women_edge_real and not men_also_tilted:
    print(f"\n  Women's favorites beat consensus close by {w_edge:+.1%}pp (CI excl 0).")
    print(f"  Men's favorites do NOT beat consensus close (CI includes 0).")
    print(f"  → WOMEN'S-SPECIFIC anomaly CONFIRMED. Proceed to characterization.")
else:
    print(f"\n  Women's edge does not survive (CI includes zero).")
    print(f"  → No anomaly. STOP.")
