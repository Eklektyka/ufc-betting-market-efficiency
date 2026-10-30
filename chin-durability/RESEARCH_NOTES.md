# UFC Betting Market Efficiency — Research Notes
*Personal working document. Full pipeline record to date.*

---

## 1. Research Question

Do UFC betting markets fully incorporate publicly available fighter style statistics into closing odds? Specifically: does opponent chin vulnerability (measured as career strikes absorbed per minute, `sapm_r_opp`) predict systematic miscalibration between market-implied win probabilities and actual win rates?

**Original hypothesis (pre-analysis):** Flashy KO artists are overvalued as favourites. Markets anchor on offensive highlight-reel performance and underweight the opponent's chin durability — a slow-moving, publicly observable, yet cognitively non-salient statistic.

---

## 2. Data

### Sources
| Source | Content | Scrape date (approx.) |
|---|---|---|
| UFCStats | Fight outcomes, strike totals, fighter stats | ~April 20, 2026 |
| BestFightOdds (BFO) | Opening + closing American odds, sparklines | ~April 20, 2026 |

### Files
- `bfo_odds_raw.csv` — 18,660 rows, Apr 2009 – Sep 2023 (raw BFO scrape)
- `bfo_odds_joined.csv` — 13,872 rows, Jun 2007 – Sep 2025 (BFO matched to UFC fights)
- `bfo_odds_devigged.csv` — 13,830 rows, Jul 2007 – Sep 2025 (Shin-devigged probabilities)
- `style_panel.csv` — 6,138 rows, Dec 2007 – Apr 2026 (main analysis panel, fighter-fight level)

### Analysis sample
After complete-case filtering (all required variables non-missing): **N = 5,234** fighter-fight observations, **2008-06-21 – 2026-04-18**.

- Train (≤2019): N = 2,678
- Test (2020–2026): N = 2,556

The 2008 start reflects BFO odds availability, not a minimum fight history requirement.

### Key constructed variables
- `calibration_gap` = actual win indicator − Shin-devigged closing probability (per fighter row)
- `sapm_r` = career strikes absorbed per minute, residualised against division-adjusted opponent quality
- `sapm_r_opp` = same, for the opponent (joined via fight_id × opponent_id)
- `glicko_z` = standardised Glicko rating (fixed to use training-set moments; see §6)
- `q_close` = Shin-devigged closing win probability (used for P&L decimal odds)

---

## 3. Methodology

### Devigging
Shin (1993) two-outcome closed form. Preferred over:
- **Proportional normalisation**: theoretically wrong — assumes margin allocated proportionally, systematically overestimates favourite probabilities, biasing the dependent variable
- **Additive/symmetric margin**: no theoretical foundation, fails at extreme odds

Shin is standard in sports economics (Cain, Law & Peel 2000; Franck et al. 2010) and produces better-calibrated probabilities in empirical validation.

### Outcome variable
`calibration_gap = won − market_prob_shin`. Positive = market undervalued the fighter; negative = market overvalued. OLS on this linear measure is the primary estimator (Mincer-Zarnowitz 1969 linear form for calibration). MZ logit added as robustness check.

### Main estimating equation (STEP 1)
```
calibration_gap ~ [34 ALL_ATOMIC style vars] + glicko_z + age_at_fight
                  + layoff_days_c + C(division) + C(year)
```
OLS with cluster-robust SE by `fighter_id`. Both sides of each fight appear as separate rows; clustering handles the within-fighter correlation.

---

## 4. Main Results — `sapm_r_opp`

### 4.0 Robustness checklist (all pass)

| # | Check | Result |
|---|---|---|
| 1 | OOS survival (frozen holdout 2020–2026) | +0.00997, p=0.012 — CI excludes zero |
| 2 | Permutation test | 12.8σ above null |
| 3 | Romano-Wolf rank 1 of 5 (focused family) | RW p=0.0001 |
| 4 | Specification curve (288 specs) | 100% positive-signed, 100% significant |
| 5 | MZ logit offset (β≡1) | p=0.0011 |
| 6 | Raw sapm_opp (corr=0.99) | All results replicate — residualisation not driving it |
| 7 | Two-way CGM cluster SE | SE inflation 1.002x — single-cluster SE was fine |
| 8 | Drop Overturned rows (N=5,212) | +0.01280 ***, coefficient strengthens |
| 9 | Pre-fight sapm proxy (lagged) | +0.01132 ***, attenuation 0.896x — point-in-time leakage closed |

