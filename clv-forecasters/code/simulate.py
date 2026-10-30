#!/usr/bin/env python3
"""Simulation: null + skill models. Power via 95th-pctile of null draws."""

import csv, os, numpy as np

os.chdir(os.path.dirname(os.path.abspath(__file__)))

SEED = 67
N_USERS = 1547
N_DRAWS = 500
SIGMA_S_GRID = [0, 0.01, 0.02, 0.03]
STAKE = 100
DROP_RATE = 0.05
RANK_CUTOFF = '2026-04-17'


def to_dec(a):
    a = int(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


def load_fights():
    fights = []
    with open('bfo_close_all.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            fights.append({
                'p_fair_a': float(row['p_fair_a']),
                'p_fair_b': float(row['p_fair_b']),
                'dec_a': to_dec(row['best_line_a']),
                'dec_b': to_dec(row['best_line_b']),
                'window': 'rank' if row['event_date'] <= RANK_CUTOFF else 'test',
            })
    return fights


def run_draw(rng, F, pf_a, pf_b, dec_a, dec_b, is_rank, is_test, a_is_fav,
             fav_acc, dog_acc, mean_fav_acc, mean_dog_acc,
             user_dog_share, null_acc_u, sigma_s):
    """Run one draw, return dict of stat values."""

    outcomes = (rng.random(F) < pf_a).astype(np.float64)

    delta_u = rng.normal(0, sigma_s, size=N_USERS) if sigma_s > 0 \
              else np.zeros(N_USERS)
    s_u = np.clip(delta_u / (1 - null_acc_u), 0, 1)

    mask = rng.random((N_USERS, F)) >= DROP_RATE

    use_skill = rng.random((N_USERS, F)) < s_u[:, None]
    skill_pick_a = outcomes[None, :].astype(np.int8)
    pick_dog = rng.random((N_USERS, F)) < user_dog_share[:, None]
    style_pick_a = np.where(pick_dog, ~a_is_fav, a_is_fav).astype(np.int8)
    picks_a = np.where(use_skill, skill_pick_a, style_pick_a)

    a_won = outcomes[None, :]
    profit = np.where(
        picks_a,
        np.where(a_won, STAKE * (dec_a - 1), -STAKE),
        np.where(1 - a_won, STAKE * (dec_b - 1), -STAKE),
    ) * mask

    pf_picked = np.where(picks_a, pf_a, pf_b)
    win_picked = np.where(picks_a, a_won, 1 - a_won)
    n_active = mask.sum(axis=1)
    staked = n_active * STAKE
    user_roi = profit.sum(axis=1) / np.maximum(staked, 1)
    user_clv = ((win_picked - pf_picked) * mask).sum(axis=1) / \
               np.maximum(n_active, 1)

    rank_mask = mask * is_rank[None, :]
    test_mask = mask * is_test[None, :]
    rank_active = rank_mask.sum(axis=1)
    test_active = test_mask.sum(axis=1)
    rank_clv = ((win_picked - pf_picked) * rank_mask).sum(axis=1) / \
               np.maximum(rank_active, 1)
    test_clv = ((win_picked - pf_picked) * test_mask).sum(axis=1) / \
               np.maximum(test_active, 1)

    dec_n = max(1, N_USERS // 10)
    rank_order = np.argsort(-rank_clv)
    top_idx = rank_order[:dec_n]
    bot_idx = rank_order[-dec_n:]

    # (a) frac_roi_pos
    frac_roi_pos = float(np.mean(user_roi > 0))

    # (b) mean_clv_edge
    mean_clv_edge = float(np.mean(user_clv))

    # (c) rho(rank CLV, test CLV)
    valid = (rank_active > 10) & (test_active > 10)
    if valid.sum() > 30:
        rho = float(np.corrcoef(rank_clv[valid], test_clv[valid])[0, 1])
    else:
        rho = np.nan

    # (d) top-decile test CLV
    top_test_clv = float(test_clv[top_idx].mean())
    bot_test_clv = float(test_clv[bot_idx].mean())

    # (e) top - bottom
    top_minus_bot = top_test_clv - bot_test_clv

    # (f) divergence consensus ROI
    top_picks_a = picks_a[top_idx] * mask[top_idx]
    top_active_f = mask[top_idx].sum(axis=0).astype(float)
    top_share_a = np.where(top_active_f > 0,
                           top_picks_a.sum(axis=0) / top_active_f, 0.5)
    div_a = (top_share_a - pf_a) >= 0.10
    div_b = ((1 - top_share_a) - pf_b) >= 0.10
    div_any = (div_a | div_b) & is_test

    if div_any.sum() > 0:
        div_pick_a = div_a & div_any
        div_pick_b = div_b & div_any & ~div_a
        div_profit = np.where(
            div_pick_a,
            np.where(outcomes, STAKE * (dec_a - 1), -STAKE),
            np.where(div_pick_b,
                     np.where(1 - outcomes, STAKE * (dec_b - 1), -STAKE),
                     0))
        div_staked = div_any.sum() * STAKE
        div_roi = float(div_profit.sum() / max(div_staked, 1))
    else:
        div_roi = np.nan

    # (g) always-fav test ROI
    fav_profit = np.where(
        is_test,
        np.where(a_is_fav,
                 np.where(outcomes, STAKE * (dec_a - 1), -STAKE),
                 np.where(1 - outcomes, STAKE * (dec_b - 1), -STAKE)),
        0)
    af_roi = float(fav_profit.sum() / (is_test.sum() * STAKE))

    return {
        'frac_roi_pos': frac_roi_pos,
        'mean_clv_edge': mean_clv_edge,
        'rho_rank_test_clv': rho,
        'top_decile_test_clv': top_test_clv,
        'top_minus_bot_clv': top_minus_bot,
        'divergence_consensus_roi': div_roi,
        'always_fav_test_roi': af_roi,
    }


def main():
    rng = np.random.default_rng(SEED)
    fights = load_fights()
    F = len(fights)

    pf_a = np.array([f['p_fair_a'] for f in fights])
    pf_b = np.array([f['p_fair_b'] for f in fights])
    dec_a = np.array([f['dec_a'] for f in fights])
    dec_b = np.array([f['dec_b'] for f in fights])
    is_rank = np.array([f['window'] == 'rank' for f in fights])
    is_test = ~is_rank
    a_is_fav = pf_a >= 0.5

    fav_acc = np.maximum(pf_a, pf_b)
    dog_acc = np.minimum(pf_a, pf_b)
    mean_fav_acc = float(fav_acc.mean())
    mean_dog_acc = float(dog_acc.mean())

    user_dog_share = rng.beta(2, 12, size=N_USERS)
    null_acc_u = (1 - user_dog_share) * mean_fav_acc + user_dog_share * mean_dog_acc

    n_rank = int(is_rank.sum())
    n_test = int(is_test.sum())
    print(f'Fights: {F} (rank={n_rank}, test={n_test})')
    print(f'Users: {N_USERS}, Draws: {N_DRAWS}, Seed: {SEED}')

    stat_names = [
        'frac_roi_pos', 'mean_clv_edge', 'rho_rank_test_clv',
        'top_decile_test_clv', 'top_minus_bot_clv',
        'divergence_consensus_roi', 'always_fav_test_roi',
    ]

    common = dict(F=F, pf_a=pf_a, pf_b=pf_b, dec_a=dec_a, dec_b=dec_b,
                  is_rank=is_rank, is_test=is_test, a_is_fav=a_is_fav,
                  fav_acc=fav_acc, dog_acc=dog_acc,
                  mean_fav_acc=mean_fav_acc, mean_dog_acc=mean_dog_acc,
                  user_dog_share=user_dog_share, null_acc_u=null_acc_u)

    # Collect all draws per sigma_s
    all_draws = {}  # sigma_s -> {stat: np.array(N_DRAWS)}
    for sigma_s in SIGMA_S_GRID:
        print(f'\nRunning sigma_s={sigma_s} ...', end=' ', flush=True)
        draws = {s: np.empty(N_DRAWS) for s in stat_names}
        for d in range(N_DRAWS):
            r = run_draw(rng, sigma_s=sigma_s, **common)
            for s in stat_names:
                draws[s][d] = r[s]
        all_draws[sigma_s] = draws
        print('done.')

    # Compute thresholds from null (sigma_s=0) at 95th percentile
    null = all_draws[0]
    thresholds = {}
    null_sds = {}
    for s in stat_names:
        v = null[s]
        v_clean = v[~np.isnan(v)]
        thresholds[s] = float(np.percentile(v_clean, 95))
        null_sds[s] = float(np.std(v_clean))

    # Null rejection rate should be ~5%
    print('\n=== NULL SIZE CHECK ===')
    for s in stat_names:
        v = null[s]
        v_clean = v[~np.isnan(v)]
        rej = np.mean(v_clean > thresholds[s])
        print(f'  {s:<30} threshold={thresholds[s]:>9.4f}  '
              f'null_SD={null_sds[s]:>8.4f}  null_rej={rej:.1%}')

    # Power per sigma_s
    print(f'\n{"Statistic":<30} {"null SD":>8} {"thresh":>8}', end='')
    for sigma_s in SIGMA_S_GRID:
        label = 'null' if sigma_s == 0 else f'{sigma_s}'
        print(f' | {label:>12}', end='')
    print()
    print('-' * 110)

    rows_out = []
    for s in stat_names:
        row = {'stat': s, 'null_sd': null_sds[s], 'threshold': thresholds[s]}
        line = f'{s:<30} {null_sds[s]:>8.4f} {thresholds[s]:>8.4f}'
        for sigma_s in SIGMA_S_GRID:
            v = all_draws[sigma_s][s]
            v_clean = v[~np.isnan(v)]
            m = float(np.mean(v_clean))
            power = float(np.mean(v_clean > thresholds[s]))
            label = 'null' if sigma_s == 0 else f'{sigma_s}'
            line += f' | {m:>7.4f} {power:>4.1%}'
            row[f'mean_{sigma_s}'] = round(m, 6)
            row[f'power_{sigma_s}'] = round(power, 4)
        print(line)
        rows_out.append(row)

    # Save
    with open('sim_results.csv', 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['stat', 'null_sd', 'threshold']
        for sigma_s in SIGMA_S_GRID:
            fieldnames += [f'mean_{sigma_s}', f'power_{sigma_s}']
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    with open('sim_summary.md', 'w', encoding='utf-8') as f:
        f.write('# Simulation Summary\n\n')
        f.write(f'Fights: {F} (rank={n_rank}, test={n_test}) | '
                f'Users: {N_USERS} | Draws: {N_DRAWS} | Seed: {SEED}\n')
        f.write(f'Skill: delta_u ~ N(0,sigma_s), pick winner w.p. '
                f'delta_u/(1-null_acc)\n')
        f.write(f'Power: share of draws above 95th percentile of null '
                f'(sigma_s=0) distribution\n\n')

        f.write('| Statistic | Null SD | Threshold |')
        for sigma_s in SIGMA_S_GRID:
            label = 'null' if sigma_s == 0 else f'{sigma_s}'
            f.write(f' {label} mean |')
            f.write(f' {label} power |')
        f.write('\n|---|---|---|')
        f.write('---|---|' * len(SIGMA_S_GRID))
        f.write('\n')

        for row in rows_out:
            f.write(f'| {row["stat"]} | {row["null_sd"]:.4f} | '
                    f'{row["threshold"]:.4f} |')
            for sigma_s in SIGMA_S_GRID:
                f.write(f' {row[f"mean_{sigma_s}"]:.4f} |')
                f.write(f' {row[f"power_{sigma_s}"]:.1%} |')
            f.write('\n')

    print('\nWrote sim_results.csv + sim_summary.md')


if __name__ == '__main__':
    main()
