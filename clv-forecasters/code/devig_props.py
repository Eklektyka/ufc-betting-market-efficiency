#!/usr/bin/env python3
"""
devig_props.py
--------------
De-vig method-of-victory prop odds using Shin (1993).

Input:  bfo_mov_odds.csv  (method props per book)
        bfo_odds_rank.csv + bfo_odds_ext_2026.csv  (moneyline per book)
Output: bfo_props_devig.csv

Markets:
  6-way: {ko_tko, submission, decision} × {fighter_a, fighter_b}
  2-way: inside_distance per fighter (vs "not inside distance")

Shin de-vigging within each book, then aggregate across books.
"""

import csv
import math
import os
import sys
from collections import defaultdict
from statistics import median

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Shin (1993) de-vigging
# ---------------------------------------------------------------------------

def american_to_implied(odds):
    """American odds -> raw implied probability (includes vig)."""
    if odds < 0:
        return -odds / (-odds + 100)
    else:
        return 100 / (odds + 100)


def american_to_decimal(odds):
    if odds < 0:
        return 1 + 100 / abs(odds)
    else:
        return 1 + odds / 100


def shin_objective(z, pis, beta):
    """Sum of Shin probabilities minus 1. Root at correct z."""
    total = 0.0
    for pi in pis:
        num = math.sqrt(z**2 + 4 * (1 - z) * pi**2 / beta) - z
        den = 2 * (1 - z)
        total += num / den
    return total - 1.0


def shin_probs(z, pis, beta):
    """Return list of Shin probabilities for given z."""
    result = []
    for pi in pis:
        num = math.sqrt(z**2 + 4 * (1 - z) * pi**2 / beta) - z
        den = 2 * (1 - z)
        result.append(num / den)
    return result


def brentq(f, a, b, tol=1e-10, maxiter=200):
    """Simple Brent's method root finder."""
    fa, fb = f(a), f(b)
    if fa * fb > 0:
        return None
    if abs(fa) < tol:
        return a
    if abs(fb) < tol:
        return b
    c, fc = a, fa
    d = e = b - a
    for _ in range(maxiter):
        if fb * fc > 0:
            c, fc = a, fa
            d = e = b - a
        if abs(fc) < abs(fb):
            a, b, c = b, c, b
            fa, fb, fc = fb, fc, fb
        tol1 = 2e-16 * abs(b) + 0.5 * tol
        m = 0.5 * (c - b)
        if abs(m) <= tol1 or fb == 0:
            return b
        if abs(e) >= tol1 and abs(fa) > abs(fb):
            s = fb / fa
            if a == c:
                p = 2 * m * s
                q = 1 - s
            else:
                q = fa / fc
                r = fb / fc
                p = s * (2 * m * q * (q - r) - (b - a) * (r - 1))
                q = (q - 1) * (r - 1) * (s - 1)
            if p > 0:
                q = -q
            else:
                p = -p
            if 2 * p < min(3 * m * q - abs(tol1 * q), abs(e * q)):
                e, d = d, p / q
            else:
                d = e = m
        else:
            d = e = m
        a, fa = b, fb
        if abs(d) > tol1:
            b += d
        else:
            b += tol1 if m > 0 else -tol1
        fb = f(b)
    return b