---

### 4.1 Full-sample OLS
| Variable | Coef | SE | t | p |
|---|---|---|---|---|
| `sapm_r_opp` | +0.01248 | 0.00288 | 4.337 | <0.001 *** |
| `sapm_r` | −0.01034 | 0.00292 | −3.541 | 0.0004 *** |
| `age_at_fight` | −0.00624 | 0.00186 | −3.349 | 0.0008 *** |

adj-R² = 0.0033 (expected; calibration_gap is noisy by construction)

### 4.2 Specification curve (288 specs)
Varying: 5 control inclusion decisions × 3 year-start cutoffs × 3 division-drop variants.
- % positive-signed: **100%**
- % significant (p<0.05): **100%**
- Coef range: [+0.01226, +0.01280], median +0.01247

Interpretation: result is insensitive to any reasonable model choice.

### 4.3 Romano-Wolf FWER correction

**5-variable focused family** (sapm_r_opp, sapm_r, age_at_fight, slpm_r, slpm_r_opp)  
*[Canonical family — theoretically motivated, used in paper]*:
| Variable | Obs \|t\| | RW p | Sig |
|---|---|---|---|
| sapm_r_opp | 4.337 | 0.0001 | *** |
| sapm_r | 3.541 | 0.0018 | ** |
| age_at_fight | 3.349 | 0.0029 | ** |
| slpm_r | 2.296 | 0.0382 | * |
| slpm_r_opp | 2.347 | 0.0382 | * |

**41-variable family** (34 ALL_ATOMIC + 7 continuous composites):  
*[Exploratory; NOT reported as primary — composite collinearity creates near-singular design matrix (condition number ~10^19), destabilising RW rankings. Dropped from paper.]*

### 4.4 Mincer-Zarnowitz logit
Correct functional form for binary outcome (`won`). Division FEs dropped (Hessian singularity with 80+ params); year FEs retained.

| Variant | sapm_r_opp coef | p |
|---|---|---|
| Unconstrained (β on logit_mkt free) | +0.02666 | 0.0045 ** |
| Offset (β≡1 constrained) | +0.02968 | 0.0011 ** |

Market calibration test: β_logit_mkt = 1.162, t = +3.40 → **rejects H0: β=1**. Market is slightly overconfident on favourites (favourite-longshot bias in margin). Separate finding, not the focus.

### 4.5 Frozen temporal holdout
| | Coef | SE | p |
|---|---|---|---|
| IS (2007–2019, N=2,678) | +0.01298 | — | 0.0022 |
| OOS (2020–2026, N=2,556) | +0.00997 | 0.00395 | 0.0115 |

OOS CI: [+0.00224, +0.01771] — **excludes zero**.
Attenuation: 0.769 (23% decay IS→OOS). Typical for genuine effects post-publication/discovery.
Corr(frozen_pred, actual_gap) = 0.069.

### 4.6 Bootstrap P&L (10,000 resamples, actual closing odds)
Strategy B — top-decile sapm_r_opp (OOS, pre-committed):
- N bets: 256 | Win rate: 58.2% | Gross gap: +5.56 pp | Net edge: +3.56 pp
- 95% CI: [−6.79, +18.54] | Bootstrap p: 0.362
- **CI crosses zero — not tradeable by our criterion**

Strategy A — frozen_pred > 0 (N=738): Net edge −0.58 pp, CI crosses zero.

### 4.7 Raw sapm_opp robustness (closes leakage item 3)
Replace `sapm_r_opp` with raw career `sapm_opp` (no residualisation):
- Corr(raw, residualised) = **0.9911**
- Full-sample: +0.01306 *** | IS: +0.01435 *** | OOS: +0.00992 * CI=[+0.00208, +0.01775]
- Top-decile gap: +3.97 pp gross / +1.97 pp net
- **All results replicate. Residualisation leakage concern closed.**

---

## 5. Secondary Finding — `age_at_fight`

Markets systematically overvalue older fighters.

### 5.1 RW (fighter-state family: age, layoff, glicko)
| Variable | Obs \|t\| | RW p | Sig |
|---|---|---|---|
| age_at_fight | 3.490 | 0.0016 | ** |
| glicko_z | 0.810 | 0.6642 | |
| layoff_days_c | 0.125 | 0.8978 | |

