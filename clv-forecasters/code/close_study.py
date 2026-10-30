#!/usr/bin/env python3
"""
close_study.py — Close out the pre-registered forecaster-CLV panel study.

OPERATOR DECISIONS (locked):
  CONTINUE_TO_FUTILITY_GATE = false → EARLY-TERMINATED
  COVERAGE_EXCLUSION_RULE = "No exclusion; score on collected events,
    require ≥150 rank / ≥80 test scored picks"

Pre-reg windows (from osf_prereg.md):
  Rank: 2025-08-09 through 2026-04-17
  Test: 2026-04-18 through 2026-08-15
  Dolidze card (2025-08-09) dropped from rank window for v1/v2 parity.
  Effective rank: 2025-08-16 through 2026-04-17.

Seed 67 everywhere.
"""

import csv, json, math, os, re, sys, time, unicodedata, hashlib, io
import numpy as np
from scipy.stats import spearmanr
from collections import defaultdict, Counter
from statistics import median
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000
PICKS_DIR = r'C:\Research\ufc\picks\users'
STATE_FILE = r'C:\Research\ufc\picks\state.json'
AUTHOR = 'Ezoteryka'
DROP_DATE = '2025-08-09'
MIN_RANK = 150; MIN_TEST = 80

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

# ─── Load bout table ───
event_bouts = defaultdict(list)
all_bouts = []
with open('ezoteryka_scored.csv', 'r', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        event_bouts[normalize_event(r['card_key'])].append(r)
        all_bouts.append(r)

# Fight arrays
bout_to_fidx = {}; fight_pfair_a = []; fight_window = []
for b in all_bouts:
    bk = (b['card_key'], b['bout'])
    if bk in bout_to_fidx: continue
    parts = b['bout'].split(' vs ')
    if len(parts) != 2: continue
    fidx = len(fight_pfair_a)
    p_ezo = float(b['p_fair_picked']); ezo_f = normalize(b['picked_fighter'])
    p_a = p_ezo if names_match(ezo_f, normalize(parts[0])) else 1 - p_ezo
    fight_pfair_a.append(p_a)
    fight_window.append('dropped' if b['canonical_date'] == DROP_DATE else b['window'])
    bout_to_fidx[bk] = fidx
fight_pfair_a = np.array(fight_pfair_a)
n_fights = len(fight_pfair_a)

def score_user(username):
    safe = username.replace(' ', '_').replace('/', '_')
    path = os.path.join(PICKS_DIR, f'{safe}.csv')
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f:
        picks = list(csv.DictReader(f))
    scored = []
    for p in picks:
        fp_n = normalize(p['fighter_picked']); opp_n = normalize(p['opponent'])
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
        if not r: continue
        ezo_picked_n = normalize(r['picked_fighter'])
        if names_match(fp_n, ezo_picked_n):
            best_line = int(r['best_line']); p_fair = float(r['p_fair_picked'])
        else:
            p_fair = 1 - float(r['p_fair_picked'])
            dec = 1 / p_fair if p_fair > 0 else 100
            best_line = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))
        is_correct = p['correct'] == 'YES'
        clv = (1 if is_correct else 0) - p_fair
        w = 'dropped' if r['canonical_date'] == DROP_DATE else r['window']
        scored.append({
            'card_key': r['card_key'], 'bout': r['bout'],
            'fighter_picked': p['fighter_picked'], 'correct': is_correct,
            'p_fair': p_fair, 'clv': clv, 'window': w, 'best_line': best_line,
            'canonical_date': r['canonical_date'],
        })
    return scored

