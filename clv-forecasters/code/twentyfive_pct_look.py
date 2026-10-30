#!/usr/bin/env python3
"""
twentyfive_pct_look.py — 25% pre-registered efficacy look
Seed 67 everywhere. Real usernames.
"""

import csv, json, math, os, re, sys, time, unicodedata
from collections import defaultdict, Counter
from statistics import median
import numpy as np
from scipy.stats import spearmanr

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67
N_BOOT = 5000
PICKS_DIR = r'C:\Research\ufc\picks\users'
STATE_FILE = r'C:\Research\ufc\picks\state.json'
AUTHOR = 'Ezoteryka'
MIN_SCORED = 200
RANK_END = '2026-04-17'
TEST_START = '2026-04-18'

# ─── helpers ───
def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
def normalize(name):
    return re.sub(r'[^\w\s]', '', strip_accents(name).strip().lower()).strip()
def normalize_event(name):
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

METHOD_MAP = {'ko/tko': 'ko_tko', 'tko/ko': 'ko_tko', 'ko': 'ko_tko', 'tko': 'ko_tko',
              'submission': 'submission', 'sub': 'submission', 'decision': 'decision', 'dec': 'decision'}

def map_tap_method(raw):
    return METHOD_MAP.get(raw.strip().lower())

def map_actual_method(raw):
    raw = raw.strip().lower()
    if 'ko' in raw or 'tko' in raw: return 'ko_tko'
    if 'submission' in raw: return 'submission'
    if 'decision' in raw: return 'decision'
    return None

# ─── load bout table ───
def load_bout_table():
    event_bouts = defaultdict(list)
    all_bouts = []
    with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            event_bouts[normalize_event(r['card_key'])].append(r)
            all_bouts.append(r)
    return event_bouts, all_bouts

