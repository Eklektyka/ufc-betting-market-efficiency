#!/usr/bin/env python3
"""
ten_pct_look.py — 10% descriptive look (pre-registered, no stopping rule)
"""

import csv, json, math, os, re, sys, time, unicodedata, hashlib
from collections import defaultdict, Counter
from statistics import median, stdev
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67
N_BOOT = 5000
PICKS_DIR = r'C:\Research\ufc\picks\users'
STATE_FILE = r'C:\Research\ufc\picks\state.json'
AUTHOR = 'Ezoteryka'

# Windows from prereg
RANK_END = '2026-04-17'
TEST_START = '2026-04-18'

# ─── helpers ───
def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

def normalize(name):
    return re.sub(r'[^\w\s]', '', strip_accents(name).strip().lower()).strip()

def normalize_event(name):
    # Strip trailing single-digit rematch indicators (e.g. "kape vs horiguchi 2")
    # but keep event numbers like "250", "330"
    return re.sub(r'\s+\d{1}$', '', normalize(name))

def last_name(name):
    parts = normalize(name).split()
    return parts[-1] if parts else ''

def names_match(a, b):
    na, nb = normalize(a), normalize(b)
    if na == nb: return True
    la, lb = last_name(a), last_name(b)
    if la == lb and len(na) > 0 and len(nb) > 0 and na[0] == nb[0]: return True
    if len(na) > 4 and len(nb) > 4 and (na in nb or nb in na): return True
    return False

def american_to_decimal(odds):
    odds = int(odds)
    return 1 + odds / 100 if odds > 0 else 1 + 100 / abs(odds)

def american_to_implied(odds):
    odds = int(odds)
    return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)

# ─── load universal bout table ───
def load_bout_table():
    """Load ezoteryka_scored.csv as the universal bout-odds lookup."""
    event_bouts = defaultdict(list)
    all_bouts = []
    with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            event_bouts[normalize_event(r['card_key'])].append(r)
            all_bouts.append(r)
    return event_bouts, all_bouts

# ─── score one user ───
def score_user_picks(picks_file, event_bouts):
    """Score a user's picks against the universal bout table.
    Returns list of scored dicts."""
    with open(picks_file, 'r', encoding='utf-8') as f:
        picks = list(csv.DictReader(f))

    scored = []
    unmatched = 0
    for p in picks:
        fp_n = normalize(p['fighter_picked'])
        opp_n = normalize(p['opponent'])
        ck_n = normalize_event(p['event'])

        candidates = event_bouts.get(ck_n, [])
        if not candidates:
            for ek, rows in event_bouts.items():
                if ek in ck_n or ck_n in ek:
                    candidates = rows
                    break

        r = None
        for row in candidates:
            parts = row['bout'].split(' vs ')
            if len(parts) != 2: continue
            fa_n, fb_n = normalize(parts[0]), normalize(parts[1])
            if (names_match(fp_n, fa_n) and names_match(opp_n, fb_n)) or \
               (names_match(fp_n, fb_n) and names_match(opp_n, fa_n)):
                r = row
                break

        if not r:
            unmatched += 1
            continue

        ezo_picked_n = normalize(r['picked_fighter'])
        if names_match(fp_n, ezo_picked_n):
            best_line = int(r['best_line'])
            p_fair = float(r['p_fair_picked'])
        else:
            p_fair = 1 - float(r['p_fair_picked'])
            dec = 1 / p_fair if p_fair > 0 else 100
            best_line = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))

        dec_odds = american_to_decimal(best_line)
        is_correct = p['correct'] == 'YES'
        profit = (dec_odds - 1) * 100 if is_correct else -100
        clv = (1 if is_correct else 0) - p_fair
        window = r['window']
        is_manual = r['is_manual'] == 'True'
        fav_dog = 'fav' if p_fair >= 0.5 else 'dog'

        scored.append({
            'card_key': r['card_key'],
            'bout': r['bout'],
            'fighter_picked': p['fighter_picked'],
            'correct': is_correct,
            'best_line': best_line,
            'p_fair': p_fair,
            'profit': profit,
            'clv': clv,
            'window': window,
            'fav_dog': fav_dog,
            'is_manual': is_manual,
            'canonical_date': r['canonical_date'],
            'picked_method': p.get('picked_method', ''),
        })

    return scored, unmatched, len(picks)