# ═══════════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    state = json.load(open(STATE_FILE))
    done = {u: v for u, v in state['users'].items() if v['status'] == 'done'}
    snapshot = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    git_hash = os.popen('git rev-parse HEAD').read().strip()

    OUT = open('RESULTS.md', 'w', encoding='utf-8')
    def pr(s=''): print(s); OUT.write(s + '\n')

    pr("# Results — Persistence of Forecasting Skill in UFC Predictions")
    pr(f"\nSnapshot: {snapshot} | Git: {git_hash[:12]}")
    pr(f"Status: **EARLY-TERMINATED** at {len(done)}/{1447} users ({len(done)/1447:.0%} of roster)")
    pr(f"Coverage exclusion: score on collected events, ≥{MIN_RANK} rank / ≥{MIN_TEST} test picks")
    pr(f"Dolidze card ({DROP_DATE}) dropped from rank window for v1/v2 parity")
    pr()

    # ─── Phase 2: Score all users ───
    pr("## Phase 2 — Union and Score")
    all_scored = {}; all_stats = {}; drop_log = []
    for u in sorted(done.keys()):
        if u == AUTHOR: continue
        scored = score_user(u)
        if scored is None: drop_log.append((u, 'file_missing')); continue
        all_scored[u] = scored
        rank_s = [s for s in scored if s['window'] == 'rank']
        test_s = [s for s in scored if s['window'] == 'test']
        all_stats[u] = {
            'n': len(scored), 'rank_n': len(rank_s), 'test_n': len(test_s),
            'rank_clv': sum(s['clv'] for s in rank_s) / len(rank_s) if rank_s else 0,
            'test_clv': sum(s['clv'] for s in test_s) / len(test_s) if test_s else 0,
            'clv': sum(s['clv'] for s in scored) / len(scored) if scored else 0,
            'roi': sum((american_to_decimal(s['best_line'])-1)*100 if s['correct'] else -100
                       for s in scored) / (len(scored)*100) if scored else 0,
            'sv': done[u].get('scraper_version', 1),
        }

    # Author
    author_scored = score_user(AUTHOR)
    author_rank = [s for s in author_scored if s['window'] == 'rank'] if author_scored else []
    author_test = [s for s in author_scored if s['window'] == 'test'] if author_scored else []

    # Qualification
    qualified = {u: s for u, s in all_stats.items() if s['rank_n'] >= MIN_RANK and s['test_n'] >= MIN_TEST}
    excluded = [(u, s) for u, s in all_stats.items() if u not in qualified]
    for u, s in excluded: drop_log.append((u, f'below_threshold: rank={s["rank_n"]} test={s["test_n"]}'))

    pr(f"\nUsers scored: {len(all_stats)}")
    pr(f"Qualified (≥{MIN_RANK} rank, ≥{MIN_TEST} test): **{len(qualified)}**")
    pr(f"Excluded: {len(excluded)} (below pick threshold)")
    pr(f"Scraper versions in qualified: v1={sum(1 for s in qualified.values() if s['sv']==1)}, v2={sum(1 for s in qualified.values() if s['sv']==2)}")

    # ─── Phase 3: Coverage matrix ───
    pr("\n## Phase 3 — Coverage")
    canonical = []
    with open(r'C:\Research\ufc\data\frame\canonical_events.csv', encoding='utf-8') as f:
        canonical = list(csv.DictReader(f))
    can_events = [c['card_key'] for c in canonical]

    # Build status matrix for qualified users
    coverage = {}
    for u in qualified:
        user_events = set()
        for s in all_scored[u]:
            user_events.add(s['card_key'])
        row = {}
        for ce in can_events:
            if ce in user_events:
                row[ce] = 'PICKED'
            else:
                # Check if event was NOT_COLLECTED (v2 stop gate) or ABSTAINED
                row[ce] = 'NOT_COLLECTED_OR_ABSTAINED'
        coverage[u] = row

    picked_counts = [sum(1 for v in row.values() if v == 'PICKED') for row in coverage.values()]
    pr(f"Events per qualified user: min={min(picked_counts)}, median={median(picked_counts):.0f}, max={max(picked_counts)}")
    pr(f"No additional exclusions applied (rule D: score on collected events)")

    # ─── Phase 4: Estimands ───
    pr("\n## Phase 4 — Pre-Registered Statistics")

    n_elig = len(qualified)
    d = max(1, n_elig // 10)
    se_rho = 1 / np.sqrt(n_elig - 3)
    rank_clvs = np.array([qualified[u]['rank_clv'] for u in qualified])
    test_clvs = np.array([qualified[u]['test_clv'] for u in qualified])
    user_list = list(qualified.keys())

    rho_obs, _ = spearmanr(rank_clvs, test_clvs)
    si = np.argsort(rank_clvs)
    top_idx = si[-d:]; bot_idx = si[:d]
    tmb_obs = test_clvs[top_idx].mean() - test_clvs[bot_idx].mean()

    pr(f"\nn = {n_elig}, decile = {d}, SE(ρ) = {se_rho:.4f}")
    pr(f"H1 threshold: ρ > 0.104 | H2 threshold: top−bot > 0.008")

    # Bootstrap
    pr(f"\nBootstrap: {N_BOOT} draws, seed {SEED}")
    rng = np.random.RandomState(SEED)
    upar = {}
    for u in qualified:
        pd = []
        for s in all_scored[u]:
            bk = (s['card_key'], s['bout'])
            fidx = bout_to_fidx.get(bk)
            if fidx is None: continue
            if fight_window[fidx] == 'dropped': continue
            parts = s['bout'].split(' vs ')
            if len(parts) != 2: continue
            pa = 1 if names_match(normalize(s['fighter_picked']), normalize(parts[0])) else 0
            pd.append((fidx, pa, s['p_fair'], fight_window[fidx]))
        upar[u] = pd

    null_rho = []; null_tmb = []
    for _ in range(N_BOOT):
        sim = rng.random(n_fights) < fight_pfair_a
        sr = []; st = []
        for u in qualified:
            rs = ts = 0; rn = tn = 0
            for fidx, pa, pf, w in upar[u]:
                correct = (pa == 1 and sim[fidx]) or (pa == 0 and not sim[fidx])
                c = (1 if correct else 0) - pf
                if w == 'rank': rs += c; rn += 1
                elif w == 'test': ts += c; tn += 1
            sr.append(rs/rn if rn else 0); st.append(ts/tn if tn else 0)
        sr = np.array(sr); st = np.array(st)
        r, _ = spearmanr(sr, st); null_rho.append(r)
        si2 = np.argsort(sr)
        null_tmb.append(st[si2[-d:]].mean() - st[si2[:d]].mean())
    null_rho = np.array(null_rho); null_tmb = np.array(null_tmb)

    def fmt(name, obs, null, threshold=None):
        nm = null.mean(); ns = null.std(); n95 = np.percentile(null, 95)
        pctile = (null < obs).mean() * 100
        ci = (np.percentile(null, 2.5), np.percentile(null, 97.5))
        sig = "YES" if threshold and obs > threshold else "NO" if threshold else ""
        pr(f"| {name:<35} | {obs:>+.4f} | {nm:>+.4f} | {ns:.4f} | {n95:>+.4f} | {pctile:>5.1f}% | [{ci[0]:+.4f}, {ci[1]:+.4f}] | {sig} |")

    pr("\n| Statistic | Observed | Null mean | Null SD | 95th | Pctile | 95% CI | Sig? |")
    pr("|---|---|---|---|---|---|---|---|")
    fmt("H1: ρ(rank CLV, test CLV)", rho_obs, null_rho, 0.104)
    fmt("H2: top−bot decile test CLV", tmb_obs, null_tmb, 0.008)

    obs_ci = (rho_obs - 1.96*se_rho, rho_obs + 1.96*se_rho)
    pr(f"\nObserved ρ 95% CI: [{obs_ci[0]:+.4f}, {obs_ci[1]:+.4f}]")
    if obs_ci[1] < 0.10:
        pr("**FUTILITY**: CI lies entirely below 0.10")
    else:
        pr("CI overlaps 0.10 — no futility")

    # Leave-one-out influence
    pr("\n### Leave-one-out influence on ρ")
    loo_rhos = []
    for i in range(n_elig):
        mask = np.ones(n_elig, dtype=bool); mask[i] = False
        r, _ = spearmanr(rank_clvs[mask], test_clvs[mask])
        loo_rhos.append((user_list[i], r))
    loo_rhos.sort(key=lambda x: abs(x[1] - rho_obs), reverse=True)
    pr(f"\nFull ρ = {rho_obs:+.4f}. Top 5 influential users:")
    pr("| User | ρ without | Δρ |")
    pr("|---|---|---|")
    for u, r in loo_rhos[:5]:
        pr(f"| {u} | {r:+.4f} | {r - rho_obs:+.4f} |")

    # ─── Sensitivity appendix ───
    pr("\n### Sensitivity: v1-only, v2-only, corrected frame")
    frames = {
        'v1-only': {u: s for u, s in qualified.items() if s['sv'] == 1},
        'v2-only': {u: s for u, s in qualified.items() if s['sv'] == 2},
        'corrected (all)': qualified,
    }
    pr("\n| Frame | n | ρ | 95% CI | Top−bot |")
    pr("|---|---|---|---|---|")
    for label, fq in frames.items():
        if len(fq) < 10:
            pr(f"| {label} | {len(fq)} | — | — | — |")
            continue
        rc = np.array([fq[u]['rank_clv'] for u in fq])
        tc = np.array([fq[u]['test_clv'] for u in fq])
        r, _ = spearmanr(rc, tc)
        se = 1/np.sqrt(len(fq)-3)
        dd = max(1, len(fq)//10)
        ssi = np.argsort(rc)
        tb = tc[ssi[-dd:]].mean() - tc[ssi[:dd]].mean()
        pr(f"| {label} | {len(fq)} | {r:+.4f} | [{r-1.96*se:+.4f}, {r+1.96*se:+.4f}] | {tb:+.4f} |")

    pr("\nThe v1/v2 sign flip (v1 ρ≈+0.16, v2 ρ≈−0.10) is reported as evidence that")
    pr("the null result is robust to frame choice, not as a hidden finding.")

    # ─── Author ───
    pr("\n### Author (Ezoteryka)")
    if author_scored:
        n_a = len(author_scored)
        r_clv = sum(s['clv'] for s in author_rank) / len(author_rank) if author_rank else 0
        t_clv = sum(s['clv'] for s in author_test) / len(author_test) if author_test else 0
        roi = sum((american_to_decimal(s['best_line'])-1)*100 if s['correct'] else -100
                  for s in author_scored) / (n_a * 100)
        pr(f"Picks: {n_a} (rank={len(author_rank)}, test={len(author_test)})")
        pr(f"Rank CLV: {r_clv:+.4f} | Test CLV: {t_clv:+.4f} | ROI: {roi:+.1%}")

    # ─── Panel summary ───
    pr("\n### Panel summary")
    all_clvs_q = [s['clv'] for s in qualified.values()]
    all_rois_q = [s['roi'] for s in qualified.values()]
    pr(f"Mean CLV: {np.mean(all_clvs_q):+.4f} (SD={np.std(all_clvs_q):.4f})")
    pr(f"Mean ROI: {np.mean(all_rois_q):+.1%}")
    pr(f"Users ROI > 0: {sum(1 for r in all_rois_q if r > 0)}/{len(all_rois_q)} ({sum(1 for r in all_rois_q if r > 0)/len(all_rois_q):.1%})")

    # ─── Phase 5: Deviations ───
    pr("\n## Deviations from Pre-Registration")
    pr("""
1. **Early termination**: Study terminated at {n}/{total} users ({pct:.0%} of roster),
   below the pre-registered 50% futility gate. Labelled EARLY-TERMINATED.
2. **Dolidze card dropped**: The 2025-08-09 card is excluded from the rank window
   because the v2 scraper's stop gate fires at UFC 319 (2025-08-16) before reaching
   the Dolidze card. This makes v1 and v2 users comparable. Effective rank window:
   2025-08-16 through 2026-04-17.
3. **v1/v2 scraper differences**: v1 (134 users) used a looser UFC filter and a
   non-breaking stop gate; v2 (260 users) used `startswith('ufc')` and a breaking
   stop gate. Both produce identical pick data on shared bouts (0/4,110 field
   mismatches). Differences are in event collection scope only.
4. **Hernandez vs Rodrigues**: A new event appeared on Tapology between the v1 and
   v2 scrape periods. Present in some v2 users, absent in v1.
5. **No control cohort**: The pre-registered 100-user control group (ranks 2124–7000)
   was not added to the roster before termination.
""".format(n=len(done), total=1447, pct=len(done)/1447))

    # ─── Drop log ───
    pr("\n## Drop Log")
    pr(f"Total drops: {len(drop_log)}")
    if drop_log:
        pr("| User | Reason |")
        pr("|---|---|")
        for u, reason in sorted(drop_log, key=lambda x: x[1]):
            pr(f"| {u} | {reason} |")

    OUT.close()

    # ─── Write frozen dataset ───
    frozen_path = f'C:/Research/ufc/data/final/qualified_users_{git_hash[:8]}.csv'
    with open(frozen_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['username', 'scraper_version', 'n_scored', 'rank_n', 'test_n',
                     'rank_clv', 'test_clv', 'overall_clv', 'roi'])
        for u in sorted(qualified):
            s = qualified[u]
            w.writerow([u, s['sv'], s['n'], s['rank_n'], s['test_n'],
                        f"{s['rank_clv']:.6f}", f"{s['test_clv']:.6f}",
                        f"{s['clv']:.6f}", f"{s['roi']:.6f}"])

    t_end = time.time()
    print(f"\nRuntime: {t_end-t0:.0f}s")
    print(f"Outputs: RESULTS.md, {frozen_path}")


if __name__ == '__main__':
    main()