# ─── load props ───
def load_props():
    bouts = {}
    with open('bfo_props_devig.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            key = (r['bfo_event_id'], r['bfo_matchup_id'])
            if key not in bouts:
                bouts[key] = {'fighter_a': r['fighter_a'], 'fighter_b': r['fighter_b'],
                              'event_name': r['event_name'], 'outcomes': {}}
            ok = (r['prop_type'], normalize(r['prop_fighter']))
            if ok not in bouts[key]['outcomes']:
                bouts[key]['outcomes'][ok] = {
                    'consensus_p': float(r['consensus_p']),
                    'best_odds': int(r['best_odds']) if r['best_odds'] else None,
                    'best_book': r['best_book'], 'n_books': int(r['n_books']),
                }
    return bouts

def load_card_map():
    cm = defaultdict(list)
    with open('card_map.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            cm[r['card_key']].append(r['bfo_event_id'])
    return cm

def load_name_overrides():
    ov = {}
    with open('name_overrides.csv', 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            ov[normalize(r['tapology_name'])] = normalize(r['bfo_name'])
    return {v: k for k, v in ov.items()}, ov

# ─── score user moneyline ───
def score_user_ml(picks_file, event_bouts):
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
                    candidates = rows; break
        r = None
        for row in candidates:
            parts = row['bout'].split(' vs ')
            if len(parts) != 2: continue
            fa_n, fb_n = normalize(parts[0]), normalize(parts[1])
            if (names_match(fp_n, fa_n) and names_match(opp_n, fb_n)) or \
               (names_match(fp_n, fb_n) and names_match(opp_n, fa_n)):
                r = row; break
        if not r:
            unmatched += 1; continue
        ezo_picked_n = normalize(r['picked_fighter'])
        if names_match(fp_n, ezo_picked_n):
            best_line = int(r['best_line']); p_fair = float(r['p_fair_picked'])
        else:
            p_fair = 1 - float(r['p_fair_picked'])
            dec = 1 / p_fair if p_fair > 0 else 100
            best_line = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))
        is_correct = p['correct'] == 'YES'
        dec_odds = american_to_decimal(best_line)
        profit = (dec_odds - 1) * 100 if is_correct else -100
        clv = (1 if is_correct else 0) - p_fair
        scored.append({
            'card_key': r['card_key'], 'bout': r['bout'],
            'fighter_picked': p['fighter_picked'], 'correct': is_correct,
            'best_line': best_line, 'p_fair': p_fair, 'profit': profit,
            'clv': clv, 'window': r['window'], 'is_manual': r['is_manual'] == 'True',
            'fav_dog': 'fav' if p_fair >= 0.5 else 'dog',
            'canonical_date': r['canonical_date'],
            'picked_method': p.get('picked_method', ''),
            'actual_method': p.get('actual_method', ''),
            'opponent': p['opponent'],
        })
    return scored, unmatched, len(picks)

# ─── score user methods ───
def score_user_methods(scored_ml, card_map, props, rev_overrides, tap_overrides):
    method_scored = []
    for s in scored_ml:
        pm_raw = s.get('picked_method', '').strip()
        if not pm_raw: continue
        pm = map_tap_method(pm_raw)
        if pm is None: continue
        am = map_actual_method(s.get('actual_method', ''))
        if am is None: continue

        event = s['card_key']
        event_ids = card_map.get(event, [])
        if not event_ids:
            for ck in card_map:
                if normalize_event(ck) == normalize_event(event) or \
                   normalize_event(ck) in normalize_event(event) or \
                   normalize_event(event) in normalize_event(ck):
                    event_ids = card_map[ck]; break
        if not event_ids: continue

        fp_n = normalize(s['fighter_picked'])
        opp_n = normalize(s['opponent'])
        fp_bfo = tap_overrides.get(fp_n, fp_n)

        bout_key = None; matched_pf = None
        for eid in event_ids:
            for (eid2, mid), bout in props.items():
                if eid2 != eid: continue
                fa_n = normalize(bout['fighter_a']); fb_n = normalize(bout['fighter_b'])
                matched_fa = names_match(fp_bfo, fa_n) or names_match(fp_n, fa_n)
                matched_fb = names_match(fp_bfo, fb_n) or names_match(fp_n, fb_n)
                opp_fa = names_match(opp_n, fa_n) or names_match(normalize(s['opponent']), fa_n)
                opp_fb = names_match(opp_n, fb_n) or names_match(normalize(s['opponent']), fb_n)
                if (matched_fa and opp_fb) or (matched_fb and opp_fa):
                    prop_fighters = set(fn for (_, fn) in bout['outcomes'].keys())
                    for pf_n in prop_fighters:
                        if names_match(fp_n, pf_n) or names_match(fp_bfo, pf_n):
                            bout_key = (eid2, mid); matched_pf = pf_n; break
                    break
            if bout_key: break
        if not bout_key or not matched_pf: continue

        bout = props[bout_key]
        outcome_key = (pm, matched_pf)
        if outcome_key not in bout['outcomes']: continue

        oc = bout['outcomes'][outcome_key]
        if oc['n_books'] < 1: continue

        consensus_p = oc['consensus_p']
        best_odds = oc['best_odds']
        joint_hit = 1 if (s['correct'] and am == pm) else 0
        joint_clv = joint_hit - consensus_p
        joint_profit = ((american_to_decimal(best_odds) - 1) * 100 if joint_hit else -100) if best_odds else None

        cond_hit = None; p_cond = None; cond_clv = None
        if s['correct']:
            cond_hit = 1 if am == pm else 0
            fighter_total = sum(v['consensus_p'] for (pt, fn), v in bout['outcomes'].items()
                               if fn == matched_pf and pt in ('ko_tko', 'submission', 'decision'))
            if fighter_total > 0:
                p_cond = consensus_p / fighter_total
                cond_clv = cond_hit - p_cond

        method_scored.append({
            'event': s['card_key'], 'bout': s['bout'],
            'fighter_picked': s['fighter_picked'], 'picked_method': pm,
            'actual_method': am, 'fighter_correct': s['correct'],
            'method_correct': am == pm, 'joint_hit': joint_hit,
            'consensus_p': consensus_p, 'joint_clv': joint_clv,
            'best_odds': best_odds, 'joint_profit': joint_profit,
            'cond_hit': cond_hit, 'p_cond': p_cond, 'cond_clv': cond_clv,
            'window': s['window'],
        })
    return method_scored

def user_ml_stats(scored):
    if not scored: return None
    n = len(scored)
    correct = sum(s['correct'] for s in scored)
    profit = sum(s['profit'] for s in scored)
    mean_clv = sum(s['clv'] for s in scored) / n
    mean_pfair = sum(s['p_fair'] for s in scored) / n
    fav_share = sum(1 for s in scored if s['fav_dog'] == 'fav') / n
    by_w = {}
    for w in ('rank', 'test'):
        ws = [s for s in scored if s['window'] == w]
        if ws:
            wn = len(ws)
            by_w[w] = {'n': wn, 'correct': sum(s['correct'] for s in ws),
                       'accuracy': sum(s['correct'] for s in ws) / wn,
                       'clv': sum(s['clv'] for s in ws) / wn,
                       'roi': sum(s['profit'] for s in ws) / (wn * 100),
                       'profit': sum(s['profit'] for s in ws)}
        else:
            by_w[w] = {'n': 0, 'correct': 0, 'accuracy': 0, 'clv': 0, 'roi': 0, 'profit': 0}
    return {'n': n, 'correct': correct, 'accuracy': correct/n, 'expected_accuracy': mean_pfair,
            'clv': mean_clv, 'roi': profit/(n*100), 'profit': profit, 'fav_share': fav_share,
            'rank': by_w['rank'], 'test': by_w['test']}

def user_method_stats(method_scored):
    if not method_scored: return None
    n = len(method_scored)
    jh = sum(s['joint_hit'] for s in method_scored)
    mean_cp = sum(s['consensus_p'] for s in method_scored) / n
    mean_jclv = sum(s['joint_clv'] for s in method_scored) / n
    profits = [s['joint_profit'] for s in method_scored if s['joint_profit'] is not None]
    jroi = sum(profits) / (len(profits) * 100) if profits else 0
    cond = [s for s in method_scored if s['cond_hit'] is not None]
    if cond:
        cn = len(cond); ch = sum(s['cond_hit'] for s in cond)
        mean_pcond = sum(s['p_cond'] for s in cond if s['p_cond'] is not None) / cn
        mean_cclv = sum(s['cond_clv'] for s in cond if s['cond_clv'] is not None) / cn
    else:
        cn = ch = 0; mean_pcond = mean_cclv = 0
    by_w = {}
    for w in ('rank', 'test'):
        ws = [s for s in method_scored if s['window'] == w]
        wp = [s['joint_profit'] for s in ws if s['joint_profit'] is not None]
        wc = [s for s in ws if s['cond_hit'] is not None]
        by_w[w] = {
            'n': len(ws),
            'joint_roi': sum(wp)/(len(wp)*100) if wp else 0,
            'joint_clv': sum(s['joint_clv'] for s in ws)/len(ws) if ws else 0,
            'cond_clv': sum(s['cond_clv'] for s in wc if s['cond_clv'] is not None)/len(wc) if wc else 0,
        }
    return {'n': n, 'joint_hits': jh, 'joint_acc': jh/n, 'expected_acc': mean_cp,
            'joint_clv': mean_jclv, 'joint_roi': jroi,
            'cond_n': cn, 'cond_hits': ch, 'cond_acc': ch/cn if cn else 0,
            'cond_expected': mean_pcond, 'cond_clv': mean_cclv,
            'rank': by_w['rank'], 'test': by_w['test']}

# ═══════════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    print("=" * 90)
    print("25% LOOK — PRE-REGISTERED EFFICACY LOOK")
    print("No threshold, window, decile or divergence-rule changes after this run.")
    print("=" * 90)

    state = json.load(open(STATE_FILE))
    done_users = {u: v for u, v in state['users'].items() if v['status'] == 'done'}
    failed_users = {u: v for u, v in state['users'].items() if v['status'] == 'failed'}
    unavail_users = {u: v for u, v in state['users'].items() if v['status'] == 'unavailable'}

    event_bouts, all_bouts = load_bout_table()
    card_map = load_card_map()
    props = load_props()
    rev_overrides, tap_overrides = load_name_overrides()

    # Score all users
    user_ml_scored = {}; user_ml_st = {}
    user_meth_scored = {}; user_meth_st = {}
    total_unmatched = 0
    users_with_method = 0

    for username in sorted(done_users.keys()):
        safe = username.replace(' ', '_').replace('/', '_')
        path = os.path.join(PICKS_DIR, f'{safe}.csv')
        if not os.path.exists(path): continue
        scored, unmatched, total = score_user_ml(path, event_bouts)
        user_ml_scored[username] = scored
        st = user_ml_stats(scored)
        if st: user_ml_st[username] = st
        total_unmatched += unmatched

        # Method scoring
        ms = score_user_methods(scored, card_map, props, rev_overrides, tap_overrides)
        user_meth_scored[username] = ms
        mst = user_method_stats(ms)
        if mst: user_meth_st[username] = mst

        if any(s.get('picked_method', '').strip() for s in scored):
            users_with_method += 1

    author_ml_st = user_ml_st.pop(AUTHOR, None)
    author_meth_st = user_meth_st.pop(AUTHOR, None)
    author_ml_scored = user_ml_scored.pop(AUTHOR, [])

    panel = {u: s for u, s in user_ml_st.items()}
    panel_meth = {u: s for u, s in user_meth_st.items()}
    qualified = {u: s for u, s in panel.items() if s['n'] >= MIN_SCORED}

    t_score = time.time()

    # ═══════════════════════════════════════════════════════════════
    # SECTION 1
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("SECTION 1 — ROSTER AND DATA HEALTH")
    print("=" * 90)
    v1 = sum(1 for v in done_users.values() if 'scraper_version' not in v)
    v2 = sum(1 for v in done_users.values() if v.get('scraper_version') == 2)
    print(f"\nUsers done:        {len(done_users)} (v1={v1}, v2={v2})")
    print(f"Users unavailable: {len(unavail_users)}")
    print(f"Users failed:      {len(failed_users)}")
    print(f"Users with method: {users_with_method}")
    print(f"Qualified (>={MIN_SCORED} scored): {len(qualified)}")
    picks_counts = [s['n'] for s in panel.values()]
    if picks_counts:
        print(f"Picks per user:    min={min(picks_counts)}, median={median(picks_counts):.0f}, max={max(picks_counts)}")
    total_scored = sum(s['n'] for s in panel.values())
    print(f"Total scored (panel): {total_scored}")
    print(f"Unmatched picks:      {total_unmatched}")
    mr = total_scored / (total_scored + total_unmatched) if (total_scored + total_unmatched) else 0
    print(f"Match rate:           {mr:.1%}")
    manual_ct = sum(1 for sc in user_ml_scored.values() for s in sc if s.get('is_manual'))
    print(f"Manual-odds picks:    {manual_ct}")
    # Dup check
    dup = 0
    for sc in user_ml_scored.values():
        seen = set()
        for s in sc:
            k = (s['card_key'], s['bout'])
            if k in seen: dup += 1
            seen.add(k)
    print(f"Duplicates:           {dup} {'PASS' if dup == 0 else 'FAIL'}")

    # ═══════════════════════════════════════════════════════════════
    # SECTION 2
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("SECTION 2 — BASELINES (per window)")
    print("=" * 90)

    for wl in ('rank', 'test', 'all'):
        bouts = all_bouts if wl == 'all' else [b for b in all_bouts if b['window'] == wl]
        fav_p = dog_p = 0
        for b in bouts:
            pf = float(b['p_fair_picked']); bl = int(b['best_line']); res = b['result']
            dec = american_to_decimal(bl)
            if pf >= 0.5:
                fav_p += (dec-1)*100 if res=='win' else -100
                p_dog = 1-pf; dd = 1/p_dog if p_dog > 0 else 100
                dog_p += (dd-1)*100 if res=='loss' else -100
            else:
                dog_p += (dec-1)*100 if res=='win' else -100
                p_fav = 1-pf; df = 1/p_fav if p_fav > 0 else 100
                fav_p += (df-1)*100 if res=='loss' else -100
        nb = len(bouts)
        pclvs = [s[wl if wl != 'all' else 'clv'] if wl == 'all'
                 else s[wl]['clv'] for s in qualified.values()
                 if (wl == 'all' or s[wl]['n'] > 0)]
        # Fix: get CLV properly
        if wl == 'all':
            pclvs = [s['clv'] for s in qualified.values()]
            prois = [s['roi'] for s in qualified.values()]
        else:
            pclvs = [s[wl]['clv'] for s in qualified.values() if s[wl]['n'] > 0]
            prois = [s[wl]['roi'] for s in qualified.values() if s[wl]['n'] > 0]
        rp = sum(1 for r in prois if r > 0)
        print(f"\n  {wl.upper()} ({nb} bouts):")
        print(f"    Always-fav ROI:    {fav_p/(nb*100):+.1%}")
        print(f"    Always-dog ROI:    {dog_p/(nb*100):+.1%}")
        if pclvs:
            print(f"    Panel mean CLV:    {np.mean(pclvs):+.4f} (SD={np.std(pclvs):.4f})")
            print(f"    Panel mean ROI:    {np.mean(prois):+.1%}")
            print(f"    Users ROI > 0:     {rp}/{len(prois)} ({rp/len(prois):.1%})")

    # ═══════════════════════════════════════════════════════════════
    # SECTION 3
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("SECTION 3 — LEADERBOARDS (real usernames)")
    print("=" * 90)

    # Top 30 by ROI
    ranked_roi = sorted(qualified.items(), key=lambda x: x[1]['roi'], reverse=True)
    print(f"\nTOP 30 BY MONEYLINE ROI (n={len(qualified)}):")
    hdr = f"  {'User':<22} {'Picks':>5} {'Acc%':>5} {'Exp%':>5} {'CLV':>7} {'ROI':>7} {'rROI':>7} {'tROI':>7} {'Fav%':>5}"
    print(hdr); print("  " + "-" * (len(hdr)-2))
    for u, s in ranked_roi[:30]:
        rr = s['rank']['roi'] if s['rank']['n'] > 0 else 0
        tr = s['test']['roi'] if s['test']['n'] > 0 else 0
        print(f"  {u[:21]:<22} {s['n']:>5} {s['accuracy']:>5.1%} {s['expected_accuracy']:>5.1%} "
              f"{s['clv']:>+7.4f} {s['roi']:>+6.1%} {rr:>+6.1%} {tr:>+6.1%} {s['fav_share']:>4.0%}")

    # Top 30 by CLV
    ranked_clv = sorted(qualified.items(), key=lambda x: x[1]['clv'], reverse=True)
    print(f"\nTOP 30 BY MONEYLINE CLV:")
    print(hdr); print("  " + "-" * (len(hdr)-2))
    for u, s in ranked_clv[:30]:
        rr = s['rank']['roi'] if s['rank']['n'] > 0 else 0
        tr = s['test']['roi'] if s['test']['n'] > 0 else 0
        print(f"  {u[:21]:<22} {s['n']:>5} {s['accuracy']:>5.1%} {s['expected_accuracy']:>5.1%} "
              f"{s['clv']:>+7.4f} {s['roi']:>+6.1%} {rr:>+6.1%} {tr:>+6.1%} {s['fav_share']:>4.0%}")

    # Top 30 by method ROI
    qual_meth = {u: s for u, s in panel_meth.items() if s['n'] >= 100 and u in qualified}
    ranked_meth = sorted(qual_meth.items(), key=lambda x: x[1]['joint_roi'], reverse=True)
    print(f"\nTOP 30 BY METHOD ROI (joint, n={len(qual_meth)}):")
    mhdr = f"  {'User':<22} {'mPicks':>6} {'jAcc':>5} {'jExp':>5} {'jCLV':>7} {'jROI':>7} {'cAcc':>5} {'cExp':>5} {'cCLV':>7} {'rjROI':>7} {'tjROI':>7}"
    print(mhdr); print("  " + "-" * (len(mhdr)-2))
    for u, s in ranked_meth[:30]:
        rjr = s['rank']['joint_roi'] if s['rank']['n'] > 0 else 0
        tjr = s['test']['joint_roi'] if s['test']['n'] > 0 else 0
        print(f"  {u[:21]:<22} {s['n']:>6} {s['joint_acc']:>5.1%} {s['expected_acc']:>5.1%} "
              f"{s['joint_clv']:>+7.4f} {s['joint_roi']:>+6.1%} {s['cond_acc']:>5.1%} "
              f"{s['cond_expected']:>5.1%} {s['cond_clv']:>+7.4f} {rjr:>+6.1%} {tjr:>+6.1%}")

    # Overlap
    top30_roi_set = set(u for u, _ in ranked_roi[:30])
    top30_meth_set = set(u for u, _ in ranked_meth[:30])
    overlap = top30_roi_set & top30_meth_set
    print(f"\n  Overlap top-30 ML ROI & top-30 method ROI: {len(overlap)}")

    # Spearman ML CLV vs cond CLV
    both = [(panel[u]['clv'], panel_meth[u]['cond_clv'])
            for u in qualified if u in panel_meth and panel_meth[u]['cond_n'] > 0]
    if len(both) > 5:
        r_mc, _ = spearmanr([x[0] for x in both], [x[1] for x in both])
        print(f"  Spearman(ML CLV, cond method CLV): {r_mc:.3f} (n={len(both)})")

    # Distributions
    all_rois = [s['roi'] for s in qualified.values()]
    all_clvs = [s['clv'] for s in qualified.values()]
    all_jclvs = [s['joint_clv'] for s in qual_meth.values()]
    all_cclvs = [s['cond_clv'] for s in qual_meth.values() if s['cond_n'] > 0]
    pcts = [5, 25, 50, 75, 95]

    for label, data in [('ROI', all_rois), ('CLV', all_clvs),
                        ('Joint method CLV', all_jclvs), ('Cond method CLV', all_cclvs)]:
        if not data: continue
        vals = np.percentile(data, pcts)
        print(f"\n  {label} (n={len(data)}): mean={np.mean(data):+.4f}, SD={np.std(data):.4f}")
        print(f"    " + "  ".join(f"p{p}={v:+.4f}" for p, v in zip(pcts, vals)))

    # Author
    if author_ml_st:
        print(f"\n  AUTHOR ({AUTHOR}): picks={author_ml_st['n']}, acc={author_ml_st['accuracy']:.1%}, "
              f"CLV={author_ml_st['clv']:+.4f}, ROI={author_ml_st['roi']:+.1%}")
    if author_meth_st:
        print(f"    Method: n={author_meth_st['n']}, jAcc={author_meth_st['joint_acc']:.1%}, "
              f"jCLV={author_meth_st['joint_clv']:+.4f}, jROI={author_meth_st['joint_roi']:+.1%}, "
              f"cCLV={author_meth_st['cond_clv']:+.4f}")

    # ═══════════════════════════════════════════════════════════════
    # SECTION 4 — MONEYLINE BOOTSTRAP
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("SECTION 4 — PRE-REGISTERED STATISTICS (moneyline)")
    print("=" * 90)

    eligible = {u: s for u, s in qualified.items()
                if s['rank']['n'] >= 150 and s['test']['n'] >= 80}
    if len(eligible) < 20:
        eligible = {u: s for u, s in qualified.items()
                    if s['rank']['n'] >= 50 and s['test']['n'] >= 30}
        print(f"\n  WARNING: relaxed eligibility to 50/30")

    n_elig = len(eligible)
    print(f"\n  Eligible: {n_elig} users")
    d = max(1, n_elig // 10)
    print(f"  Decile size: {d}")
    print(f"  SE on rho for n={n_elig}: {1/np.sqrt(n_elig-3):.4f}")

    rank_clvs = np.array([s['rank']['clv'] for s in eligible.values()])
    test_clvs = np.array([s['test']['clv'] for s in eligible.values()])

    rho_obs, _ = spearmanr(rank_clvs, test_clvs)
    sorted_by_rank = np.argsort(rank_clvs)
    top_idx = sorted_by_rank[-d:]; bot_idx = sorted_by_rank[:d]
    tmb_obs = test_clvs[top_idx].mean() - test_clvs[bot_idx].mean()
    top_test_obs = test_clvs[top_idx].mean()

    # Divergence
    top_users_list = [list(eligible.keys())[i] for i in top_idx]
    bout_fairs = {}
    for b in all_bouts:
        if b['window'] != 'test': continue
        bk = (b['card_key'], b['bout'])
        parts = b['bout'].split(' vs ')
        if len(parts) != 2: continue
        p_ezo = float(b['p_fair_picked']); ezo_f = b['picked_fighter']
        p_a = p_ezo if names_match(normalize(ezo_f), normalize(parts[0])) else 1 - p_ezo
        bout_fairs[bk] = {'fighter_a': parts[0], 'fighter_b': parts[1],
                          'p_a': p_a, 'result': b['result'], 'ezo_picked': ezo_f,
                          'best_line': int(b['best_line']), 'p_fair_picked': p_ezo}

    def compute_divergence(user_list, scored_dict):
        test_bout_picks = defaultdict(lambda: {'total': 0, 'sides': defaultdict(int)})
        for u in user_list:
            for s in scored_dict.get(u, []):
                if s['window'] != 'test': continue
                bk = (s['card_key'], s['bout'])
                test_bout_picks[bk]['total'] += 1
                test_bout_picks[bk]['sides'][s['fighter_picked']] += 1
        dp = 0; db = 0
        for bk, info in test_bout_picks.items():
            if info['total'] == 0: continue
            bf = bout_fairs.get(bk)
            if not bf: continue
            for fighter, count in info['sides'].items():
                share = count / info['total']
                p_f = bf['p_a'] if names_match(normalize(fighter), normalize(bf['fighter_a'])) else 1 - bf['p_a']
                if share - p_f >= 0.10:
                    db += 1
                    if names_match(normalize(fighter), normalize(bf['ezo_picked'])):
                        bl = bf['best_line']; won = bf['result'] == 'win'
                    else:
                        po = 1 - bf['p_fair_picked']; dc = 1/po if po > 0 else 100
                        bl = round((dc-1)*100) if dc >= 2 else round(-100/(dc-1))
                        won = bf['result'] == 'loss'
                    dp += (american_to_decimal(bl)-1)*100 if won else -100
        return dp / (db * 100) if db > 0 else 0, db

    div_roi_obs, div_bets = compute_divergence(top_users_list, user_ml_scored)
    whole_div_roi, whole_div_bets = compute_divergence(list(eligible.keys()), user_ml_scored)

    # Always-fav test ROI
    test_bouts = [b for b in all_bouts if b['window'] == 'test']
    fav_p_test = 0
    for b in test_bouts:
        pf = float(b['p_fair_picked']); bl = int(b['best_line']); dec = american_to_decimal(bl)
        if pf >= 0.5:
            fav_p_test += (dec-1)*100 if b['result']=='win' else -100
        else:
            pfav = 1-pf; df = 1/pfav if pfav > 0 else 100
            fav_p_test += (df-1)*100 if b['result']=='loss' else -100
    fav_roi_test = fav_p_test / (len(test_bouts) * 100)

    # Bootstrap
    print(f"\n  Running {N_BOOT}-draw bootstrap (seed {SEED})...")
    rng = np.random.RandomState(SEED)

    bout_to_fidx = {}; fight_pfair_a = []
    for b in all_bouts:
        bk = (b['card_key'], b['bout'])
        if bk in bout_to_fidx: continue
        fidx = len(fight_pfair_a)
        parts = b['bout'].split(' vs ')
        if len(parts) != 2: continue
        p_ezo = float(b['p_fair_picked']); ezo_f = normalize(b['picked_fighter'])
        p_a = p_ezo if names_match(ezo_f, normalize(parts[0])) else 1 - p_ezo
        fight_pfair_a.append(p_a)
        bout_to_fidx[bk] = fidx
    fight_pfair_a = np.array(fight_pfair_a)
    n_fights = len(fight_pfair_a)

    user_picks_arr = {}
    for u in eligible:
        pd = []
        for s in user_ml_scored.get(u, []):
            bk = (s['card_key'], s['bout'])
            fidx = bout_to_fidx.get(bk)
            if fidx is None: continue
            parts = s['bout'].split(' vs ')
            if len(parts) != 2: continue
            picked_a = 1 if names_match(normalize(s['fighter_picked']), normalize(parts[0])) else 0
            pd.append((fidx, picked_a, s['p_fair'], s['window']))
        user_picks_arr[u] = pd

    null_rho = []; null_tmb = []; null_top = []
    for _ in range(N_BOOT):
        sim = rng.random(n_fights) < fight_pfair_a
        sr = []; st = []
        for u in eligible:
            rs = ts = 0; rn = tn = 0
            for fidx, pa, pf, w in user_picks_arr[u]:
                correct = (pa == 1 and sim[fidx]) or (pa == 0 and not sim[fidx])
                clv = (1 if correct else 0) - pf
                if w == 'rank': rs += clv; rn += 1
                elif w == 'test': ts += clv; tn += 1
            sr.append(rs/rn if rn else 0); st.append(ts/tn if tn else 0)
        sr = np.array(sr); st = np.array(st)
        if len(sr) > 2:
            r, _ = spearmanr(sr, st); null_rho.append(r)
        si = np.argsort(sr)
        null_tmb.append(st[si[-d:]].mean() - st[si[:d]].mean())
        null_top.append(st[si[-d:]].mean())

    null_rho = np.array(null_rho); null_tmb = np.array(null_tmb); null_top = np.array(null_top)

    def report(name, obs, null):
        nm = null.mean(); ns = null.std(); n95 = np.percentile(null, 95)
        pctile = (null < obs).mean() * 100
        ci_lo = np.percentile(null, 2.5); ci_hi = np.percentile(null, 97.5)
        print(f"  {name:<40} obs={obs:>+.4f}  null_m={nm:>+.4f}  SD={ns:.4f}  "
              f"95th={n95:>+.4f}  pctile={pctile:.1f}%  CI=[{ci_lo:+.4f},{ci_hi:+.4f}]")

    print()
    report("H1: rho(rank CLV, test CLV)", rho_obs, null_rho)
    report("H2: top-bot decile test CLV", tmb_obs, null_tmb)
    report("S2: top-decile test CLV", top_test_obs, null_top)
    print(f"  {'S1: divergence ROI (10pp, top decile)':<40} obs={div_roi_obs:>+.4f}  bets={div_bets}")
    print(f"  {'S1: divergence ROI (whole roster)':<40} obs={whole_div_roi:>+.4f}  bets={whole_div_bets}")
    print(f"  {'Always-fav test ROI':<40} obs={fav_roi_test:>+.4f}")

    # Interim rule
    ci_lo_rho = np.percentile(null_rho, 2.5)
    ci_hi_rho = np.percentile(null_rho, 97.5)
    # The CI here is on the null. The pre-reg says: if 95% CI for rho lies entirely below 0.10
    # This means the observed rho's CI. Approximate CI for observed rho:
    se_rho = 1 / np.sqrt(n_elig - 3)
    obs_ci_lo = rho_obs - 1.96 * se_rho
    obs_ci_hi = rho_obs + 1.96 * se_rho
    print(f"\n  Observed rho 95% CI: [{obs_ci_lo:+.4f}, {obs_ci_hi:+.4f}]")
    if obs_ci_hi < 0.10:
        print("\n  " + "!" * 60)
        print("  FUTILITY — 95% CI for rho lies entirely below 0.10")
        print("  " + "!" * 60)
    else:
        print("\n  " + "=" * 60)
        print("  CONTINUE — rho CI overlaps 0.10, no futility stop")
        print("  " + "=" * 60)

    # ═══════════════════════════════════════════════════════════════
    # SECTION 5 — METHOD PIPELINE (exploratory)
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("SECTION 5 — METHOD PIPELINE (exploratory)")
    print("=" * 90)

    meth_eligible = {u: s for u, s in qual_meth.items() if u in eligible}
    print(f"\n  Method-eligible users: {len(meth_eligible)}")

    if len(meth_eligible) >= 10:
        # Persistence
        me_rank_jclv = [s['rank']['joint_clv'] for s in meth_eligible.values() if s['rank']['n'] > 0]
        me_test_jclv = [s['test']['joint_clv'] for s in meth_eligible.values() if s['test']['n'] > 0]
        me_rank_cclv = [s['rank']['cond_clv'] for s in meth_eligible.values() if s['rank']['n'] > 0]
        me_test_cclv = [s['test']['cond_clv'] for s in meth_eligible.values() if s['test']['n'] > 0]

        if len(me_rank_jclv) == len(me_test_jclv) and len(me_rank_jclv) > 5:
            r_j, _ = spearmanr(me_rank_jclv, me_test_jclv)
            print(f"  rho(rank joint CLV, test joint CLV): {r_j:.3f}")
        if len(me_rank_cclv) == len(me_test_cclv) and len(me_rank_cclv) > 5:
            r_c, _ = spearmanr(me_rank_cclv, me_test_cclv)
            print(f"  rho(rank cond CLV, test cond CLV):   {r_c:.3f}")

        # Top decile by ML CLV: method performance
        ml_sorted = sorted(eligible.items(), key=lambda x: x[1]['rank']['clv'], reverse=True)
        ml_top_users = [u for u, _ in ml_sorted[:d]]
        ml_top_meth = [panel_meth[u] for u in ml_top_users if u in panel_meth]
        if ml_top_meth:
            tw = [s['test'] for s in ml_top_meth if s['test']['n'] > 0]
            if tw:
                avg_tjr = np.mean([s['joint_roi'] for s in tw])
                avg_tcc = np.mean([s['cond_clv'] for s in tw])
                print(f"  Top decile (by ML CLV): test joint ROI={avg_tjr:+.1%}, test cond CLV={avg_tcc:+.4f}")

        # Top decile by cond CLV
        cclv_sorted = sorted(meth_eligible.items(), key=lambda x: x[1]['rank']['cond_clv'], reverse=True)
        cclv_top = [u for u, _ in cclv_sorted[:max(1, len(meth_eligible)//10)]]
        cclv_top_test = [panel_meth[u]['test']['cond_clv'] for u in cclv_top if u in panel_meth and panel_meth[u]['test']['n'] > 0]
        if cclv_top_test:
            print(f"  Top decile (by cond CLV): test cond CLV={np.mean(cclv_top_test):+.4f}")
    else:
        print("  Too few method-eligible users for persistence tests")

    # ═══════════════════════════════════════════════════════════════
    # SECTION 6 — CONTROL
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("SECTION 6 — CONTROL VS MAIN")
    print("=" * 90)
    print("\n  All users are cohort=main. No control group in current roster.")

    # ═══════════════════════════════════════════════════════════════
    # SECTION 7 — RUNTIME
    # ═══════════════════════════════════════════════════════════════
    t_end = time.time()
    print("\n" + "=" * 90)
    print("SECTION 7 — RUNTIME")
    print("=" * 90)
    print(f"  Scoring:    {t_score - t0:.1f}s")
    print(f"  Bootstrap:  {t_end - t_score:.1f}s")
    print(f"  Total:      {t_end - t0:.1f}s")
    print(f"  Users:      {len(done_users)}")
    print(f"  Projection at 1,547: ~{(t_end - t0) * 1547 / len(done_users):.0f}s "
          f"({(t_end - t0) * 1547 / len(done_users) / 60:.1f} min)")


if __name__ == '__main__':
    main()