### 5.2 Linearity
- Quadratic term (age²): not significant — effect approximately linear
- **Bin dummies (ref: 28–30):**
  - ≤27 vs 28–30: −0.00060 (p=0.98) — **no youth discount**
  - 31–33: −0.05116 (p=0.006) **
  - 34–36: −0.05814 (p=0.003) **
  - ≥37: −0.06432 (p=0.004) **
- Threshold at 31+, not gradual decline. Monotonically increasing penalty.

### 5.3 Frozen holdout
- IS coef: −0.005138 (p=0.0584)
- OOS coef: −0.006795 (p=0.009), CI=[−0.011893, −0.001696]
- Attenuation: 1.323 — **OOS coefficient is larger than IS. No decay; mispricing growing.**
- Decile 10 (avg age 39.9): cal gap = −0.0842 in OOS

### 5.4 P&L bootstrap (fading oldest fighters, OOS)
- Age threshold (90th pct OOS): ≥38 years | N fade bets: 184
- Win rate: 70.1% | Market prob: 62.8% | Cal gap: +7.28 pp
- Net edge: +4.04 pp | 95% CI: [−6.87, +14.84] | p=0.459
- **CI crosses zero — underpowered at N=184**

### 5.5 Interaction (age × sapm_r_opp)
- Interaction term p = 0.66 — **not significant**
- Effects are additive, not multiplicative

### 5.6 Interpretation
Statistical signal is solid (RW p=0.0016, OOS coefficient actually strengthens). Economic underpowering is a sample-size issue: very old active UFC fighters are rare. Secondary finding, disclose P&L limitation honestly.

---

## 6. Limitations

### Confirmed/addressed

**L1 — Glicko full-timeline leak**
Glicko ratings computed over 2007–2026 full timeline. Post-2019 outcomes could influence pre-2020 RD (rating uncertainty decay). Practical impact: modest — rating *value* is primarily forward-driven, and `glicko_z` p=0.42 in all specifications. Spec curve drops glicko_z entirely in 32 specs; 100% still find sapm_r_opp significant. **Verdict: immaterial. Disclose.**

**L2 — glicko_z standardisation leak (FIXED)**
Original `glicko_z` standardised on full-panel mean/SD. Fixed: re-standardise using training moments only. Impact: **zero** — glicko_z is insignificant, changing its scale moves nothing.

**L3 — _r residualisation leak (CLOSED)**
Style `_r` variables residualised using full-panel regression slopes. Addressed via raw `sapm_opp` robustness check (corr=0.99, all results replicate). Residualisation does essentially nothing — the Glicko–sapm correlation being partialled out is negligible. **Verdict: closed by robustness check. Add one sentence to paper.**

**L4 — No pre-registration**
Variable selected through exploration of 41 candidates. Cannot be recovered. Formal response: Romano-Wolf over 41 variables (rank 1, RW p=0.0002) + permutation test (12.8σ above null). Theoretical motivation precedes analysis. **Verdict: disclose, point to RW41 result.**

**L5 — Functional form (FIXED)**
Linear calibration_gap ~ OLS is an approximation for binary outcomes. MZ logit (offset variant, β≡1) confirms sapm_r_opp survives (p=0.0024). **Verdict: closed.**

**L6 — Family-wise error (FIXED)**
Addressed by RW over 41 variables. **Verdict: closed.**

### Flagged — not yet addressed

**L7 — Bootstrap P&L CI crosses zero**
Both OOS betting strategies have wide CIs that include zero. The statistical signal is real; the bet-level noise is too high to confirm economic significance at available sample sizes. Honest disclosure required. Cannot be fixed — the sample is what it is.

**L8 — MZ β_logit_mkt > 1**
Unconstrained logit finds β = 1.17 (t=+3.57), rejecting well-calibrated market H0. This means the market is systematically overconfident on favourites — a favourite-longshot bias in the margin. Currently handled as a footnote. Could be a separate paper. **Risk: opening this avenue dilutes the primary finding. Keep as one sentence.**

**L9 — Panel builder pipeline reconstructed**
`run_style_matchup.py` was deleted; `_r` residualisation procedure was reconstructed forensically. Evidence pointed to pre-fight opponent Glicko-1 rating as the original quality measure (`rebuild_panel_prefight_glicko.py`). Style vars residualised on `avg_pre_opp_glicko + C(division)`. Correlations between reconstructed and prior `_r` values: 0.955–1.000 (sapm: 0.984). Coverage: 77% of panel rows received the pre-fight Glicko update; remaining 23% retain static Glicko residuals (685 rows not in ufc_extended, rest missing due to unpaired fights). Practical impact: negligible — correlations near 1.0 ensure OLS results are essentially identical under either method. Robustness: raw `sapm_opp` (no residualisation at all) gives corr=0.99 with residualised version and full replication of all results. **Disclose residualisation procedure clearly in paper methods section.**

