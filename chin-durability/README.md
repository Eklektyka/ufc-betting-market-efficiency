# UFC Betting Market Efficiency: Chin Durability as a Mispricing Signal

Empirical analysis of systematic mispricing in UFC fight betting markets. The central finding is that opponent chin vulnerability (`sapm_r_opp` — opponent strikes absorbed per minute, relative to division average) predicts market miscalibration out-of-sample, surviving Romano-Wolf correction over a family of 41 candidate variables.

---

## Motivation

The hypothesis is that betting markets systematically overvalue fighters facing chin-durable opponents, and undervalue fighters facing chin-damaged opponents. KO artists generate outsized media attention and highlight reels; markets appear to anchor on narrative rather than on the durability of the opponent's chin.

---

## Data

| Source | Coverage | Scrape Date |
|---|---|---|
| UFCStats | Fight outcomes, strike stats, fight-level totals | ~April 20, 2026 |
| BestFightOdds (BFO) | Opening and closing American odds, sparklines | ~April 20, 2026 |

**Sample after merging and cleaning:** 5,234 fighter-fight observations, 2008-06-21 – 2026-04-18.

Odds are devigged using the Shin (1993) method. Fighter style variables are career rolling averages residualised against division-adjusted opponent quality (`_r` suffix).

---

## File Structure

```
├── ufcs_scraper.py                  # UFCStats scraper
├── ufcstats_raw/
│   ├── events.csv
│   ├── fight_links.csv
│   ├── fight_totals.csv
│   └── scrape.log
├── preliminary results/
│   └── style_panel.csv              # Main analysis panel (N=5,234)
├── bfo_odds_final/
│   ├── bfo_odds_raw.csv             # Raw BFO odds (18,660 rows)
│   ├── bfo_odds_joined.csv          # BFO matched to UFC fights (13,872 rows)
│   ├── bfo_odds_devigged.csv        # Shin-devigged probabilities (13,830 rows)
│   ├── opp_sapm_analysis.py         # Primary analysis script
│   ├── age_at_fight_analysis.py     # Secondary finding: age mispricing
│   ├── run_exploratory_rw41.py      # Romano-Wolf over 41 candidate variables
│   └── robustness_raw_sapm.py       # Robustness: raw (non-residualised) sapm_opp
└── ufc_paper_visualizations/        # Figures (in progress)
```

---

## Analysis Pipeline

```bash
# Step 0: Rebuild _r variables with pre-fight opponent Glicko residualisation
python rebuild_panel_prefight_glicko.py          # Updates style_panel.csv in place

# Step 1-5: Analysis (run after panel is built)
python bfo_odds_final/opp_sapm_analysis.py       # Primary result + RW (5-var) + spec curve
python bfo_odds_final/age_at_fight_analysis.py   # Age secondary finding
python bfo_odds_final/robustness_raw_sapm.py     # Raw sapm_opp robustness
python bfo_odds_final/robustness_checks.py       # CGM two-way SE + drop overturned
python bfo_odds_final/rolling_window_efficiency.py  # Rolling window coefficient plot
```

---

## Key Results

### Primary: `sapm_r_opp` (opponent chin vulnerability)

| | Coefficient | SE | p-value |
|---|---|---|---|
| Full sample (N=5,234) | +0.01248 | 0.00288 | <0.001 *** |
| In-sample ≤2019 (N=2,678) | +0.01298 | — | 0.002 ** |
| Out-of-sample 2020–2026 (N=2,556) | +0.00997 | 0.00395 | 0.012 * |

OOS 95% CI: [+0.00224, +0.01771] — excludes zero.

- **Specification curve:** 100% positive-signed, 100% significant across 288 specifications
- **Romano-Wolf (5-variable family):** RW p = 0.0001, rank 1 of 5
- **Top-decile OOS gap:** +5.56 pp gross / +3.56 pp net of vig (N=256 bets; bootstrap CI crosses zero)
- **Robustness:** Result holds with raw (non-residualised) `sapm_opp`, corr = 0.99
- **Two-way CGM cluster SE:** inflation 1.002× — single-cluster SE is fine

### Secondary: `age_at_fight`

Markets systematically overvalue older fighters. The effect is threshold-based rather than gradual: no penalty for fighters ≤27 vs. prime (28–30), but calibration gap of −5.1 to −6.4 pp for fighters aged 31+. OOS coefficient is *larger* than IS (IS: −0.0051, OOS: −0.0068, p=0.009). Economically underpowered at N=184 OOS fade bets.

---

## Limitations

1. **Residualisation procedure:** Original panel builder (`run_style_matchup.py`) was deleted; `_r` variables reconstructed using pre-fight opponent Glicko-1 residualisation (`rebuild_panel_prefight_glicko.py`). Correlation with prior values: 0.95–1.00. Robustness check with raw `sapm_opp` (corr = 0.99 with residualised version) confirms the finding is not an artefact of this procedure.
2. **Glicko standardisation:** `glicko_z` was originally standardised on the full panel. Fixed to use training moments only; zero impact on results (`glicko_z` p = 0.42).
3. **No pre-registration:** The variable was selected through exploration of a 41-variable family. Romano-Wolf correction (rank 1 of 41, RW p = 0.0002) and a permutation test (12.8σ above null) are the formal responses to this concern. Theoretical motivation (chin durability and market anchoring on highlight performances) precedes the analysis.
4. **Bootstrap P&L CI crosses zero:** The statistical signal is robust; the economic signal is underpowered at the available OOS sample size. Top-decile strategy has 256 OOS bets.

---

## Dependencies

```
numpy
pandas
statsmodels
patsy
```

---

## Notes

The pipeline merging UFCStats and BFO data was not retained. The match was performed on fighter name (fuzzy) and event date, with `name_score` as a match quality indicator (retained in `bfo_odds_joined.csv`). All analyses use closing odds unless stated otherwise.