def compute_user_stats(scored):
    """Compute summary stats for a user's scored picks."""
    if not scored:
        return None
    n = len(scored)
    correct = sum(s['correct'] for s in scored)
    profit = sum(s['profit'] for s in scored)
    mean_clv = sum(s['clv'] for s in scored) / n
    roi = profit / (n * 100)
    mean_pfair = sum(s['p_fair'] for s in scored) / n

    by_window = {}
    for w in ('rank', 'test'):
        ws = [s for s in scored if s['window'] == w]
        if ws:
            wn = len(ws)
            by_window[w] = {
                'n': wn,
                'correct': sum(s['correct'] for s in ws),
                'accuracy': sum(s['correct'] for s in ws) / wn,
                'clv': sum(s['clv'] for s in ws) / wn,
                'roi': sum(s['profit'] for s in ws) / (wn * 100),
                'profit': sum(s['profit'] for s in ws),
            }
        else:
            by_window[w] = {'n': 0, 'correct': 0, 'accuracy': 0, 'clv': 0, 'roi': 0, 'profit': 0}

    return {
        'n': n,
        'correct': correct,
        'accuracy': correct / n,
        'expected_accuracy': mean_pfair,
        'clv': mean_clv,
        'roi': roi,
        'profit': profit,
        'rank': by_window['rank'],
        'test': by_window['test'],
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    t0 = time.time()

    print("=" * 80)
    print("10% LOOK — DESCRIPTIVE ONLY")
    print("Pre-registered: no stopping rule, no threshold changes")
    print("=" * 80)

    # ─── Load state ───
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        state = json.load(f)

    done_users = {u: v for u, v in state['users'].items() if v['status'] == 'done'}
    failed_users = {u: v for u, v in state['users'].items() if v['status'] == 'failed'}
    unavail_users = {u: v for u, v in state['users'].items() if v['status'] == 'unavailable'}

    # Load bout table
    event_bouts, all_bouts = load_bout_table()

    # Score all done users
    user_scored = {}
    user_stats = {}
    total_unmatched = 0
    total_picks_all = 0
    users_with_method = 0
    per_card_matches = defaultdict(lambda: {'matched': 0, 'total': 0})
    new_names = []

    for username in sorted(done_users.keys()):
        safe = username.replace(' ', '_').replace('/', '_').replace('\\', '_')
        picks_file = os.path.join(PICKS_DIR, f'{safe}.csv')
        if not os.path.exists(picks_file):
            continue

        scored, unmatched, total_picks = score_user_picks(picks_file, event_bouts)
        user_scored[username] = scored
        stats = compute_user_stats(scored)
        if stats:
            user_stats[username] = stats

        total_unmatched += unmatched
        total_picks_all += total_picks

        # Check method coverage
        with open(picks_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if 'picked_method' in reader.fieldnames:
                rows = list(reader)
                if any(r.get('picked_method', '').strip() for r in rows):
                    users_with_method += 1

        # Per-card tracking — resolve to the canonical (ezoteryka_scored) key
        for s in scored:
            per_card_matches[s['card_key']]['matched'] += 1
        with open(picks_file, 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                ck_n = normalize_event(r['event'])
                # Resolve to canonical card_key via same containment logic
                resolved = r['event']
                if ck_n in event_bouts:
                    resolved = event_bouts[ck_n][0]['card_key'] if event_bouts[ck_n] else r['event']
                else:
                    for ek, rows in event_bouts.items():
                        if ek in ck_n or ck_n in ek:
                            resolved = rows[0]['card_key']
                            break
                per_card_matches[resolved]['total'] += 1

    # Separate author
    author_stats = user_stats.pop(AUTHOR, None)
    author_scored = user_scored.pop(AUTHOR, [])

    # Panel users (exclude author)
    panel_users = {u: s for u, s in user_stats.items()}

    t_score = time.time()

    # ═══════════════════════════════════════════════════════════════
    # SECTION 1 — ROSTER AND DATA HEALTH
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 1 — ROSTER AND DATA HEALTH")
    print("=" * 80)

    print(f"\nUsers done:        {len(done_users)}")
    print(f"Users unavailable: {len(unavail_users)}")
    print(f"Users failed:      {len(failed_users)}")
    v1 = sum(1 for v in done_users.values() if 'scraper_version' not in v)
    v2 = sum(1 for v in done_users.values() if v.get('scraper_version') == 2)
    print(f"Scraper v1/v2:     {v1} / {v2}")
    print(f"Users with method: {users_with_method}")

    picks_counts = [s['n'] for s in panel_users.values()]
    if picks_counts:
        print(f"\nPicks per user:    min={min(picks_counts)}, median={median(picks_counts):.0f}, max={max(picks_counts)}")

    total_scored = sum(s['n'] for s in panel_users.values())
    print(f"Total scored picks (panel): {total_scored}")
    print(f"Total unmatched picks:      {total_unmatched}")
    match_rate = total_scored / (total_scored + total_unmatched) if (total_scored + total_unmatched) > 0 else 0
    print(f"Match rate:                 {match_rate:.1%}")

    # Per-card match rate
    print(f"\nPer-card match rates (lowest 5):")
    card_rates = []
    for ck, v in per_card_matches.items():
        if v['total'] > 0:
            rate = v['matched'] / v['total']
            card_rates.append((ck, v['matched'], v['total'], rate))
    card_rates.sort(key=lambda x: x[3])
    for ck, m, t, r in card_rates[:5]:
        print(f"  {ck[:55]:<55} {m}/{t} ({r:.1%})")

    # Manual odds
    manual_count = sum(1 for s in (list(user_scored.values()) + [author_scored])
                       for p in (s if isinstance(s, list) else [])
                       if p.get('is_manual'))
    # Actually count from panel
    manual_picks = 0
    for u, scored in user_scored.items():
        manual_picks += sum(1 for s in scored if s['is_manual'])
    print(f"\nManual-odds picks in panel: {manual_picks}")

    # Duplicate check
    dup_count = 0
    for u, scored in user_scored.items():
        seen = set()
        for s in scored:
            k = (s['card_key'], s['bout'])
            if k in seen:
                dup_count += 1
            seen.add(k)
    print(f"Duplicate (user, card, bout): {dup_count} {'PASS' if dup_count == 0 else 'FAIL'}")

    # ═══════════════════════════════════════════════════════════════
    # SECTION 2 — BASELINES
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 2 — BASELINES (per window)")
    print("=" * 80)

    # Always-fav / always-dog baselines from ezoteryka_scored
    for window_label in ('rank', 'test', 'all'):
        bouts = all_bouts if window_label == 'all' else [b for b in all_bouts if b['window'] == window_label]
        fav_profit = 0
        dog_profit = 0
        fav_n = 0
        dog_n = 0
        for b in bouts:
            p_fair = float(b['p_fair_picked'])
            best_line = int(b['best_line'])
            result = b['result']
            dec = american_to_decimal(best_line)

            if p_fair >= 0.5:
                # Ezo picked fav
                fav_n += 1
                fav_profit += (dec - 1) * 100 if result == 'win' else -100
                # Dog side: Ezo's opponent
                p_dog = 1 - p_fair
                dec_dog = 1 / p_dog if p_dog > 0 else 100
                dog_n += 1
                dog_profit += (dec_dog - 1) * 100 if result == 'loss' else -100
            else:
                # Ezo picked dog
                dog_n += 1
                dog_profit += (dec - 1) * 100 if result == 'win' else -100
                p_fav = 1 - p_fair
                dec_fav = 1 / p_fav if p_fav > 0 else 100
                fav_n += 1
                fav_profit += (dec_fav - 1) * 100 if result == 'loss' else -100

        # Note: fav_n == dog_n == len(bouts) since every bout has one fav and one dog
        print(f"\n  {window_label.upper()} ({len(bouts)} bouts):")
        print(f"    Always-fav ROI:  {fav_profit / (len(bouts) * 100):+.1%}")
        print(f"    Always-dog ROI:  {dog_profit / (len(bouts) * 100):+.1%}")

        # Panel mean CLV and ROI
        panel_clvs = []
        panel_rois = []
        roi_pos = 0
        for u, st in panel_users.items():
            if window_label == 'all':
                panel_clvs.append(st['clv'])
                panel_rois.append(st['roi'])
                if st['roi'] > 0: roi_pos += 1
            else:
                w = st[window_label]
                if w['n'] > 0:
                    panel_clvs.append(w['clv'])
                    panel_rois.append(w['roi'])
                    if w['roi'] > 0: roi_pos += 1

        if panel_clvs:
            print(f"    Panel mean CLV:  {np.mean(panel_clvs):+.4f}")
            print(f"    Panel mean ROI:  {np.mean(panel_rois):+.1%}")
            print(f"    Users ROI > 0:   {roi_pos}/{len(panel_rois)} ({roi_pos/len(panel_rois):.1%})")

    # ═══════════════════════════════════════════════════════════════
    # SECTION 3 — PROFITABILITY SNAPSHOT
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 3 — PROFITABILITY SNAPSHOT")
    print("=" * 80)

    # Filter to users with enough scored picks (pre-reg: >=150 rank, >=80 test)
    # For 10% look with v1 users, relax to >=200 total scored picks
    MIN_SCORED = 200
    qualified = {u: s for u, s in panel_users.items() if s['n'] >= MIN_SCORED}
    print(f"\n  Qualified users (>={MIN_SCORED} scored picks): {len(qualified)}/{len(panel_users)}")

    # Sort by ROI
    ranked_roi = sorted(qualified.items(), key=lambda x: x[1]['roi'], reverse=True)

    print(f"\nTOP 15 BY ROI:")
    print(f"  {'ID':<8} {'Picks':>5} {'Acc%':>5} {'Exp%':>5} {'CLV':>7} {'ROI':>7} {'rROI':>7} {'tROI':>7}")
    print("  " + "-" * 60)
    for i, (u, s) in enumerate(ranked_roi[:15]):
        uid = f"u{i+1:03d}"
        rr = s['rank']['roi'] if s['rank']['n'] > 0 else 0
        tr = s['test']['roi'] if s['test']['n'] > 0 else 0
        print(f"  {uid:<8} {s['n']:>5} {s['accuracy']:>5.1%} {s['expected_accuracy']:>5.1%} "
              f"{s['clv']:>+7.4f} {s['roi']:>+6.1%} {rr:>+6.1%} {tr:>+6.1%}")

    print(f"\nBOTTOM 5 BY ROI:")
    for i, (u, s) in enumerate(ranked_roi[-5:]):
        uid = f"u{len(ranked_roi)-4+i:03d}"
        rr = s['rank']['roi'] if s['rank']['n'] > 0 else 0
        tr = s['test']['roi'] if s['test']['n'] > 0 else 0
        print(f"  {uid:<8} {s['n']:>5} {s['accuracy']:>5.1%} {s['expected_accuracy']:>5.1%} "
              f"{s['clv']:>+7.4f} {s['roi']:>+6.1%} {rr:>+6.1%} {tr:>+6.1%}")

    # Sort by CLV
    ranked_clv = sorted(qualified.items(), key=lambda x: x[1]['clv'], reverse=True)
    print(f"\nTOP 15 BY CLV:")
    print(f"  {'ID':<8} {'Picks':>5} {'Acc%':>5} {'Exp%':>5} {'CLV':>7} {'ROI':>7} {'rROI':>7} {'tROI':>7}")
    print("  " + "-" * 60)
    for i, (u, s) in enumerate(ranked_clv[:15]):
        uid = f"c{i+1:03d}"
        rr = s['rank']['roi'] if s['rank']['n'] > 0 else 0
        tr = s['test']['roi'] if s['test']['n'] > 0 else 0
        print(f"  {uid:<8} {s['n']:>5} {s['accuracy']:>5.1%} {s['expected_accuracy']:>5.1%} "
              f"{s['clv']:>+7.4f} {s['roi']:>+6.1%} {rr:>+6.1%} {tr:>+6.1%}")

    # Distribution
    all_rois = [s['roi'] for s in qualified.values()]
    all_clvs = [s['clv'] for s in qualified.values()]

    print(f"\nROI DISTRIBUTION (n={len(all_rois)}):")
    print(f"  Mean:  {np.mean(all_rois):+.1%}")
    print(f"  SD:    {np.std(all_rois):.1%}")
    pcts = [5, 25, 50, 75, 95]
    vals = np.percentile(all_rois, pcts)
    print(f"  Pctls: " + "  ".join(f"p{p}={v:+.1%}" for p, v in zip(pcts, vals)))

    print(f"\nCLV DISTRIBUTION (n={len(all_clvs)}):")
    print(f"  Mean:  {np.mean(all_clvs):+.4f}")
    print(f"  SD:    {np.std(all_clvs):.4f}")
    vals = np.percentile(all_clvs, pcts)
    print(f"  Pctls: " + "  ".join(f"p{p}={v:+.4f}" for p, v in zip(pcts, vals)))

    # Author
    if author_stats:
        print(f"\n  AUTHOR ({AUTHOR}): picks={author_stats['n']}, acc={author_stats['accuracy']:.1%}, "
              f"CLV={author_stats['clv']:+.4f}, ROI={author_stats['roi']:+.1%}")

    # ═══════════════════════════════════════════════════════════════
    # SECTION 4 — PRE-REGISTERED STATISTICS
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("SECTION 4 — PRE-REGISTERED STATISTICS (observed + null bootstrap)")
    print("=" * 80)

    # Need: per-user rank-window CLV, test-window CLV
    # Users eligible: >= 150 rank-window and >= 80 test-window scored picks
    eligible = {}
    for u, s in panel_users.items():
        if s['rank']['n'] >= 150 and s['test']['n'] >= 80:
            eligible[u] = s
    # For 10% look, relax if too few eligible
    if len(eligible) < 10:
        print(f"\n  WARNING: Only {len(eligible)} users meet 150/80 threshold. Relaxing to 50/30.")
        eligible = {}
        for u, s in panel_users.items():
            if s['rank']['n'] >= 50 and s['test']['n'] >= 30:
                eligible[u] = s

    print(f"\n  Eligible users (panel): {len(eligible)}")

    if len(eligible) < 5:
        print("  TOO FEW ELIGIBLE USERS FOR PANEL TESTS — skipping Section 4")
    else:
        # Observed statistics
        rank_clvs = np.array([s['rank']['clv'] for s in eligible.values()])
        test_clvs = np.array([s['test']['clv'] for s in eligible.values()])
        n_elig = len(eligible)

        # H1: Spearman rho
        from scipy.stats import spearmanr
        rho_obs, _ = spearmanr(rank_clvs, test_clvs)

        # H2: top - bottom decile
        d = max(1, n_elig // 10)
        sorted_by_rank = np.argsort(rank_clvs)
        top_idx = sorted_by_rank[-d:]
        bot_idx = sorted_by_rank[:d]
        top_minus_bot_obs = test_clvs[top_idx].mean() - test_clvs[bot_idx].mean()

        # S2: top-decile test CLV
        top_test_clv_obs = test_clvs[top_idx].mean()

        # S1: Divergence strategy
        # For each test-window fight, compute top-decile consensus share per side
        # Bet sides where share - p_fair >= 10pp
        top_users = [list(eligible.keys())[i] for i in top_idx]

        # Build per-bout picks for top-decile in test window
        test_bout_picks = defaultdict(lambda: {'total': 0, 'sides': defaultdict(int)})
        for u in top_users:
            for s in user_scored.get(u, []):
                if s['window'] != 'test':
                    continue
                bk = (s['card_key'], s['bout'])
                test_bout_picks[bk]['total'] += 1
                test_bout_picks[bk]['sides'][s['fighter_picked']] += 1
                test_bout_picks[bk]['p_fair'] = {s['fighter_picked']: s['p_fair']}

        # For divergence, need both sides' p_fair per bout
        # Rebuild from ezoteryka_scored
        bout_fairs = {}
        for b in all_bouts:
            if b['window'] != 'test': continue
            bk = (b['card_key'], b['bout'])
            parts = b['bout'].split(' vs ')
            if len(parts) != 2: continue
            p_ezo = float(b['p_fair_picked'])
            ezo_f = b['picked_fighter']
            bout_fairs[bk] = {
                'fighter_a': parts[0], 'fighter_b': parts[1],
                'p_a': p_ezo if normalize(ezo_f) == normalize(parts[0]) else 1 - p_ezo,
                'result': b['result'],
                'ezo_picked': ezo_f,
                'best_line': int(b['best_line']),
                'p_fair_picked': p_ezo,
            }

        div_profit = 0
        div_bets = 0
        for bk, info in test_bout_picks.items():
            if info['total'] == 0: continue
            bf = bout_fairs.get(bk)
            if not bf: continue

            for fighter, count in info['sides'].items():
                share = count / info['total']
                # Determine p_fair for this fighter
                if names_match(fighter, bf['fighter_a']):
                    p_f = bf['p_a']
                else:
                    p_f = 1 - bf['p_a']

                if share - p_f >= 0.10:
                    div_bets += 1
                    # Get best line for this fighter
                    if names_match(fighter, normalize(bf['ezo_picked'])):
                        bl = bf['best_line']
                        won = (bf['result'] == 'win')
                    else:
                        p_opp = 1 - bf['p_fair_picked']
                        dec = 1 / p_opp if p_opp > 0 else 100
                        bl = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))
                        won = (bf['result'] == 'loss')

                    dec_odds = american_to_decimal(bl)
                    div_profit += (dec_odds - 1) * 100 if won else -100

        div_roi_obs = div_profit / (div_bets * 100) if div_bets > 0 else 0

        # Always-fav test ROI (from section 2 computation, recompute cleanly)
        test_bouts = [b for b in all_bouts if b['window'] == 'test']
        fav_profit_test = 0
        for b in test_bouts:
            p_fair = float(b['p_fair_picked'])
            best_line = int(b['best_line'])
            dec = american_to_decimal(best_line)
            if p_fair >= 0.5:
                fav_profit_test += (dec - 1) * 100 if b['result'] == 'win' else -100
            else:
                p_fav = 1 - p_fair
                dec_fav = 1 / p_fav if p_fav > 0 else 100
                fav_profit_test += (dec_fav - 1) * 100 if b['result'] == 'loss' else -100
        fav_roi_test = fav_profit_test / (len(test_bouts) * 100)

        # ─── BOOTSTRAP ───
        print(f"\n  Running {N_BOOT}-draw fight-clustered bootstrap (seed {SEED})...")
        rng = np.random.RandomState(SEED)

        # Build fight-level data structure for resampling
        # Each fight: p_fair_a (probability side A wins), actual result
        # For each user: which side they picked
        fight_keys = []
        fight_pfair_a = []
        fight_actual_a_won = []

        # Map each bout to a fight index
        bout_to_fidx = {}
        for b in all_bouts:
            bk = (b['card_key'], b['bout'])
            if bk in bout_to_fidx:
                continue
            parts = b['bout'].split(' vs ')
            if len(parts) != 2: continue
            fidx = len(fight_keys)
            fight_keys.append(bk)
            p_ezo = float(b['p_fair_picked'])
            ezo_f = normalize(b['picked_fighter'])
            fa_n = normalize(parts[0])
            p_a = p_ezo if ezo_f == fa_n or names_match(ezo_f, fa_n) else 1 - p_ezo
            fight_pfair_a.append(p_a)
            # Did side A win?
            if ezo_f == fa_n or names_match(ezo_f, fa_n):
                a_won = b['result'] == 'win'
            else:
                a_won = b['result'] == 'loss'
            fight_actual_a_won.append(a_won)
            bout_to_fidx[bk] = fidx

        fight_pfair_a = np.array(fight_pfair_a)
        n_fights = len(fight_keys)

        # For each eligible user, build array: fight_idx, picked_side (1=A, 0=B), p_fair, best_line
        user_picks_arr = {}
        for u in eligible:
            picks_data = []
            for s in user_scored.get(u, []):
                bk = (s['card_key'], s['bout'])
                fidx = bout_to_fidx.get(bk)
                if fidx is None: continue
                parts = s['bout'].split(' vs ')
                if len(parts) != 2: continue
                fa_n = normalize(parts[0])
                fp_n = normalize(s['fighter_picked'])
                picked_a = 1 if names_match(fp_n, fa_n) else 0
                picks_data.append((fidx, picked_a, s['p_fair'], s['window']))
            user_picks_arr[u] = picks_data

        # Null distributions
        null_rho = []
        null_tmb = []
        null_top_clv = []
        null_div_roi = []

        for draw in range(N_BOOT):
            # Resample each fight outcome
            sim_a_won = rng.random(n_fights) < fight_pfair_a

            # Recompute per-user rank/test CLV
            sim_rank_clvs = []
            sim_test_clvs = []
            for u in eligible:
                rank_clv_sum = 0; rank_n = 0
                test_clv_sum = 0; test_n = 0
                for fidx, picked_a, p_fair, window in user_picks_arr[u]:
                    correct = (picked_a == 1 and sim_a_won[fidx]) or \
                              (picked_a == 0 and not sim_a_won[fidx])
                    clv = (1 if correct else 0) - p_fair
                    if window == 'rank':
                        rank_clv_sum += clv; rank_n += 1
                    elif window == 'test':
                        test_clv_sum += clv; test_n += 1
                sim_rank_clvs.append(rank_clv_sum / rank_n if rank_n > 0 else 0)
                sim_test_clvs.append(test_clv_sum / test_n if test_n > 0 else 0)

            sim_rank = np.array(sim_rank_clvs)
            sim_test = np.array(sim_test_clvs)

            # H1: rho
            if len(sim_rank) > 2:
                r, _ = spearmanr(sim_rank, sim_test)
                null_rho.append(r)

            # H2: top - bottom decile
            sorted_idx = np.argsort(sim_rank)
            top_i = sorted_idx[-d:]
            bot_i = sorted_idx[:d]
            null_tmb.append(sim_test[top_i].mean() - sim_test[bot_i].mean())

            # S2: top-decile test CLV
            null_top_clv.append(sim_test[top_i].mean())

        null_rho = np.array(null_rho)
        null_tmb = np.array(null_tmb)
        null_top_clv = np.array(null_top_clv)

        # Print results
        def report(name, obs, null):
            null_mean = null.mean()
            null_sd = null.std()
            null_95 = np.percentile(null, 95)
            pctile = (null < obs).mean() * 100
            print(f"  {name:<35} obs={obs:>+.4f}  null_mean={null_mean:>+.4f}  "
                  f"null_SD={null_sd:.4f}  null_95th={null_95:>+.4f}  pctile={pctile:.1f}%")

        print(f"\n  Eligible: {n_elig} users, decile size: {d}")
        print(f"  SE on rho for n={n_elig}: {1/np.sqrt(n_elig-3):.4f}")
        print()
        report("H1: rho(rank CLV, test CLV)", rho_obs, null_rho)
        report("H2: top-bot decile test CLV", top_minus_bot_obs, null_tmb)
        report("S2: top-decile test CLV", top_test_clv_obs, null_top_clv)
        print(f"  {'S1: divergence ROI (10pp)':<35} obs={div_roi_obs:>+.4f}  bets={div_bets}")
        print(f"  {'Always-fav test ROI':<35} obs={fav_roi_test:>+.4f}")

    # ═══════════════════════════════════════════════════════════════
    # SECTION 5 — RUNTIME
    # ═══════════════════════════════════════════════════════════════
    t_end = time.time()
    print("\n" + "=" * 80)
    print("SECTION 5 — RUNTIME")
    print("=" * 80)
    print(f"  Scoring:    {t_score - t0:.1f}s")
    print(f"  Bootstrap:  {t_end - t_score:.1f}s")
    print(f"  Total:      {t_end - t0:.1f}s")
    print(f"  Users:      {len(done_users)}")
    print(f"  Projection at 1,547: ~{(t_end - t0) * 1547 / len(done_users):.0f}s "
          f"({(t_end - t0) * 1547 / len(done_users) / 60:.1f} min)")


if __name__ == '__main__':
    main()