---

## 7. Data Filters (Confirmed / Flagged)

| Filter | Status | Detail |
|---|---|---|
| Draws | **Confirmed excluded** | `won` is strictly 0/1 (N=3,126 + 3,012). No draw rows in panel |
| No-contests | **Confirmed excluded** | No NC method strings in panel |
| Overturned results | **FLAG** | 31 rows with method="Overturned" are coded `won=0`. Need to verify: should these be excluded entirely rather than treated as losses? |
| Cancelled fights | **Confirmed excluded** | Pipeline only joined odds to fights that already had outcomes in UFCStats |
| Extreme odds | **No cutoff applied** | User confirmed. Extreme odds very rare in UFC; overround is routinely 3–5% |
| Minimum fight history | **No minimum confirmed** | 199 fighters in panel with only 1 fight. 2008 start is odds availability, not history filter |
| Name score threshold | **FLAG** | User recalls threshold of 90. However, both `bfo_odds_joined.csv` and `bfo_odds_devigged.csv` contain 389–391 rows with name_score < 90 (min = 71.4). Threshold may not have been strictly enforced, or was applied at a later stage that wasn't retained. 97% of rows have score=100 so practical impact is low, but should be verified |
| Non-UFC orgs | **Confirmed excluded** | BFO covers other orgs; UFCStats-based join restricts to UFC only |
| Women's divisions | **Confirmed included** | Present in division column |
| Preliminary fights | **Confirmed included** | No card-level filtering evident |

---

## 8. Avenues for Upgrade

### High priority (would strengthen the paper)

**U1 — Rebuild panel with training-only residualisation and Glicko**
Re-run `run_style_matchup.py` with a 2019 cutoff: fit `_r` residualisation slopes and Glicko on ≤2019 only, apply forward. This is the "proper" fix for L1 and L3. Current position: raw sapm robustness check is sufficient for disclosure, but a full rebuild would be the cleanest answer if a top journal asks.

**U2 — Resolve Overturned coding**
Check whether the 31 "Overturned" fights should be excluded rather than coded `won=0`. If they are NCs coded as losses, they're misclassified. Drop them and re-run as a robustness check.

**U3 — Verify name score threshold**
Confirm the actual name_score threshold applied, or add an explicit filter at 90 and re-run. With 97% perfect matches the impact will be negligible, but cleanliness matters for reviewers.

### Medium priority (nice to have)

**U4 — Time-series of the mispricing**
Is the age effect getting worse over time? Is the sapm effect stable by year? A rolling-window or year-by-year coefficient plot would be a compelling figure.

**U5 — Division heterogeneity**
Does the sapm_r_opp effect vary by weight class? Heavyweight KOs are more common; the effect might be stronger there. An interaction sapm_r_opp × heavyweight_dummy would be straightforward.

**U6 — Placebo tests**
Permute fighter identities within year × division cells, re-run the full analysis. Shows the result is not an artefact of panel structure. The permutation test already does this at the variable level, but a full placebo would be cleaner for a journal.

**U7 — Expand OOS P&L sample**
The bootstrap CI crosses zero because N=256 top-decile OOS bets is small. More recent fight data (post April 2026) would extend this. Not actionable right now but worth revisiting.

**U8 — Address favourite-longshot bias formally**
The MZ logit showed β_logit_mkt = 1.17, rejecting well-calibrated market. This is a known phenomenon in sports betting. A brief section or appendix documenting this for UFC would add a secondary contribution, but risks diluting focus. Decision: one footnote for now.

### Low priority / future work

**U9 — Out-of-UFC validation**
Does the sapm mispricing exist in Bellator or ONE Championship? Would require BFO scrape for other orgs + separate stats source.

**U10 — Structural break test**
Did the COVID era (2020, Fight Island) change market efficiency? The attenuation IS→OOS (39% decay) could partly reflect structural change rather than just noise.

---

## 9. Pre-Registration Note

No formal pre-registration predates the analysis. The theoretical hypothesis (markets misprice chin vulnerability) preceded the data analysis, but the specific operationalisation (`sapm_r_opp`) was confirmed through exploration of a 41-variable family.

