#!/usr/bin/env python3
"""
reconcile_25pct.py — Reconciled 25% look after dropping Dolidze card.
Seed 67. Drop 2025-08-09 from rank window to make v1/v2 comparable.
"""
import csv, json, math, os, re, sys, time, unicodedata, io
import numpy as np
from scipy.stats import spearmanr
from collections import defaultdict, Counter
from statistics import median

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67; N_BOOT = 5000; N_SIM = 500
PICKS_DIR = r'C:\Research\ufc\picks\users'
STATE_FILE = r'C:\Research\ufc\picks\state.json'
AUTHOR = 'Ezoteryka'
DROP_DATE = '2025-08-09'  # Dolidze card, excluded from rank window

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

# Fight arrays for bootstrap
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
    # Adjusted window: drop Dolidze card from rank
    if b['canonical_date'] == DROP_DATE:
        fight_window.append('dropped')
    else:
        fight_window.append(b['window'])
    bout_to_fidx[bk] = fidx
fight_pfair_a = np.array(fight_pfair_a)
n_fights = len(fight_pfair_a)

# ─── Score user ───
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
        # Adjusted window
        w = r['window']
        if r['canonical_date'] == DROP_DATE:
            w = 'dropped'
        scored.append({
            'card_key': r['card_key'], 'bout': r['bout'],
            'fighter_picked': p['fighter_picked'], 'correct': is_correct,
            'p_fair': p_fair, 'clv': clv, 'window': w, 'best_line': best_line,
            'canonical_date': r['canonical_date'],
        })
    return scored

def user_window_stats(scored):
    by_w = {}
    for w in ('rank', 'test'):
        ws = [s for s in scored if s['window'] == w]
        n = len(ws)
        if n > 0:
            by_w[w] = {'n': n, 'clv': sum(s['clv'] for s in ws) / n,
                       'roi': sum((american_to_decimal(s['best_line'])-1)*100 if s['correct'] else -100 for s in ws) / (n*100)}
        else:
            by_w[w] = {'n': 0, 'clv': 0, 'roi': 0}
    return by_w

