# Live Patterns — Phase B analysis
Run started: 2026-10-12T05:56:51.189263

## Loading data...
  Data loaded in 0.8s
  Crosswalk: 315 fights
  Kalshi trades: 2,729,470
  PM trades: 130,134
  Fights.csv: 8,758 unique fights
  Rounds_totals.csv: 41,186 rows

## Mapping crosswalk to ufcstats fights...
  Mapped 222/315 crosswalk fights to ufcstats hex IDs
  (0.0s)

## STEP B1 — FIGHT-START INFERENCE
  Indexing trades...
  Trade indexing: 5.3s (550 Kalshi tickers, 275 PM fights)
  Inferred fight start for 250 fights
  Validation on 103 finished fights (non-decisions):
    |error| distribution: median=58s, p25=21s, p75=261s, max=1566s
    signed error: mean=-52s (+ = expected too late)
    Worst 5 errors:
      20250607_DVAOMA: |err|=1566s, R3 SUBMISSION
      20260530_PAVTEI: |err|=1141s, R1 KO/TKO
      20250614_ABDBRU: |err|=1123s, R3 OVERTURNED
      20251011_DINPIN: |err|=1122s, R2 KO/TKO
      20260620_SHACHO: |err|=1065s, R1 KO/TKO
HARD GATE **B1-timing**: PASSED  median |error| = 58s
  B1 completed in 13.2s

## STEP B2 — ENTRY SET
  Entry set: 196 fights total
    Kalshi venue: n=195
    PM venue:     n=190
HARD GATE **B2-sample-size**: PASSED  max venue n = 195
  Fights with known outcome: 145
  B2 completed in 0.4s

## STEP B3 — FIGHTER-PATTERN VARIABLES
  Fighter-pattern variables computed for 111/196 entry-set fights
  B3 completed in 0.3s

## STEP B4 — CONFIRMATORY TEST
### Kalshi venue
  [Kalshi] n=106, win rate=0.462
    Coefficients: intercept=-0.2896, logit(p_R1break)=0.9010, DeltaX1=-0.3569
    DeltaX1 95% CI: [-2.1945, 1.6069]
    Calibration (p_R1break quintiles):
    Quintile     Price Range          n      Win Rate  
    Q1          [0.01, 0.24)           20     0.200
    Q2          [0.24, 0.46)           22     0.136
    Q3          [0.46, 0.63)           21     0.476
    Q4          [0.63, 0.76)           17     0.647
    Q5          [0.76, 0.99)           26     0.808
    Calibration by DeltaX1 tercile:
    T1 (DX1 [-0.589,-0.103)): n=35, win rate=0.457
    T2 (DX1 [-0.103,0.048)): n=36, win rate=0.361
    T3 (DX1 [0.048,0.779)): n=35, win rate=0.571
    No-X calibration (dropped >=10c):
      n=27, win rate=0.185, mean break price=0.253

### Polymarket venue
  [PM] n=104, win rate=0.462
    Coefficients: intercept=-0.1446, logit(p_R1break)=-0.1215, DeltaX1=0.2613
    DeltaX1 95% CI: [-1.4023, 2.3214]
    Calibration (p_R1break quintiles):
    Quintile     Price Range          n      Win Rate  
    Q1          [0.01, 0.24)           21     0.476
    Q2          [0.24, 0.40)           20     0.500
    Q3          [0.40, 0.59)           21     0.429
    Q4          [0.59, 0.74)           21     0.524
    Q5          [0.74, 1.00)           21     0.381
    Calibration by DeltaX1 tercile:
    T1 (DX1 [-0.589,-0.102)): n=35, win rate=0.429
    T2 (DX1 [-0.102,0.047)): n=34, win rate=0.353
    T3 (DX1 [0.047,0.779)): n=35, win rate=0.600
    No-X calibration (dropped >=10c):
      n=25, win rate=0.440, mean break price=0.244

  B4 completed in 3.8s

