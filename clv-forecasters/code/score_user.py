#!/usr/bin/env python3
"""Score a Tapology user's picks against BFO closing odds."""

import csv, os, re, unicodedata, argparse, numpy as np
from collections import defaultdict
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))

RANK_CUTOFF = '2026-04-17'  # rank window ≤ this date
SEED = 42
N_RESAMPLE = 5000
STAKE = 100

# ── Normalisation (same as ezo_join.py) ──

_CHAR_MAP = str.maketrans({
    '\u0142': 'l', '\u0141': 'L', '\u00f8': 'o', '\u00d8': 'O',
    '\u0111': 'd', '\u0110': 'D', '\u00df': 'ss',
    '\u2019': '', "'": '', '-': ' ',
})

def normalize(name):
    name = name.translate(_CHAR_MAP)
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.lower().strip()
    name = re.sub(r'\s+(jr|sr|ii|iii|iv)\.?$', '', name)
    return re.sub(r'\s+', ' ', name)

def token_set(name):
    return frozenset(normalize(name).split())


# ── Load overrides ──

def load_overrides():
    aliases = defaultdict(set)
    if not os.path.exists('name_overrides.csv'):
        return aliases
    with open('name_overrides.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['bfo_name'] and row['tapology_name']:
                nb = normalize(row['bfo_name'])
                nt = normalize(row['tapology_name'])
                aliases[nb].add(nt)
                aliases[nt].add(nb)
    # Transitive closure
    changed = True
    while changed:
        changed = False
        for name, als in list(aliases.items()):
            expanded = set(als)
            for a in als:
                expanded |= aliases.get(a, set())
            expanded.discard(name)
            if expanded != als:
                aliases[name] = expanded
                changed = True
    return aliases


# ── Load card_map ──

def load_card_map():
    cm = {}
    with open('card_map.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            cm[row['bfo_event_id']] = row
    return cm


# ── Load BFO odds index ──

def load_bfo_index(card_map, include_manual=True):
    """Returns {card_key: {norm_pair: {side1_name, side2_name, best_line_1, best_line_2,
       p_fair_1, p_fair_2, is_manual, canonical_date}}}"""
    eid_to_ck = {eid: cm['card_key'] for eid, cm in card_map.items()}
    eid_to_date = {eid: cm['canonical_date'] for eid, cm in card_map.items()}

    # Load per-book odds from all sources
    odds_files = ['bfo_odds_rank.csv', 'bfo_odds_ext_2026.csv']
    per_book = defaultdict(lambda: {'f1': {}, 'f2': {}, 'meta': {}})
    # key: (card_key, matchup_id)

    for ofile in odds_files:
        if not os.path.exists(ofile):
            continue
        with open(ofile, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                eid = row['bfo_event_id']
                ck = eid_to_ck.get(eid, row.get('event_name', ''))
                mid = row['bfo_matchup_id']
                side = str(row['fighter_side'])
                is_book = int(row['is_book'])
                odds = int(row['odds_american'])
                if odds == 0:
                    continue
                key = 'f1' if side == '1' else 'f2'
                if is_book == 1:
                    per_book[(ck, mid)][key][row['book']] = odds
                per_book[(ck, mid)]['meta'][f'f{side}_name'] = row['fighter_name']
                per_book[(ck, mid)]['meta']['eid'] = eid

    def implied_prob(a):
        if a > 0:
            return 1 / (1 + a / 100)
        elif a < 0:
            return 1 / (1 + 100 / abs(a))
        return 0.5

    index = defaultdict(dict)

    for (ck, mid), data in per_book.items():
        f1_sb = {b: o for b, o in data['f1'].items() if b not in ('Polymarket', 'Kalshi')}
        f2_sb = {b: o for b, o in data['f2'].items() if b not in ('Polymarket', 'Kalshi')}
        if not f1_sb or not f2_sb:
            continue
        best1 = max(f1_sb.values())
        best2 = max(f2_sb.values())
        p1 = implied_prob(best1)
        p2 = implied_prob(best2)
        total = p1 + p2
        eid = data['meta'].get('eid', '')
        cdate = eid_to_date.get(eid, '')
        f1_name = data['meta'].get('f1_name', '')
        f2_name = data['meta'].get('f2_name', '')
        pair = frozenset({normalize(f1_name), normalize(f2_name)})

        entry = {
            'f1': f1_name, 'f2': f2_name,
            'best_line_1': best1, 'best_line_2': best2,
            'p_fair_1': p1 / total, 'p_fair_2': p2 / total,
            'canonical_date': cdate, 'is_manual': False,
        }
        if pair not in index[ck]:
            index[ck][pair] = entry

    # Manual entries
    if include_manual and os.path.exists('bfo_close_manual.csv'):
        with open('bfo_close_manual.csv', 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                eid = row['bfo_event_id']
                ck_cm = card_map.get(eid, {})
                ck = ck_cm.get('card_key', row.get('event_name', ''))
                cdate = ck_cm.get('canonical_date', row.get('event_date', ''))
                f1 = row['fighter1_name']
                f2 = row['fighter2_name']
                pair = frozenset({normalize(f1), normalize(f2)})
                entry = {
                    'f1': f1, 'f2': f2,
                    'best_line_1': int(row['best_line_a']),
                    'best_line_2': int(row['best_line_b']),
                    'p_fair_1': float(row['p_fair_a']),
                    'p_fair_2': float(row['p_fair_b']),
                    'canonical_date': cdate, 'is_manual': True,
                }
                if pair not in index[ck]:
                    index[ck][pair] = entry

    return index


# ── Event name mapping ──

def build_event_map(tap_events, bfo_card_keys):
    TAP_OVERRIDES = {
        'UFC Freedom 250: Topuria vs. Gaethje': 'UFC Freedom 250',
    }

    def event_number(name):
        m = re.search(r'ufc\s+(\d{3})', normalize(name))
        return int(m.group(1)) if m else None

    tap_to_ck = {}
    for te in tap_events:
        if te in TAP_OVERRIDES:
            tap_to_ck[te] = TAP_OVERRIDES[te]
            continue
        norm_te = normalize(te)
        if te in bfo_card_keys:
            tap_to_ck[te] = te
            continue
        for ck in bfo_card_keys:
            if normalize(ck) == norm_te:
                tap_to_ck[te] = ck
                break
        else:
            stripped = re.sub(r'\s+\d+$', '', norm_te)
            for ck in bfo_card_keys:
                if normalize(ck) == stripped:
                    tap_to_ck[te] = ck
                    break
            else:
                te_num = event_number(te)
                if te_num:
                    for ck in bfo_card_keys:
                        if event_number(ck) == te_num:
                            tap_to_ck[te] = ck
                            break
                if te not in tap_to_ck:
                    m = re.search(r':\s*(.+?)\s+vs\.?\s+(.+?)$', norm_te)
                    if m:
                        h1, h2 = m.group(1).split()[-1], m.group(2).split()[-1]
                        for ck in bfo_card_keys:
                            nck = normalize(ck)
                            if h1 in nck and h2 in nck:
                                te_n, ck_n = event_number(te), event_number(ck)
                                if te_n and ck_n and te_n != ck_n:
                                    continue
                                tap_to_ck[te] = ck
                                break
    return tap_to_ck


# ── Match a single pick ──

def match_pick(fighter_picked, opponent, card_key, bfo_index, aliases):
    """Find BFO entry for this bout. Returns (entry, side_idx) or (None, None)."""
    matchups = bfo_index.get(card_key, {})
    if not matchups:
        return None, None

    fn_p = normalize(fighter_picked)
    fn_o = normalize(opponent)
    pair = frozenset({fn_p, fn_o})

    # Expand with aliases
    all_pairs = {pair}
    variants_p = {fn_p} | aliases.get(fn_p, set())
    variants_o = {fn_o} | aliases.get(fn_o, set())
    for vp in variants_p:
        for vo in variants_o:
            all_pairs.add(frozenset({vp, vo}))

    # Also try token sets
    ts_p = frozenset(fn_p.split())
    ts_o = frozenset(fn_o.split())
    for vp in variants_p:
        for vo in variants_o:
            all_pairs.add(frozenset({frozenset(vp.split()), frozenset(vo.split())}))

    for bp, entry in matchups.items():
        if bp in all_pairs:
            # Determine which side the picked fighter is
            if normalize(entry['f1']) in variants_p:
                return entry, 1
            elif normalize(entry['f2']) in variants_p:
                return entry, 2
            # Token-set fallback
            ts_f1 = frozenset(normalize(entry['f1']).split())
            ts_f2 = frozenset(normalize(entry['f2']).split())
            if ts_f1 & {frozenset(v.split()) for v in variants_p}:
                return entry, 1
            if ts_f2 & {frozenset(v.split()) for v in variants_p}:
                return entry, 2
            return entry, 1  # fallback

        # Token-set match on the entry
        bp_ts = frozenset({token_set(entry['f1']), token_set(entry['f2'])})
        for ap in all_pairs:
            if isinstance(list(ap)[0], frozenset):
                if ap == bp_ts:
                    ts_f1 = token_set(entry['f1'])
                    if ts_p in {token_set(v) for v in variants_p} or ts_p == ts_f1:
                        return entry, 1
                    return entry, 2

    return None, None


# ── American to decimal ──

def american_to_decimal(a):
    a = int(a)
    if a > 0:
        return 1 + a / 100
    else:
        return 1 + 100 / abs(a)


# ── Main scoring function ──

def score_user(picks_path, output_prefix, include_manual=True):
    card_map = load_card_map()
    aliases = load_overrides()
    bfo = load_bfo_index(card_map, include_manual=include_manual)

    # Load picks
    picks = []
    with open(picks_path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            picks.append(row)

    # Build event map
    tap_events = sorted(set(p['event'] for p in picks))
    tap_to_ck = build_event_map(tap_events, set(bfo.keys()))

    # Score each pick
    scored = []
    for p in picks:
        te = p['event']
        ck = tap_to_ck.get(te, '')
        entry, side = match_pick(p['fighter_picked'], p['opponent'], ck, bfo, aliases)

        if entry is None:
            continue  # unmatched

        best_line = entry[f'best_line_{side}']
        p_fair = entry[f'p_fair_{side}']
        decimal_odds = american_to_decimal(best_line)
        is_manual = entry['is_manual']
        cdate = entry['canonical_date']

        # Result
        actual_winner = p.get('actual_winner', '')
        correct = p.get('correct', '')
        if correct == 'YES':
            result = 'win'
        elif correct == 'NO':
            result = 'loss'
        else:
            result = 'push'

        # Profit at flat stake
        if result == 'win':
            profit = STAKE * (decimal_odds - 1)
        elif result == 'loss':
            profit = -STAKE
        else:
            profit = 0

        # Window
        window = 'rank' if cdate <= RANK_CUTOFF else 'test'

        # Fav / dog
        fav_dog = 'fav' if p_fair > 0.5 else 'dog'

        scored.append({
            'card_key': ck,
            'bout': f'{p["fighter_picked"]} vs {p["opponent"]}',
            'picked_fighter': p['fighter_picked'],
            'result': result,
            'best_line': best_line,
            'decimal_odds': round(decimal_odds, 4),
            'p_fair_picked': round(p_fair, 4),
            'profit': round(profit, 2),
            'window': window,
            'fav_dog': fav_dog,
            'is_manual': is_manual,
            'canonical_date': cdate,
        })

    # Write per-pick CSV
    picks_out = f'{output_prefix}_scored.csv'
    with open(picks_out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(scored[0].keys()))
        w.writeheader()
        w.writerows(scored)

    # ── Summary ──
    def summarize(rows, label):
        if not rows:
            return {'label': label, 'n': 0}
        n = len(rows)
        wins = sum(1 for r in rows if r['result'] == 'win')
        acc = wins / n
        exp_acc = np.mean([r['p_fair_picked'] for r in rows])
        total_profit = sum(r['profit'] for r in rows)
        staked = n * STAKE
        roi = total_profit / staked
        clv_edge = np.mean([
            (1 if r['result'] == 'win' else 0) - r['p_fair_picked']
            for r in rows
        ])
        return {
            'label': label, 'n': n, 'accuracy': round(acc, 4),
            'expected_accuracy': round(exp_acc, 4),
            'roi': round(roi, 4), 'clv_edge': round(clv_edge, 4),
            'total_profit': round(total_profit, 2), 'staked': staked,
        }

    # Splits
    all_rows = scored
    rank_rows = [r for r in scored if r['window'] == 'rank']
    test_rows = [r for r in scored if r['window'] == 'test']
    fav_rows = [r for r in scored if r['fav_dog'] == 'fav']
    dog_rows = [r for r in scored if r['fav_dog'] == 'dog']
    rank_fav = [r for r in rank_rows if r['fav_dog'] == 'fav']
    rank_dog = [r for r in rank_rows if r['fav_dog'] == 'dog']
    test_fav = [r for r in test_rows if r['fav_dog'] == 'fav']
    test_dog = [r for r in test_rows if r['fav_dog'] == 'dog']

    summaries = [
        summarize(all_rows, 'all'),
        summarize(rank_rows, 'rank'),
        summarize(test_rows, 'test'),
        summarize(fav_rows, 'all_fav'),
        summarize(dog_rows, 'all_dog'),
        summarize(rank_fav, 'rank_fav'),
        summarize(rank_dog, 'rank_dog'),
        summarize(test_fav, 'test_fav'),
        summarize(test_dog, 'test_dog'),
    ]

    # ── Null distribution (resample) ──
    rng = np.random.default_rng(SEED)

    def null_roi(rows, n_sim):
        if not rows:
            return None
        p_fairs = np.array([r['p_fair_picked'] for r in rows])
        dec_odds = np.array([r['decimal_odds'] for r in rows])
        n = len(rows)
        staked = n * STAKE

        roi_dist = np.empty(n_sim)
        for i in range(n_sim):
            wins = rng.random(n) < p_fairs
            profits = np.where(wins, STAKE * (dec_odds - 1), -STAKE)
            roi_dist[i] = profits.sum() / staked
        return roi_dist

    null_results = {}
    for label, rows in [('rank', rank_rows), ('test', test_rows), ('all', all_rows)]:
        dist = null_roi(rows, N_RESAMPLE)
        if dist is None:
            continue
        s = summarize(rows, label)
        obs_roi = s['roi']
        null_results[label] = {
            'mean': round(np.mean(dist), 4),
            'sd': round(np.std(dist), 4),
            'ci_lo': round(np.percentile(dist, 2.5), 4),
            'ci_hi': round(np.percentile(dist, 97.5), 4),
            'p_one_sided': round(np.mean(dist >= obs_roi), 4),
            'observed_roi': obs_roi,
        }

    # ── Write summary markdown ──
    md_out = f'{output_prefix}_summary.md'
    with open(md_out, 'w', encoding='utf-8') as f:
        f.write(f'# {output_prefix} Scoring Summary\n\n')
        f.write(f'Picks file: `{picks_path}`\n')
        f.write(f'Rank window: ≤ {RANK_CUTOFF} | Test window: > {RANK_CUTOFF}\n')
        f.write(f'include_manual: {include_manual}\n\n')

        f.write('## Per-split summary\n\n')
        f.write('| Split | n | Accuracy | Exp. Accuracy | ROI | CLV Edge |\n')
        f.write('|-------|---|----------|---------------|-----|----------|\n')
        for s in summaries:
            if s['n'] == 0:
                continue
            f.write(f'| {s["label"]} | {s["n"]} | '
                    f'{s["accuracy"]:.1%} | {s["expected_accuracy"]:.1%} | '
                    f'{s["roi"]:.1%} | {s["clv_edge"]:+.4f} |\n')

        f.write('\n## Null distribution (5000 resamples, seed 42)\n\n')
        f.write('| Window | Obs. ROI | Null mean | Null SD | 95% band | p (one-sided) |\n')
        f.write('|--------|----------|-----------|---------|----------|---------------|\n')
        for label in ['all', 'rank', 'test']:
            if label not in null_results:
                continue
            nr = null_results[label]
            f.write(f'| {label} | {nr["observed_roi"]:.1%} | '
                    f'{nr["mean"]:.1%} | {nr["sd"]:.1%} | '
                    f'[{nr["ci_lo"]:.1%}, {nr["ci_hi"]:.1%}] | '
                    f'{nr["p_one_sided"]:.4f} |\n')

        f.write('\n')

    # Print summary
    print(f'\nScored {len(scored)}/{len(picks)} picks -> {picks_out}')
    print(f'\n{"Split":<12} {"n":>4} {"Acc":>7} {"Exp":>7} {"ROI":>7} {"CLV":>8}')
    print('-' * 50)
    for s in summaries:
        if s['n'] == 0:
            continue
        print(f'{s["label"]:<12} {s["n"]:>4} {s["accuracy"]:>7.1%} '
              f'{s["expected_accuracy"]:>7.1%} {s["roi"]:>7.1%} {s["clv_edge"]:>+8.4f}')

    print(f'\n{"Window":<8} {"Obs ROI":>8} {"Null μ":>8} {"Null σ":>8} {"95% band":>16} {"p":>8}')
    print('-' * 60)
    for label in ['all', 'rank', 'test']:
        if label not in null_results:
            continue
        nr = null_results[label]
        print(f'{label:<8} {nr["observed_roi"]:>8.1%} {nr["mean"]:>8.1%} '
              f'{nr["sd"]:>8.1%} [{nr["ci_lo"]:>6.1%},{nr["ci_hi"]:>6.1%}] '
              f'{nr["p_one_sided"]:>8.4f}')

    return scored, summaries, null_results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--picks', default=r'C:\Users\micha\OneDrive\Pulpit\ufc_scraper\ezoteryka_picks.csv')
    parser.add_argument('--prefix', default='ezoteryka')
    parser.add_argument('--no-manual', action='store_true')
    args = parser.parse_args()

    scored, summaries, null_results = score_user(
        args.picks, args.prefix, include_manual=not args.no_manual)
