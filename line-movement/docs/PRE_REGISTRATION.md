# Pre-Registration: MMA Betting Line Efficiency

This document records the design decisions that were fixed before results were examined.
It distinguishes between choices made a priori and those made after seeing data.

---

## Fixed Before Results Were Seen

### 1. Calibration gap definitions
- `g_open = win - p_open` (opening calibration gap, fighter perspective)
- `g_close = win - p_close_hi` (closing calibration gap, fighter perspective)
- `move = p_close_hi - p_open` (market revision in probability space)

All gaps are defined in Shin-devigged probability space, not in American or decimal odds.
The choice of probability space was fixed in advance: it is linear, symmetric, and directly
interpretable as calibration error.

### 2. Closing price
`close_hi` (best available book, line-shopping price) is the canonical closing line.
This is the most efficient closing price available and is consistent with the analysis
panel already constructed for Track A.

### 3. Fighter perspective
All gaps are computed from the fighter's perspective (one row per fighter per fight).
Opponent-perspective rows are not used as independent observations — they are the mirror
image and would double-count within-fight variation.

### 4. Exclusion of imputed opening odds
Rows where opening odds were imputed (`odds_imputed=True` in ufc_fights_clean.csv) are
excluded from the line-movement analysis. Imputed opening prices carry no real market
signal; including them would artificially compress `move` toward zero.

### 5. Pre-2020 / 2020+ split
The IS/OOS cut at year < 2020 was fixed by the Track A protocol carried over from
the SAPM rate screen. It was not chosen to optimise results in this track.

### 6. Clustering choice
Standard errors are clustered by `fighter_id` throughout. This was fixed before running
any regression, motivated by the repeated-observations structure of the panel.

### 7. The "counts as real" rule
A mechanism counts as real only if it is same-signed and significant (p < 0.05) in both
the pre-2020 and 2020+ subsamples. This rule was stated explicitly before the OOS split
was run (Phase 05). No post-hoc exceptions are made.

### 8. H0 for magnitude test
The magnitude test tests H0: coef(move) = 1 (not H0: coef = 0). This null — efficient
revision — was stated before the regression was run. The direction of departure (>1 =
underreaction, <1 = overreaction) was also defined in advance.

---

## Decisions Made After Seeing Data

### 1. Identification of the Mech A/B/C taxonomy
The labelling of mechanisms as A (g_open~move), B (win~p_open+move), and C (g_close~move)
was applied after observing that A and B were significant and C was not. This is purely
presentational; the regressions themselves were pre-specified.

### 2. The coherence note (coef difference = 1)
The arithmetic observation that coef(g_open~move) - coef(g_close~move) = 1.000 by
construction was noted after results were in. It is a check, not an additional test.

---

## What Was Not Pre-Registered

- The sparkline-derived features (total_path, monotone_frac, reversal_count) described
  in the session handout are exploratory and have not been tested as of this archival.
- Any regression involving the SAPM signals jointly with movement features.