# ═══════════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    print("=" * 90)
    print("RECONCILED 25% LOOK — Dolidze card (2025-08-09) dropped from rank window")
    print("Rank window: 2025-08-16 → 2026-04-17 | Test: 2026-04-18 → 2026-08-15")
    print("=" * 90)

    state = json.load(open(STATE_FILE))
    done = {u: v for u, v in state['users'].items() if v['status'] == 'done'}

    # Load roster for position/cohort
    with open(r'C:\Research\ufc\picks\scrape_order.csv', encoding='utf-8') as f:
        lines = [l for l in f if not l.startswith('#')]
    roster = {}
    for row in csv.DictReader(io.StringIO(''.join(lines))):
        roster[row['username']] = {'pos': int(row['position']), 'cohort': row['cohort']}

    # Score all users
    all_scored = {}; all_stats = {}
    for u in done:
        if u == AUTHOR: continue
        scored = score_user(u)
        if scored is None or len(scored) < 50: continue
        all_scored[u] = scored
        all_stats[u] = user_window_stats(scored)
        sv = done[u].get('scraper_version', 1)
        all_stats[u]['sv'] = sv
        all_stats[u]['total'] = len(scored)

    # Author
    author_scored = score_user(AUTHOR)
    author_stats = user_window_stats(author_scored) if author_scored else None

    # ═══════════════════════════════════════════════════════════════
    # 1. PICKS BEFORE/AFTER DROPPING DOLIDZE
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("1. PICKS BEFORE/AFTER DROPPING DOLIDZE CARD")
    print("=" * 90)

    # Before = original rank window (includes Dolidze)
    v1_before = []; v2_before = []; v1_after = []; v2_after = []
    for u, st in all_stats.items():
        scored = all_scored[u]
        rank_before = sum(1 for s in scored if s['window'] in ('rank', 'dropped'))
        rank_after = st['rank']['n']
        if st['sv'] == 1:
            v1_before.append(rank_before); v1_after.append(rank_after)
        else:
            v2_before.append(rank_before); v2_after.append(rank_after)

    print(f"\n  v1 rank picks BEFORE drop: min={min(v1_before)}, med={median(v1_before):.0f}, max={max(v1_before)} (n={len(v1_before)})")
    print(f"  v1 rank picks AFTER drop:  min={min(v1_after)}, med={median(v1_after):.0f}, max={max(v1_after)}")
    print(f"  v2 rank picks BEFORE drop: min={min(v2_before)}, med={median(v2_before):.0f}, max={max(v2_before)} (n={len(v2_before)})")
    print(f"  v2 rank picks AFTER drop:  min={min(v2_after)}, med={median(v2_after):.0f}, max={max(v2_after)}")
    print(f"  Dolidze card had 12 bouts → v1 users lose ~12 rank picks; v2 users unchanged")

    # ═══════════════════════════════════════════════════════════════
    # 2. QUALIFICATION
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("2. QUALIFICATION (>=150 rank, >=80 test)")
    print("=" * 90)

    qualified = {}; excluded = []
    for u, st in all_stats.items():
        rn = st['rank']['n']; tn = st['test']['n']
        if rn >= 150 and tn >= 80:
            qualified[u] = st
        else:
            excluded.append((u, st['sv'], rn, tn, st['total']))

    print(f"\n  Qualified: {len(qualified)}")
    print(f"  Excluded:  {len(excluded)}")
    q_v1 = sum(1 for s in qualified.values() if s['sv'] == 1)
    q_v2 = sum(1 for s in qualified.values() if s['sv'] == 2)
    print(f"  Qualified v1/v2: {q_v1} / {q_v2}")

    if excluded:
        print(f"\n  Excluded users (showing first 20):")
        print(f"  {'User':<25} {'sv':>3} {'rank':>5} {'test':>5} {'total':>6}")
        for u, sv, rn, tn, tot in sorted(excluded, key=lambda x: x[2])[:20]:
            print(f"  {u[:24]:<25} {sv:>3} {rn:>5} {tn:>5} {tot:>6}")

    # ═══════════════════════════════════════════════════════════════
    # 3. H1, H2, S2, S1 — ALL, V1, V2
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("3. PRE-REGISTERED STATISTICS — ALL / V1 / V2")
    print("=" * 90)

    def run_stats(label, user_set):
        n_elig = len(user_set)
        if n_elig < 10:
            print(f"\n  {label}: n={n_elig}, too few"); return None
        d = max(1, n_elig // 10)
        rank_clvs = np.array([user_set[u]['rank']['clv'] for u in user_set])
        test_clvs = np.array([user_set[u]['test']['clv'] for u in user_set])
        rho_obs, _ = spearmanr(rank_clvs, test_clvs)
        se_rho = 1 / np.sqrt(n_elig - 3)

        si = np.argsort(rank_clvs)
        top_idx = si[-d:]; bot_idx = si[:d]
        tmb_obs = test_clvs[top_idx].mean() - test_clvs[bot_idx].mean()
        top_test_obs = test_clvs[top_idx].mean()

        # Always-fav test ROI
        test_bouts_set = [b for b in all_bouts if b['window'] == 'test']
        fav_test = 0
        for b in test_bouts_set:
            pf = float(b['p_fair_picked']); bl = int(b['best_line']); dec = american_to_decimal(bl)
            if pf >= 0.5: fav_test += (dec-1)*100 if b['result']=='win' else -100
            else:
                pfav = 1-pf; df = 1/pfav if pfav > 0 else 100
                fav_test += (df-1)*100 if b['result']=='loss' else -100
        fav_roi = fav_test / (len(test_bouts_set)*100)

        # Divergence
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

        def divergence_roi(users):
            tbp = defaultdict(lambda: {'total': 0, 'sides': defaultdict(int)})
            for u in users:
                for s in all_scored.get(u, []):
                    if s['window'] != 'test': continue
                    bk = (s['card_key'], s['bout'])
                    tbp[bk]['total'] += 1; tbp[bk]['sides'][s['fighter_picked']] += 1
            dp = 0; db = 0
            for bk, info in tbp.items():
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
            return dp/(db*100) if db else 0, db

        top_users = [list(user_set.keys())[i] for i in top_idx]
        div_roi, div_bets = divergence_roi(top_users)
        whole_div, whole_bets = divergence_roi(list(user_set.keys()))

        # CLV variance ratio
        clv_var_obs = np.var(test_clvs)

        # Bootstrap
        rng = np.random.RandomState(SEED)
        upar = {}
        for u in user_set:
            pd = []
            for s in all_scored.get(u, []):
                bk = (s['card_key'], s['bout'])
                fidx = bout_to_fidx.get(bk)
                if fidx is None: continue
                if fight_window[fidx] == 'dropped': continue
                parts = s['bout'].split(' vs ')
                if len(parts) != 2: continue
                pa = 1 if names_match(normalize(s['fighter_picked']), normalize(parts[0])) else 0
                pd.append((fidx, pa, s['p_fair'], fight_window[fidx]))
            upar[u] = pd

        null_rho = []; null_tmb = []; null_top = []; null_var = []
        for _ in range(N_BOOT):
            sim = rng.random(n_fights) < fight_pfair_a
            sr = []; st = []
            for u in user_set:
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
            null_top.append(st[si2[-d:]].mean())
            null_var.append(np.var(st))

        null_rho = np.array(null_rho); null_tmb = np.array(null_tmb)
        null_top = np.array(null_top); null_var = np.array(null_var)

        def rpt(name, obs, null):
            nm = null.mean(); ns = null.std(); n95 = np.percentile(null, 95)
            pctile = (null < obs).mean() * 100
            ci = (np.percentile(null, 2.5), np.percentile(null, 97.5))
            print(f"    {name:<40} obs={obs:>+.4f} null_m={nm:>+.4f} SD={ns:.4f} "
                  f"95th={n95:>+.4f} pctl={pctile:>5.1f}% CI=[{ci[0]:+.4f},{ci[1]:+.4f}]")

        print(f"\n  {label} (n={n_elig}, decile={d}, SE_rho={se_rho:.4f}):")
        rpt("H1: rho(rank CLV, test CLV)", rho_obs, null_rho)
        rpt("H2: top-bot decile test CLV", tmb_obs, null_tmb)
        rpt("S2: top-decile test CLV", top_test_obs, null_top)
        print(f"    {'S1: divergence (top decile)':<40} obs={div_roi:>+.4f} bets={div_bets}")
        print(f"    {'S1: divergence (whole roster)':<40} obs={whole_div:>+.4f} bets={whole_bets}")
        print(f"    {'Always-fav test ROI':<40} obs={fav_roi:>+.4f}")
        rpt("CLV variance ratio", clv_var_obs, null_var)

        # Interim rule
        obs_ci_lo = rho_obs - 1.96 * se_rho
        obs_ci_hi = rho_obs + 1.96 * se_rho
        print(f"    Observed rho 95% CI: [{obs_ci_lo:+.4f}, {obs_ci_hi:+.4f}]")
        if obs_ci_hi < 0.10:
            print(f"    >>> FUTILITY <<<")
        else:
            print(f"    >>> CONTINUE <<<")

        return {'rho': rho_obs, 'se_rho': se_rho, 'n': n_elig,
                'rank_clvs': rank_clvs, 'test_clvs': test_clvs}

    # ALL qualified
    result_all = run_stats("ALL QUALIFIED", qualified)

    # V1 only
    q_v1_set = {u: s for u, s in qualified.items() if s['sv'] == 1}
    result_v1 = run_stats("V1 ONLY", q_v1_set)

    # V2 only
    q_v2_set = {u: s for u, s in qualified.items() if s['sv'] == 2}
    result_v2 = run_stats("V2 ONLY", q_v2_set)

    # ═══════════════════════════════════════════════════════════════
    # 4. THORNDIKE CORRECTION
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("4. RANGE-RESTRICTION CORRECTION (Thorndike Case II)")
    print("=" * 90)

    if result_all:
        rho_raw = result_all['rho']
        # Selection ratio: roster ~ 2124 eligible from ~3700 total
        # (Platinum+ from full leaderboard)
        u_ratio = 2124 / 3700  # approximate
        # Thorndike Case II: rho_c = rho_r / sqrt(u^2 + rho_r^2 * (1 - u^2))
        # where u = SD_restricted / SD_unrestricted ≈ selection ratio proxy
        # More precisely: u = sqrt(1 - selection_ratio) is NOT right.
        # For Case II direct range restriction on X:
        # rho_c = rho_r / sqrt(rho_r^2 + U^2 * (1 - rho_r^2))
        # where U = SD_unrestricted / SD_restricted
        # Approximate U from selection ratio (top 57%):
        # For normal, truncating at top 57% → U ≈ 1/0.87 ≈ 1.15
        from scipy.stats import norm
        z_cut = norm.ppf(1 - u_ratio)  # cutoff for keeping top u_ratio
        # SD of truncated normal (keeping above z_cut):
        pdf_cut = norm.pdf(z_cut)
        sd_trunc = np.sqrt(1 - z_cut * pdf_cut / (1 - norm.cdf(z_cut)) -
                           (pdf_cut / (1 - norm.cdf(z_cut)))**2)
        U = 1 / sd_trunc  # unrestricted/restricted SD ratio

        if abs(rho_raw) < 1:
            rho_corrected = rho_raw / np.sqrt(rho_raw**2 + U**2 * (1 - rho_raw**2))
        else:
            rho_corrected = rho_raw

        se_corrected = result_all['se_rho'] * U  # approximate
        ci_lo_c = rho_corrected - 1.96 * se_corrected
        ci_hi_c = rho_corrected + 1.96 * se_corrected

        print(f"\n  Selection ratio: {u_ratio:.2f} (≈{2124} from ≈{3700})")
        print(f"  U (SD ratio):    {U:.3f}")
        print(f"  Raw rho:         {rho_raw:+.4f}")
        print(f"  Corrected rho:   {rho_corrected:+.4f}")
        print(f"  Corrected CI:    [{ci_lo_c:+.4f}, {ci_hi_c:+.4f}]")

    # ═══════════════════════════════════════════════════════════════
    # 5. SIMULATION WITH SELECTION
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("5. SIMULATION WITH SELECTION STEP")
    print("=" * 90)

    n_users_sim = len(qualified)
    # Use actual fight structure
    rank_fights = [i for i in range(n_fights) if fight_window[i] == 'rank']
    test_fights = [i for i in range(n_fights) if fight_window[i] == 'test']
    n_rf = len(rank_fights); n_tf = len(test_fights)
    # Last 10 test cards for selection
    test_dates = set()
    for b in all_bouts:
        if b['window'] == 'test':
            test_dates.add(b['canonical_date'])
    last_10_dates = sorted(test_dates)[-10:]

    last_10_fights = [i for i in range(n_fights)
                      if fight_window[i] == 'test' and
                      any(b['canonical_date'] in last_10_dates
                          for b in all_bouts if bout_to_fidx.get((b['card_key'], b['bout'])) == i)]

    rng_sim = np.random.RandomState(SEED)
    selection_ratio = u_ratio

    for sigma_s in [0, 0.01, 0.02, 0.03]:
        rhos_sel = []; rhos_unsel = []
        for _ in range(N_SIM):
            # Generate user skills
            skills = rng_sim.normal(0, sigma_s, n_users_sim)
            # Base accuracy ~ 0.65
            base_acc = 0.65

            # Simulate outcomes
            outcomes = rng_sim.random(n_fights) < fight_pfair_a

            # Each user picks: correct w.p. base_acc + skill
            user_rank_clv = np.zeros(n_users_sim)
            user_test_clv = np.zeros(n_users_sim)
            user_sel_acc = np.zeros(n_users_sim)

            for ui in range(n_users_sim):
                p_correct = np.clip(base_acc + skills[ui], 0.01, 0.99)
                picks_correct = rng_sim.random(n_fights) < p_correct

                # Rank CLV
                r_clvs = []
                for fi in rank_fights:
                    pf = fight_pfair_a[fi]
                    # User picks the side with prob p_correct of being right
                    if picks_correct[fi]:
                        clv = 1 - pf  # picked right side
                    else:
                        clv = 0 - pf  # picked wrong side
                    r_clvs.append(clv)
                user_rank_clv[ui] = np.mean(r_clvs) if r_clvs else 0

                # Test CLV
                t_clvs = []
                for fi in test_fights:
                    pf = fight_pfair_a[fi]
                    if picks_correct[fi]:
                        clv = 1 - pf
                    else:
                        clv = 0 - pf
                    t_clvs.append(clv)
                user_test_clv[ui] = np.mean(t_clvs) if t_clvs else 0

                # Selection: accuracy on last 10 cards
                sel_correct = sum(1 for fi in last_10_fights if picks_correct[fi])
                user_sel_acc[ui] = sel_correct / len(last_10_fights) if last_10_fights else 0

            # Unselected rho
            if n_users_sim > 3:
                r_unsel, _ = spearmanr(user_rank_clv, user_test_clv)
                rhos_unsel.append(r_unsel)

            # Selected: keep top selection_ratio by last-10 accuracy
            cutoff = np.percentile(user_sel_acc, (1 - selection_ratio) * 100)
            keep = user_sel_acc >= cutoff
            if keep.sum() > 3:
                r_sel, _ = spearmanr(user_rank_clv[keep], user_test_clv[keep])
                rhos_sel.append(r_sel)

        rhos_sel = np.array(rhos_sel); rhos_unsel = np.array(rhos_unsel)
        print(f"\n  sigma_s={sigma_s:.2f}: unsel_rho={rhos_unsel.mean():+.3f} (SD={rhos_unsel.std():.3f}), "
              f"sel_rho={rhos_sel.mean():+.3f} (SD={rhos_sel.std():.3f}), "
              f"attenuation={rhos_unsel.mean() - rhos_sel.mean():+.3f}")
        if sigma_s == 0:
            null_95_sel = np.percentile(rhos_sel, 95)
            print(f"    null 95th (selected): {null_95_sel:+.3f}")

    # ═══════════════════════════════════════════════════════════════
    # 6. CONTROL COHORT
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("6. CONTROL COHORT")
    print("=" * 90)
    print("\n  No control cohort in current roster (all cohort=main).")
    print("  Control group (ranks 2124-7000) not yet added to scrape_order.csv.")

    # ═══════════════════════════════════════════════════════════════
    # 7. AUTHOR + RUNTIME
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("7. AUTHOR + RUNTIME")
    print("=" * 90)

    if author_stats:
        print(f"\n  AUTHOR ({AUTHOR}):")
        print(f"    Total scored: {len(author_scored)}")
        print(f"    Rank: n={author_stats['rank']['n']}, CLV={author_stats['rank']['clv']:+.4f}, ROI={author_stats['rank']['roi']:+.1%}")
        print(f"    Test: n={author_stats['test']['n']}, CLV={author_stats['test']['clv']:+.4f}, ROI={author_stats['test']['roi']:+.1%}")

    t_end = time.time()
    print(f"\n  Runtime: {t_end - t0:.1f}s")
    print(f"  Users scored: {len(all_stats)}")
    print(f"  Projection at 1,547: ~{(t_end-t0)*1547/len(all_stats):.0f}s ({(t_end-t0)*1547/len(all_stats)/60:.1f} min)")


if __name__ == '__main__':
    main()
