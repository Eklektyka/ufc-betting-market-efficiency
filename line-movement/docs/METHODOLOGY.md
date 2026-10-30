# Methodology: MMA Betting Line Efficiency

## Overview

This paper tests the informational efficiency of UFC betting markets using the BestFightOdds
(BFO) odds database matched to UFCStats fight records. The central question: does the
open-to-close line movement carry information about calibration error beyond what the closing
line itself already captures?

---

## Data

### UFCStats
All UFC events and fight-level statistics scraped from ufcstats.com (fights.csv, events.csv).
One row per fight, with fighter-level and bout-level statistics for both corners.

### BestFightOdds
Opening and closing American odds scraped from bestfightodds.com for all UFC bouts.
Schema: one row per fighter per fight, carrying both fighter and opponent odds:
`fighter_open`, `fighter_close_lo`, `fighter_close_hi`, `opponent_open`,
`opponent_close_lo`, `opponent_close_hi`, `fighter_sparkline`.

The dataset covers 18,660 rows (June 2007 – April 2026). Not all fights are mirrored:
5,534 fights have only one corner's BFO page; 6,563 have both. Since every row carries
both corners' odds, deduplication to 12,097 unique fights is sufficient for analysis.

### Coverage
Of 12,097 unique fights, 10,581 (87.5%) have real (non-imputed) opening and closing odds
for both corners. The opening implied probabilities sum to >1 in all cases, confirming vig
is present and Shin devigging is applicable.

---

## Pipeline

### Step 1 — Merge
`merge_datasets.py`: joins UFCStats fights to BFO odds on fighter URL (hex ID).

### Step 2 — Impute
`impute_odds.py`: where only one side's odds are known, the missing side is imputed
using the empirical median vig. Rows with imputed opening odds are flagged `odds_imputed=True`
and excluded from the line-movement analysis (they carry no real opening price signal).

### Step 3 — Filter
`filter_odds.py`: removes corrupted odds rows.

### Step 4 — Devig
`devig_shin.py`: applies Shin's (1993) two-outcome devigging method to convert raw
American odds to calibrated win probabilities. Produces `p_open_a/b`, `p_close_lo_a/b`,
`p_close_hi_a/b` per fight. The `close_hi` variant (best available book) is used throughout.

### Step 5 — SAPM
`build_sapm_expanding.py`, `build_sapm_residual.py`: compute expanding pre-fight
significant-strikes-absorbed-per-minute, residualised on opponent Glicko rating and division.

### Step 6 — Analysis panel
`build_analysis_panel.py`: joins all signals and produces the complete-case panel
`analysis_panel_cc.csv` (N=9,267, one row per fighter per fight, all covariates non-null).

---

## Line-Efficiency Analysis (Phases 00–07)

### Phase 00 — Coverage check
Verify both-corners open+close coverage in the raw BFO data.
Usable sample: 10,581 fights with real open and close_hi for both corners.

### Phase 01 — Build gaps
Restrict analysis_panel_cc.csv to fights with real (non-imputed) opening odds (N=8,112).
Compute:
- `p_open`: Shin-devigged opening win probability (from ufc_fights_clean.csv p_open_a/b)
- `g_open = win - p_open`
- `g_close = win - p_close_hi`
- `move = p_close_hi - p_open`

All computations in probability space (Shin-devigged). The `close_hi` (best available book)
closing price is used as the canonical closing line throughout.

### Phase 02 — Accuracy comparison
Brier score and MAE for open vs close. Bootstrap 95% CI on the Brier difference.

### Phase 03 — Movement informativeness
Regress `g_open ~ move` (clustered by fighter_id): does the revision predict the opening error?
Also test: `win ~ p_open + move` (does move add predictive power over p_open alone?).

### Phase 04 — Close efficiency
Regress `g_close ~ move` (clustered by fighter_id): does the revision predict residual error
at the close? If coefficient ~0 and insignificant, movement is fully impounded.

### Phase 05 — OOS split
Re-run significant mechanisms on pre-2020 (IS) and 2020+ (OOS) subsamples.
A result counts as real only if same-signed and significant (p<0.05) in both windows.

### Phase 06 — Forecast encompassing
Regress `win ~ p_open + p_close_hi`. If p_close_hi is significant while p_open collapses,
the closing line encompasses the opening line.

### Phase 07 — Magnitude test
Test H0: coef(move) = 1 in `g_open ~ move`. Coefficient = 1 means efficient revision;
>1 means underreaction; <1 means overreaction.

---

## Clustering

All regressions cluster standard errors by `fighter_id`. Rationale: the same fighter appears
multiple times across fights, inducing within-cluster correlation in outcomes and residuals.
Clustering at the fighter level accounts for this without imposing a specific correlation
structure.

---

## Shin Devigging

Shin's (1993) method solves for the "true" win probability z under the assumption that
a fraction z_insider of bettors are perfectly informed insiders. The bookmaker prices to
break even against this insider threat, creating the overround. Given observed implied
probabilities (p_a_raw, p_b_raw) from American odds, the system:

    p_a_raw = z_a + z * (1 - z_a)
    p_b_raw = z_b + z * (1 - z_b)
    z_a + z_b = 1

is solved numerically for z_a (the devigged win probability for fighter A).