## STEP B5 — EXPLORATORY SCREEN
### Kalshi exploratory

  [Kalshi] Exploratory specs (n=106):
  Spec                           Coef       Wald SE    95% CI                   p-val   
  ----------------------------------------------------------------------------------
  DX2 (main)                     -0.0589    0.6390    [-1.3113, +1.1936]    0.927
  DX2 x moved_against            +0.0185    1.5765    [-3.0715, +3.1085]    0.991
  DX2 x 5round                   -1.0069    2.2224    [-5.3629, +3.3491]    0.650
  DX3 (main)                     -0.0092    0.0578    [-0.1225, +0.1041]    0.873
  DX3 x moved_against            +0.0011    0.1560    [-0.3047, +0.3069]    0.994
  DX3 x 5round                   +0.1982    0.2026    [-0.1989, +0.5953]    0.328
  DX4 (main)                     +0.1513    0.7360    [-1.2912, +1.5938]    0.837
  DX4 x moved_against            -0.1834    1.8882    [-3.8843, +3.5175]    0.923
  DX4 x 5round                   -2.0137    2.5716    [-7.0539, +3.0266]    0.434
  DX5 (main)                     -0.6798    1.1426    [-2.9194, +1.5598]    0.552
  DX5 x moved_against            +1.4513    2.5521    [-3.5509, +6.4535]    0.570
  DX5 x 5round                   -7.7003    4.6779    [-16.8689, +1.4684]    0.100

  [Kalshi] Observed min-p: 0.0997
  [Kalshi] Permutation-adjusted min-p: 0.2720 (from 1000 permutations)

### PM exploratory

  [PM] Exploratory specs (n=104):
  Spec                           Coef       Wald SE    95% CI                   p-val   
  ----------------------------------------------------------------------------------
  DX2 (main)                     +0.1268    0.5807    [-1.0114, +1.2649]    0.827
  DX2 x moved_against            -2.2357    1.4406    [-5.0593, +0.5879]    0.121
  DX2 x 5round                   +1.1629    2.6695    [-4.0694, +6.3952]    0.663
  DX3 (main)                     +0.0007    0.0509    [-0.0990, +0.1005]    0.988
  DX3 x moved_against            +0.2629    0.1479    [-0.0270, +0.5527]    0.075
  DX3 x 5round                   -0.4889    0.5102    [-1.4889, +0.5110]    0.338
  DX4 (main)                     +0.2085    0.6581    [-1.0814, +1.4984]    0.751
  DX4 x moved_against            +0.9360    1.5325    [-2.0676, +3.9396]    0.541
  DX4 x 5round                   +0.7557    2.2874    [-3.7276, +5.2390]    0.741
  DX5 (main)                     -0.3341    0.9538    [-2.2036, +1.5353]    0.726
  DX5 x moved_against            +3.8639    2.6622    [-1.3540, +9.0818]    0.147
  DX5 x 5round                   -4.7894    3.9226    [-12.4778, +2.8990]    0.222

  [PM] Observed min-p: 0.0755
  [PM] Permutation-adjusted min-p: 0.2260 (from 1000 permutations)

  B5 completed in 3.8s

## STEP B6 — STRATEGY SKETCH
### Top 2 exploratory hits:
  1. [PM] DX3 x moved_against: coef=+0.2629, p=0.0755
  2. [Kalshi] DX5 x 5round: coef=-7.7003, p=0.0997

### Hypothetical strategy returns:

  Strategy 1: DX3 x moved_against (PM)
    Direction: BUY YES when DeltaX3 > 1.934
    Trades: 35
    Mean P&L per trade: -0.0169 (-1.7 cents)
    Win rate: 0.486
    Total P&L: -0.59
    Sharpe (per-trade): -0.028

  Strategy 2: DX5 x 5round (Kalshi)
    Direction: BUY YES (contrarian) when DeltaX5 < -0.077
    Trades: 35
    Mean P&L per trade: -0.0280 (-2.8 cents)
    Win rate: 0.429
    Total P&L: -0.98
    Sharpe (per-trade): -0.068

  B6 completed in 0.0s

---

## Verdict

**ΔX1 (p_win_given_R2)**: coef −0.36 on Kalshi CI [−2.19, +1.61], +0.26 on PM CI [−1.40, +2.32] — straddles zero on both venues. **No-X calibration**: Kalshi R1-break prices are well-calibrated (Q1=0.20→Q5=0.81 realized win rate); pre-fight favourites dropping ≥10¢ during R1 win 18.5% at mean break price 0.25 — R1 losses are accurately priced. PM prices show poor calibration (all quintiles near 0.4–0.5), likely reflecting side-alignment noise. **Exploratory min-p**: PM 0.076 nominal (DX3 × moved_against) → 0.226 permutation-adjusted; Kalshi 0.100 nominal → 0.272 adjusted — no spec survives multiple-testing correction. Both strategy sketches show negative P&L after fees (−1.7¢ and −2.8¢/trade). Fighter career-pattern variables (cardio differential, comeback rate, R1 dependence, late finish rate, win-given-R2 rate) add zero predictive value beyond the R1-break price. The market efficiently incorporates known fighter tendencies by the end of Round 1. **No tradeable edge.**

Total runtime: 22.4s (full dataset: 41,186 round rows from 8,737 fights)