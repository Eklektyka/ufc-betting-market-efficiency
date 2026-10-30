#!/usr/bin/env python3
"""
score_methods.py
----------------
Score method-of-victory picks against devigged prop odds.

Input:  per-user pick CSVs (with picked_method, picked_round)
        bfo_props_devig.csv (consensus_p, best_odds per matchup×outcome)
        bfo_close_all.csv   (devigged moneyline probs)
        card_map.csv        (bfo_event_id → card_key)
        name_overrides.csv  (BFO↔Tapology name mapping)

Test:   python score_methods.py --test Ezoteryka
"""

import csv
import math
import os
import re
import sys
import unicodedata
from collections import defaultdict
from statistics import median

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PICKS_DIR = r'C:\Research\ufc\picks\users'

METHOD_MAP_TAP = {
    'ko/tko': 'ko_tko',
    'tko/ko': 'ko_tko',
    'ko': 'ko_tko',
    'tko': 'ko_tko',
    'submission': 'submission',
    'sub': 'submission',
    'decision': 'decision',
    'dec': 'decision',
}

METHOD_MAP_ACTUAL = {
    'ko/tko': 'ko_tko',
    'tko': 'ko_tko',
    'ko': 'ko_tko',
    'submission': 'submission',
    'decision': 'decision',
}


def map_tap_method(raw):
    """Map Tapology picked_method to {ko_tko, submission, decision} or None."""
    return METHOD_MAP_TAP.get(raw.strip().lower())


def map_actual_method(raw):
    """Map actual_method string to {ko_tko, submission, decision} or None."""
    raw = raw.strip().lower()
    if 'ko' in raw or 'tko' in raw:
        return 'ko_tko'
    if 'submission' in raw:
        return 'submission'
    if 'decision' in raw:
        return 'decision'
    return None  # draw, NC, DQ, etc.


def american_to_decimal(odds):
    if odds > 0:
        return 1 + odds / 100
    else:
        return 1 + 100 / abs(odds)


# ---------------------------------------------------------------------------
# Name matching (same logic as analyze_user.py)
# ---------------------------------------------------------------------------
def strip_accents(s):
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def normalize(name):
    name = strip_accents(name).strip().lower()
    name = re.sub(r'[^\w\s]', '', name)
    return name.strip()


def last_name(name):
    parts = normalize(name).split()
    return parts[-1] if parts else ""