def devig_shin(odds_list):
    """
    De-vig a list of American odds using Shin (1993).
    Returns (probs, z, overround, method) or None if can't solve.
    """
    pis = [american_to_implied(o) for o in odds_list]
    beta = sum(pis)

    if beta <= 1.0:
        # No overround — fall back to multiplicative
        probs = [pi / beta for pi in pis]
        return probs, 0.0, beta, 'multiplicative'

    # Find z in [0, 1) such that sum of Shin probs = 1
    f = lambda z: shin_objective(z, pis, beta)

    # Check bracket
    fa = f(1e-12)
    fb = f(0.999)
    if fa * fb > 0:
        # No root — fall back to multiplicative
        probs = [pi / beta for pi in pis]
        return probs, 0.0, beta, 'multiplicative'

    z = brentq(f, 1e-12, 0.999)
    if z is None:
        probs = [pi / beta for pi in pis]
        return probs, 0.0, beta, 'multiplicative'

    probs = shin_probs(z, pis, beta)
    return probs, z, beta, 'shin'


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_mov_props():
    """Load MoV prop odds. Returns dict: (event_id, matchup_id, book) -> list of rows."""
    props = defaultdict(list)
    with open('bfo_mov_odds.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            key = (r['bfo_event_id'], r['bfo_matchup_id'], r['book'])
            props[key].append(r)
    return props


def load_moneylines():
    """Load per-book moneylines. Returns dict: (event_id, matchup_id, book) -> {side -> odds}."""
    ml = defaultdict(dict)
    for fname in ['bfo_odds_rank.csv', 'bfo_odds_ext_2026.csv', 'bfo_odds_fill_2025.csv']:
        try:
            with open(fname, 'r', encoding='utf-8') as f:
                for r in csv.DictReader(f):
                    key = (r['bfo_event_id'], r['bfo_matchup_id'], r['book'])
                    side = int(r['fighter_side'])
                    ml[key][side] = {
                        'odds': int(r['odds_american']),
                        'name': r['fighter_name'],
                    }
        except FileNotFoundError:
            pass
    return ml


def load_moneyline_devigged():
    """Load devigged moneyline probs from bfo_close_all.csv."""
    ml_dev = {}
    with open('bfo_close_all.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            key = (r['bfo_event_id'], r['bfo_matchup_id'])
            ml_dev[key] = {
                'f1_name': r['fighter1_name'],
                'f2_name': r['fighter2_name'],
                'f1_devig': float(r['f1_devigged_prob']),
                'f2_devig': float(r['f2_devigged_prob']),
            }
    return ml_dev


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

FIELDNAMES = [
    'bfo_event_id', 'event_name', 'event_date',
    'bfo_matchup_id', 'fighter_a', 'fighter_b',
    'prop_type', 'prop_fighter',
    'book', 'odds_american', 'implied_raw',
    'p_shin', 'z', 'overround', 'method',
    'consensus_p', 'best_odds', 'best_book', 'n_books',
    'ml_consistency_diff',
]

SIX_WAY_TYPES = ['ko_tko', 'submission', 'decision']


def main(test_only=False):
    print("Loading MoV props...")
    props_by_key = load_mov_props()

    print("Loading per-book moneylines...")
    ml_by_key = load_moneylines()

    print("Loading devigged moneylines...")
    ml_devigged = load_moneyline_devigged()

    # Group props by (event_id, matchup_id) to identify bouts
    bouts = defaultdict(lambda: defaultdict(list))  # (eid, mid) -> book -> [rows]
    for (eid, mid, book), rows in props_by_key.items():
        bouts[(eid, mid)][book].extend(rows)

    print(f"Total bouts with props: {len(bouts)}")

    all_output = []
    skipped_books = 0
    total_books = 0
    fallback_count = 0
    consistency_flags = 0

    for (eid, mid), books_data in sorted(bouts.items()):
        # Get bout metadata from first row
        sample_row = next(iter(books_data.values()))[0]
        fighter_a = sample_row['fighter_a']
        fighter_b = sample_row['fighter_b']
        event_name = sample_row['event_name']
        event_date = sample_row['event_date']

        if test_only and not (
            'gamrot' in fighter_a.lower() or 'gamrot' in fighter_b.lower() or
            'oliveira' in fighter_a.lower() or 'oliveira' in fighter_b.lower()
        ):
            continue
        if test_only and eid != '3869':
            continue

        # Per-book de-vig results for 6-way
        book_results_6way = {}  # book -> {(prop_type, fighter): {odds, p_shin, ...}}

        for book, rows in books_data.items():
            total_books += 1

            # Build 6-way market
            six_way = {}  # (prop_type, fighter_name) -> odds
            inside_dist = {}  # fighter_name -> odds
            for r in rows:
                pt = r['prop_type']
                pf = r['prop_fighter']
                odds = int(r['odds_american'])
                if pt in SIX_WAY_TYPES:
                    six_way[(pt, pf)] = odds
                elif pt == 'inside_distance':
                    inside_dist[pf] = odds

            # Check if we have all 6 outcomes
            # Map prop_fighter names to fighter_a/fighter_b
            outcomes_a = [(pt, pf) for (pt, pf) in six_way if pt in SIX_WAY_TYPES
                          and pf != 'Either fighter']
            fighters_in_props = set(pf for _, pf in outcomes_a)

            # We need exactly 2 fighters × 3 types = 6 outcomes
            expected_keys = set()
            for f in fighters_in_props:
                for pt in SIX_WAY_TYPES:
                    expected_keys.add((pt, f))

            if len(expected_keys) != 6 or not expected_keys.issubset(six_way.keys()):
                skipped_books += 1
                continue

            # Order odds: ko_a, sub_a, dec_a, ko_b, sub_b, dec_b
            fighters = sorted(fighters_in_props)
            f_map = {fighters[0]: 'a', fighters[1]: 'b'}

            ordered_keys = []
            ordered_odds = []
            for f in fighters:
                for pt in SIX_WAY_TYPES:
                    k = (pt, f)
                    ordered_keys.append(k)
                    ordered_odds.append(six_way[k])

            # De-vig 6-way
            result = devig_shin(ordered_odds)
            if result is None:
                skipped_books += 1
                continue

            probs, z, overround, method = result
            if method != 'shin':
                fallback_count += 1

            book_result = {}
            for idx, k in enumerate(ordered_keys):
                pt, pf = k
                book_result[k] = {
                    'odds': ordered_odds[idx],
                    'implied_raw': american_to_implied(ordered_odds[idx]),
                    'p_shin': probs[idx],
                    'z': z,
                    'overround': overround,
                    'method': method,
                }
            book_results_6way[book] = book_result

        # Compute consensus (median across books) and best odds
        all_keys = set()
        for br in book_results_6way.values():
            all_keys.update(br.keys())

        consensus = {}
        best_odds_map = {}
        for k in all_keys:
            p_values = [br[k]['p_shin'] for br in book_results_6way.values() if k in br]
            odds_values = [(br[k]['odds'], book) for book, br in book_results_6way.items() if k in br]
            if p_values:
                consensus[k] = median(p_values)
            if odds_values:
                best = max(odds_values, key=lambda x: x[0])
                best_odds_map[k] = best

        # ML consistency check
        ml_dev = ml_devigged.get((eid, mid))

        for book, br in book_results_6way.items():
            # Sum methods for each fighter
            fighters = sorted(set(pf for _, pf in br.keys()))
            if len(fighters) != 2:
                continue

            for k, v in br.items():
                pt, pf = k
                # ML consistency: sum of fighter's 3 method probs vs ML devigged prob
                fighter_method_sum = sum(
                    br[(t, pf)]['p_shin'] for t in SIX_WAY_TYPES if (t, pf) in br
                )

                ml_diff = ''
                if ml_dev:
                    # Match fighter name to f1 or f2
                    if pf.lower() in ml_dev['f1_name'].lower() or ml_dev['f1_name'].lower() in pf.lower():
                        ml_diff = round(fighter_method_sum - ml_dev['f1_devig'], 4)
                    elif pf.lower() in ml_dev['f2_name'].lower() or ml_dev['f2_name'].lower() in pf.lower():
                        ml_diff = round(fighter_method_sum - ml_dev['f2_devig'], 4)

                    if ml_diff != '' and abs(ml_diff) > 0.05:
                        consistency_flags += 1

                row = {
                    'bfo_event_id': eid,
                    'event_name': event_name,
                    'event_date': event_date,
                    'bfo_matchup_id': mid,
                    'fighter_a': fighter_a,
                    'fighter_b': fighter_b,
                    'prop_type': pt,
                    'prop_fighter': pf,
                    'book': book,
                    'odds_american': v['odds'],
                    'implied_raw': round(v['implied_raw'], 6),
                    'p_shin': round(v['p_shin'], 6),
                    'z': round(v['z'], 6),
                    'overround': round(v['overround'], 4),
                    'method': v['method'],
                    'consensus_p': round(consensus.get(k, 0), 6),
                    'best_odds': best_odds_map.get(k, ('', ''))[0],
                    'best_book': best_odds_map.get(k, ('', ''))[1],
                    'n_books': len(book_results_6way),
                    'ml_consistency_diff': ml_diff,
                }
                all_output.append(row)

    if test_only:
        # Print test output for Gamrot vs Oliveira
        print("\n" + "=" * 80)
        print("TEST: Gamrot vs Oliveira (event 3869)")
        print("=" * 80)

        # Group by book
        by_book = defaultdict(list)
        for r in all_output:
            by_book[r['book']].append(r)

        for book in sorted(by_book):
            rows = by_book[book]
            z = rows[0]['z']
            overround = rows[0]['overround']
            method = rows[0]['method']
            print(f"\n--- {book} (z={z:.6f}, overround={overround:.4f}, method={method}) ---")
            print(f"  {'Prop':<15} {'Fighter':<20} {'Odds':>6} {'impl_raw':>10} {'p_shin':>10}")
            psum = 0
            for r in sorted(rows, key=lambda x: (x['prop_fighter'], x['prop_type'])):
                print(f"  {r['prop_type']:<15} {r['prop_fighter']:<20} {r['odds_american']:>6} {r['implied_raw']:>10.6f} {r['p_shin']:>10.6f}")
                psum += r['p_shin']
            print(f"  {'SUM':<15} {'':<20} {'':>6} {'':>10} {psum:>10.6f}")

            # ML consistency
            fighters = sorted(set(r['prop_fighter'] for r in rows))
            for f in fighters:
                f_rows = [r for r in rows if r['prop_fighter'] == f]
                f_sum = sum(r['p_shin'] for r in f_rows)
                diff = f_rows[0]['ml_consistency_diff']
                flag = ' *** FLAG' if diff != '' and abs(diff) > 0.05 else ''
                print(f"  ML diff {f}: sum_methods={f_sum:.4f}, diff={diff}{flag}")

        # Consensus table
        print(f"\n--- CONSENSUS (median across {all_output[0]['n_books']} books) ---")
        seen = set()
        print(f"  {'Prop':<15} {'Fighter':<20} {'consensus_p':>12} {'best_odds':>10} {'best_book':<12}")
        for r in sorted(all_output, key=lambda x: (x['prop_fighter'], x['prop_type'])):
            k = (r['prop_type'], r['prop_fighter'])
            if k in seen:
                continue
            seen.add(k)
            print(f"  {r['prop_type']:<15} {r['prop_fighter']:<20} {r['consensus_p']:>12.6f} {r['best_odds']:>10} {r['best_book']:<12}")
        return

    # Write output
    with open('bfo_props_devig.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for row in all_output:
            w.writerow(row)

    print(f"\nWrote bfo_props_devig.csv: {len(all_output)} rows")
    print(f"Books processed: {total_books}")
    print(f"Books skipped (incomplete 6-way): {skipped_books}")
    print(f"Fallback to multiplicative: {fallback_count}")
    print(f"ML consistency flags (|diff| > 0.05): {consistency_flags}")


if __name__ == '__main__':
    test = '--test' in sys.argv
    main(test_only=test)
