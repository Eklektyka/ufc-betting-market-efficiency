# Manifest: mma_line_efficiency_paper/

Generated: 2026-07-08
Archived from: C:/Users/micha/  and  C:/Users/micha/merged/
Git tag: submission-v1

---

## data/raw/

| File | Role | Rows | Notes |
|------|------|------|-------|
| `bfo_odds_raw.csv` | BestFightOdds scrape — opening, closing, sparkline odds for all UFC bouts | 18,660 | One row per fighter per fight. Do not modify. |
| `ufcstats_fights.csv` | UFCStats fight-level stats scrape | — | One row per fight. Do not modify. |
| `ufcstats_events.csv` | UFCStats event listing | — | Do not modify. |

---

## data/processed/

| File | Role | Rows | Cols |
|------|------|------|------|
| `analysis_panel_cc.csv` | Complete-case base panel; canonical N for Track A (SAPM rate screen) | 9,267 | 16 |
| `paths_panel_v1.csv` | Frozen open+close panel; canonical N for Track B (line efficiency); tagged paths-v1 | 8,112 | 20 |
| `PANELS.md` | Column lists and N counts for both panels | — | — |

---

## code/

### Pipeline scripts (data preparation, prefix p0x)

| File | Source | Role |
|------|--------|------|
| `p01_scrape_ufcstats.py` | ufcstats_scraper.py | Scrapes UFCStats for all events and fights |
| `p02_scrape_bfo.py` | bfo_scraper.py | Scrapes BestFightOdds for UFC bout odds |
| `p03_merge_datasets.py` | merge_datasets.py | Joins UFCStats fights to BFO odds on fighter URL |
| `p04_impute_odds.py` | impute_odds.py | Imputes missing one-sided odds using median vig |
| `p05_filter_odds.py` | filter_odds.py | Removes corrupted odds rows |
| `p06_devig_shin.py` | devig_shin.py | Applies Shin (1993) two-outcome devigging |
| `p07_build_sapm_expanding.py` | build_sapm_expanding.py | Expanding pre-fight SAPM per fighter |
| `p08_build_sapm_residual.py` | build_sapm_residual.py | SAPM residualised on opponent Glicko + division |
| `p09_build_analysis_panel.py` | build_analysis_panel.py | Assembles analysis_panel_cc.csv |

### Analysis scripts (phases 00–07)

| File | Phase | Reads | Writes | One-line result |
|------|-------|-------|--------|-----------------|
| `00_coverage_check.py` | Phase 00 | data/raw/bfo_odds_raw.csv | — | 10,581/12,097 fights (87.5%) have usable open+close; all opening sums >1 |
| `01_build_gaps.py` | Phase 01 | analysis_panel_cc.csv, ufc_fights_clean.csv | paths_panel_v1.csv | N=8,112 after excluding 1,155 imputed-open rows; both gap means = 0.000 |
| `02_accuracy_brier.py` | Phase 02 | paths_panel_v1.csv | — | Brier diff = -0.007308; 95% CI [-0.009, -0.006]; close more accurate |
| `03_movement_informative.py` | Phase 03 | paths_panel_v1.csv | — | g_open~move: coef=+1.039, p<0.0001; move adds predictive power |
| `04_close_efficiency.py` | Phase 04 | paths_panel_v1.csv | — | g_close~move: coef=+0.038, p=0.545; movement fully impounded at close |
| `05_oos_split.py` | Phase 05 | paths_panel_v1.csv | — | Mechs A+B real in both windows; Mech C rejected (sign flip) |
| `06_forecast_encompassing.py` | Phase 06 | paths_panel_v1.csv | — | p_close encompasses p_open in all three samples |
| `07_revision_magnitude_test.py` | Phase 07 | paths_panel_v1.csv | — | Cannot reject H0=1 in any window; revision magnitude efficient |

---

## results/

| File | Contents |
|------|----------|
| `phase00_coverage.txt` | BFO coverage fractions, example fights, vig check |
| `phase01_gaps_summary.txt` | Sample construction counts, summary stats for all gap variables |
| `phase02_brier.txt` | Calibration regression coefficients, MAE, Brier scores, bootstrap CI |
| `phase03_movement_informative.txt` | g_open~move and win~p_open+move regression tables |
| `phase04_close_efficiency.txt` | g_close~move regression table and coherence check |
| `phase05_oos_split.txt` | Pre-2020 / 2020+ tables for all three mechanisms, verdicts |
| `phase06_forecast_encompassing.txt` | win~p_open+p_close_hi tables, full and split samples |
| `phase07_magnitude_test.txt` | H0=1 test tables, full and split samples |

---

## docs/

| File | Contents |
|------|----------|
| `METHODOLOGY.md` | Full pipeline description, devigging method, phase-by-phase design |
| `PRE_REGISTRATION.md` | Decisions fixed before results were seen vs. post-hoc |
| `MANIFEST.md` | This file |

---

## Missing Files

| Expected file | Status | Reason |
|---------------|--------|--------|
| `ufc_fights_clean.csv` (merged/) | NOT COPIED — too large for archival, role is intermediate | Input to 01_build_gaps.py; recoverable by running p03–p06 pipeline scripts |
| Sparkline-feature analysis scripts | MISSING — not yet written | Exploratory phase noted in PRE_REGISTRATION.md as untested |
| Track A rate screen results (sapm_r_opp) | NOT IN THIS FOLDER | Separate analysis; documented in session_handout_2.md |

---

## Canonical Results Summary

**Sample:** N=8,112 fighter-fight observations (2007–2026); 4,830 pre-2020, 3,282 in 2020+.
All odds Shin-devigged to probability space; closing price = best available book (close_hi).
Opening odds restricted to non-imputed market prices.

**Brier accuracy:** Closing line Brier score (0.2125) is smaller than opening line (0.2199);
difference = -0.0073; bootstrap 95% CI [-0.0089, -0.0056]. Closing line is statistically
more accurate than opening line.

**Movement informativeness (Phase 03):** Regressing g_open on move yields coef=+1.039
(SE=0.064, p<0.0001, clustered by fighter_id). The market's revision predicts the residual
error in the opening price and adds independent predictive power (win~p_open+move move
coef=+1.039, p<0.0001).

**Close efficiency (Phase 04):** Regressing g_close on move yields coef=+0.038 (SE=0.064,
p=0.545). Movement's information is fully impounded into the closing line. No exploitable
residual error remains at the close.

**OOS stability (Phase 05):** The movement-informativeness result replicates in both
pre-2020 (coef=+1.119, p<0.0001) and 2020+ (coef=+0.936, p<0.0001). The close-efficiency
null also replicates (pre-2020: p=0.170; 2020+: p=0.486, sign flip).

**Forecast encompassing (Phase 06):** In win~p_open+p_close_hi, p_close_hi is significant
(p<0.0001) and p_open collapses to near-zero in all three samples. Closing line is a
sufficient statistic for the opening line.

**Revision magnitude (Phase 07):** Cannot reject H0: coef(move)=1 in any window
(full: p=0.545; pre-2020: p=0.170; 2020+: p=0.486). The market moves the right amount:
neither systematic overreaction nor underreaction.