def names_match(a, b):
    na, nb = normalize(a), normalize(b)
    if na == nb:
        return True
    la, lb = last_name(a), last_name(b)
    if la == lb and len(na) > 0 and len(nb) > 0 and na[0] == nb[0]:
        return True
    if len(na) > 4 and len(nb) > 4 and (na in nb or nb in na):
        return True
    return False


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
def load_card_map():
    """card_key → list of bfo_event_ids."""
    cm = defaultdict(list)
    with open('card_map.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            cm[r['card_key']].append(r['bfo_event_id'])
    return cm


def load_name_overrides():
    """bfo_name (normalized) → tapology_name (normalized)."""
    overrides = {}
    with open('name_overrides.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            overrides[normalize(r['bfo_name'])] = normalize(r['tapology_name'])
    # Also build reverse
    reverse = {v: k for k, v in overrides.items()}
    return overrides, reverse


def load_props_devig():
    """
    Returns dict: (bfo_event_id, matchup_id) → {
        'fighter_a', 'fighter_b',
        'outcomes': {(prop_type, prop_fighter_norm): {consensus_p, best_odds, best_book, n_books}}
    }
    Only keep one row per (matchup, outcome) — the consensus values.
    """
    bouts = {}
    with open('bfo_props_devig.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            key = (r['bfo_event_id'], r['bfo_matchup_id'])
            if key not in bouts:
                bouts[key] = {
                    'fighter_a': r['fighter_a'],
                    'fighter_b': r['fighter_b'],
                    'event_name': r['event_name'],
                    'outcomes': {},
                }
            ok = (r['prop_type'], normalize(r['prop_fighter']))
            if ok not in bouts[key]['outcomes']:
                bouts[key]['outcomes'][ok] = {
                    'consensus_p': float(r['consensus_p']),
                    'best_odds': int(r['best_odds']) if r['best_odds'] else None,
                    'best_book': r['best_book'],
                    'n_books': int(r['n_books']),
                    'prop_fighter_raw': r['prop_fighter'],
                }
    return bouts


def load_moneyline_devigged():
    """(bfo_event_id, matchup_id) → {f1_name, f2_name, f1_devig, f2_devig}."""
    ml = {}
    with open('bfo_close_all.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            key = (r['bfo_event_id'], r['bfo_matchup_id'])
            ml[key] = {
                'f1_name': r['fighter1_name'],
                'f2_name': r['fighter2_name'],
                'f1_devig': float(r['f1_devigged_prob']),
                'f2_devig': float(r['f2_devigged_prob']),
            }
    return ml


# ---------------------------------------------------------------------------
# Join: find the prop bout for a pick
# ---------------------------------------------------------------------------
def find_prop_bout(fighter_picked, opponent, event_ids, props, overrides, rev_overrides):
    """Find the matching bout in props_devig for a pick.
    Returns (bout_key, prop_fighter_norm) where prop_fighter_norm matches
    the key used in bout['outcomes'], or (None, None)."""
    fp_norm = normalize(fighter_picked)
    opp_norm = normalize(opponent)

    # Apply overrides (tapology→bfo direction)
    fp_bfo = rev_overrides.get(fp_norm, fp_norm)
    opp_bfo = rev_overrides.get(opp_norm, opp_norm)

    for eid in event_ids:
        for (eid2, mid), bout in props.items():
            if eid2 != eid:
                continue
            fa_norm = normalize(bout['fighter_a'])
            fb_norm = normalize(bout['fighter_b'])

            # Check if picked fighter matches fighter_a or fighter_b
            matched_fa = names_match(fp_bfo, fa_norm) or names_match(fp_norm, fa_norm)
            matched_fb = names_match(fp_bfo, fb_norm) or names_match(fp_norm, fb_norm)
            opp_fa = names_match(opp_bfo, fa_norm) or names_match(opp_norm, fa_norm)
            opp_fb = names_match(opp_bfo, fb_norm) or names_match(opp_norm, fb_norm)

            if (matched_fa and opp_fb) or (matched_fb and opp_fa):
                # Found the bout — now find which prop_fighter_norm matches
                # the picked fighter in the outcomes dict
                prop_fighters = set(fn for (_, fn) in bout['outcomes'].keys())
                for pf_norm in prop_fighters:
                    if names_match(fp_norm, pf_norm) or names_match(fp_bfo, pf_norm):
                        return (eid2, mid), pf_norm
                # Fallback: no prop_fighter matched (shouldn't happen)
                return None, None

    return None, None


# ---------------------------------------------------------------------------
# Score one user
# ---------------------------------------------------------------------------
def score_user(picks_file, card_map, props, ml_dev, overrides, rev_overrides):
    """Score a single user's method picks. Returns list of scored rows + stats."""
    with open(picks_file, 'r', encoding='utf-8') as f:
        picks = list(csv.DictReader(f))

    scored = []
    unmapped_methods = []
    no_method_count = 0
    no_prop_market = 0
    total_picks = len(picks)

    for pick in picks:
        picked_method_raw = pick.get('picked_method', '').strip()
        if not picked_method_raw:
            no_method_count += 1
            continue

        picked_method = map_tap_method(picked_method_raw)
        if picked_method is None:
            unmapped_methods.append(picked_method_raw)
            continue

        actual_method = map_actual_method(pick['actual_method'])
        if actual_method is None:
            # draw/NC/DQ → push
            continue

        fighter_picked = pick['fighter_picked']
        opponent = pick['opponent']
        event = pick['event']
        actual_winner = pick['actual_winner']
        is_correct_fighter = pick['correct'] == 'YES'

        # Find card_key → bfo_event_ids
        event_ids = card_map.get(event, [])
        if not event_ids:
            no_prop_market += 1
            continue

        # Find matching bout in props
        bout_key, matched_norm = find_prop_bout(
            fighter_picked, opponent, event_ids, props, overrides, rev_overrides)

        if bout_key is None:
            no_prop_market += 1
            continue

        bout = props[bout_key]
        outcomes = bout['outcomes']

        # Check we have a full 6-way
        if bout['outcomes'] and next(iter(bout['outcomes'].values()))['n_books'] < 1:
            no_prop_market += 1
            continue

        # Look up consensus_p for (picked_method, matched_fighter)
        outcome_key = (picked_method, matched_norm)
        if outcome_key not in outcomes:
            no_prop_market += 1
            continue

        oc = outcomes[outcome_key]
        consensus_p = oc['consensus_p']
        best_odds = oc['best_odds']
        best_book = oc['best_book']
        n_books = oc['n_books']

        # Joint hit: fighter correct AND method correct
        is_correct_method = (actual_method == picked_method)
        joint_hit = 1 if (is_correct_fighter and is_correct_method) else 0
        joint_clv = joint_hit - consensus_p

        # Joint profit at best_odds
        if best_odds is not None:
            dec_odds = american_to_decimal(best_odds)
            joint_profit = (dec_odds - 1) * 100 if joint_hit else -100
        else:
            joint_profit = None

        # Conditional (only when fighter_picked won)
        cond_hit = None
        p_cond = None
        cond_clv = None
        if is_correct_fighter:
            cond_hit = 1 if is_correct_method else 0
            # p_cond = consensus_p(fighter, method) / sum_m consensus_p(fighter, m)
            fighter_total = sum(
                v['consensus_p'] for (pt, fn), v in outcomes.items()
                if fn == matched_norm and pt in ('ko_tko', 'submission', 'decision')
            )
            if fighter_total > 0:
                p_cond = consensus_p / fighter_total
                cond_clv = cond_hit - p_cond

        scored.append({
            'event': event,
            'bout': f'{fighter_picked} vs {opponent}',
            'fighter_picked': fighter_picked,
            'opponent': opponent,
            'picked_method': picked_method,
            'picked_round': pick.get('picked_round', ''),
            'actual_winner': actual_winner,
            'actual_method_raw': pick['actual_method'],
            'actual_method': actual_method,
            'fighter_correct': is_correct_fighter,
            'method_correct': is_correct_method,
            'joint_hit': joint_hit,
            'consensus_p': consensus_p,
            'joint_clv': round(joint_clv, 6),
            'best_odds': best_odds,
            'best_book': best_book,
            'n_books': n_books,
            'joint_profit': round(joint_profit, 2) if joint_profit is not None else None,
            'cond_hit': cond_hit,
            'p_cond': round(p_cond, 6) if p_cond is not None else None,
            'cond_clv': round(cond_clv, 6) if cond_clv is not None else None,
        })

    stats = {
        'total_picks': total_picks,
        'no_method': no_method_count,
        'no_method_share': no_method_count / total_picks if total_picks else 0,
        'unmapped_methods': unmapped_methods,
        'no_prop_market': no_prop_market,
        'scored': len(scored),
    }

    return scored, stats


# ---------------------------------------------------------------------------
# Test mode
# ---------------------------------------------------------------------------
def test_user(username):
    print("Loading data...")
    card_map = load_card_map()
    props = load_props_devig()
    ml_dev = load_moneyline_devigged()
    overrides, rev_overrides = load_name_overrides()

    picks_file = os.path.join(PICKS_DIR, f'{username}.csv')
    if not os.path.exists(picks_file):
        print(f"File not found: {picks_file}")
        return

    print(f"Scoring {username}...")
    scored, stats = score_user(picks_file, card_map, props, ml_dev, overrides, rev_overrides)

    print(f"\n{'='*100}")
    print(f"USER: {username}")
    print(f"{'='*100}")
    print(f"Total picks:        {stats['total_picks']}")
    print(f"No method:          {stats['no_method']} ({stats['no_method_share']:.1%})")
    print(f"Unmapped methods:   {stats['unmapped_methods']}")
    print(f"No prop market:     {stats['no_prop_market']}")
    print(f"Scored:             {stats['scored']}")

    # Filter to UFC 330 for display
    ufc330 = [s for s in scored if '330' in s['event']]
    if not ufc330:
        print("\nNo UFC 330 picks found in scored output.")
        print("Available events:", sorted(set(s['event'] for s in scored))[:10])
        return

    print(f"\n--- UFC 330 picks ({len(ufc330)} scored) ---")
    print(f"{'Fighter':<25} {'Method':<12} {'Ftr?':>4} {'Mtd?':>4} {'Joint':>5} "
          f"{'cons_p':>8} {'CLV':>8} {'best':>6} {'profit':>8} "
          f"{'cond':>5} {'p_cond':>8} {'c_clv':>8}")
    print("-" * 120)

    for s in ufc330:
        ftr = 'Y' if s['fighter_correct'] else 'N'
        mtd = 'Y' if s['method_correct'] else 'N'
        jh = s['joint_hit']
        cp = f"{s['consensus_p']:.4f}"
        clv = f"{s['joint_clv']:+.4f}"
        best = s['best_odds'] if s['best_odds'] else ''
        profit = f"${s['joint_profit']:+.0f}" if s['joint_profit'] is not None else ''
        ch = str(s['cond_hit']) if s['cond_hit'] is not None else '-'
        pc = f"{s['p_cond']:.4f}" if s['p_cond'] is not None else '-'
        cc = f"{s['cond_clv']:+.4f}" if s['cond_clv'] is not None else '-'

        name = s['fighter_picked'][:24]
        print(f"{name:<25} {s['picked_method']:<12} {ftr:>4} {mtd:>4} {jh:>5} "
              f"{cp:>8} {clv:>8} {best:>6} {profit:>8} "
              f"{ch:>5} {pc:>8} {cc:>8}")

    # Summary for all scored picks
    n = len(scored)
    if n > 0:
        joint_hits = sum(s['joint_hit'] for s in scored)
        mean_cp = sum(s['consensus_p'] for s in scored) / n
        joint_acc = joint_hits / n
        mean_clv = sum(s['joint_clv'] for s in scored) / n

        profits = [s['joint_profit'] for s in scored if s['joint_profit'] is not None]
        roi = sum(profits) / (len(profits) * 100) if profits else 0

        cond_rows = [s for s in scored if s['cond_hit'] is not None]
        if cond_rows:
            cond_hits = sum(s['cond_hit'] for s in cond_rows)
            cond_n = len(cond_rows)
            cond_acc = cond_hits / cond_n
            mean_pcond = sum(s['p_cond'] for s in cond_rows) / cond_n
            mean_cond_clv = sum(s['cond_clv'] for s in cond_rows) / cond_n
        else:
            cond_acc = mean_pcond = mean_cond_clv = 0
            cond_n = 0

        print(f"\n--- SUMMARY (all {n} scored picks) ---")
        print(f"Joint accuracy:     {joint_acc:.3f} (expected: {mean_cp:.3f})")
        print(f"Joint CLV:          {mean_clv:+.4f}")
        print(f"Joint ROI:          {roi:+.1%}")
        print(f"Conditional (n={cond_n}): acc={cond_acc:.3f} (expected: {mean_pcond:.3f}), CLV={mean_cond_clv:+.4f}")


if __name__ == '__main__':
    if '--test' in sys.argv:
        idx = sys.argv.index('--test')
        user = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else 'Ezoteryka'
        test_user(user)
    else:
        print("Usage: python score_methods.py --test USERNAME")