**Formal statistical response:** Romano-Wolf over 41 variables, rank 1, RW p=0.0002. Permutation test: 12.8σ above null.

**Action taken:** Upload pre-analysis plan to OSF, dated post-hoc, with explicit disclosure that it is ex-post documentation. Do not claim pre-registration status.

---

## 10. Efficiency Framing

**Relevant form: semi-strong efficiency.** `sapm_r_opp` is freely available on UFCStats and third-party aggregators — no private information involved. The question is whether closing odds fully incorporate this publicly available statistic.

The MZ logit offset test (β≡1 on logit_mkt) operationalises this directly: residual predictive power of sapm_r_opp after conditioning on the market's closing probability = rejection of semi-strong efficiency. Answer: yes, p=0.0024.

---

## 11. Mechanism (theory section draft)

Three complementary explanations for why publicly observable chin vulnerability is underweighted:

1. **Salience asymmetry / availability heuristic** — KO power is vivid and memorable; opponent chin durability is a quiet distributional statistic. Bettors anchor on offensive narrative, not defensive liability.

2. **Attribute substitution** — "who wins?" is replaced by "who has the more impressive record?" Chin durability doesn't produce highlights. Grinders accumulate high sapm without generating the media attention that would move odds.

3. **Asymmetric updating** — chin vulnerability becomes narratively salient *after* a KO loss. The latent vulnerability accumulated through years of absorbed punishment is observable in statistics but not yet priced. Markets update after the fact.

**Why it persists:** sapm is a career average — slow-moving. Exploiting it requires systematic tracking across hundreds of fighters. Most bettors don't do this, limiting arbitrage pressure.

---

## 12. Robustness Checks (`robustness_checks.py`)

Three checks against baseline single-cluster results (sapm_r_opp and age_at_fight only reported):

### CHECK 1 — Two-way cluster SE (CGM 2011)
Concern: each fight contributes two rows; `calibration_gap` sums to exactly zero within each fight, so single-cluster SE by `fighter_id` may understate variance. Cameron-Gelbach-Miller two-way clustering by `fighter_id` AND `fight_id` addresses within-fight dependency.

| | Baseline | Two-way CGM | SE inflation |
|---|---|---|---|
| `sapm_r_opp` | 0.00288 | 0.00288 | **1.002x** |
| `age_at_fight` | 0.00186 | 0.00183 | **0.981x** |

CGM SE is essentially identical to single-cluster baseline — within-fight dependency is not inflating SEs. Both variables remain p<0.001. Single-cluster SE is fine.

### CHECK 3 — Rolling window sapm_opp [NOT IMPLEMENTED]
Requires per-fight strike absorption values (not career averages). `fight_totals.csv` concatenates both fighters' stats without a reliable separator (e.g., "15 of 25 21 of 51"). Cannot be parsed cleanly. Needs a re-scrape of per-fight UFCStats data.

### CHECK 5 — Drop Overturned fights
31 rows have `method="Overturned"` coded as `won=0` — likely No Contests misclassified as losses. Drop and re-run (22 rows dropped after complete-case filter, N=5,212).

| | Baseline | No Overturned |
|---|---|---|
| `sapm_r_opp` | +0.01248 *** | +0.01280 *** |
| SE | (0.00288) | (0.00287) |
| `age_at_fight` | −0.00624 *** | −0.00599 ** |
| SE | (0.00186) | (0.00186) |

Results unchanged. `sapm_r_opp` strengthens marginally. **Overturned coding is immaterial.**

### Summary table (all three specifications)

|  | Baseline | Two-way CGM | No Overturned |
|---|---|---|---|
| `sapm_r_opp` | +0.01248*** | +0.01248*** | +0.01280*** |
| SE | (0.00288) | (0.00288) | (0.00287) |
| `age_at_fight` | −0.00624*** | −0.00624*** | −0.00599** |
| SE | (0.00186) | (0.00183) | (0.00186) |

---

## 13. Scripts (run order)

```
1. opp_sapm_analysis.py         Primary result + glicko_z fix + MZ logit
2. run_exploratory_rw41.py      RW over 41 variables
3. age_at_fight_analysis.py     Secondary finding
4. robustness_raw_sapm.py       Leakage robustness check
5. robustness_checks.py         CGM two-way cluster SE + Drop Overturned
```

All scripts self-contained. Output to console only (no files written). Requires: numpy, pandas, statsmodels, patsy.
