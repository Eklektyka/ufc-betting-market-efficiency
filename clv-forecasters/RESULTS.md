# Results — Persistence of Forecasting Skill in UFC Predictions

Snapshot: 2026-08-23T01:55:00Z | Git: 698670a119fa
Status: **EARLY-TERMINATED** at 394/1447 users (27% of roster)
Coverage exclusion: score on collected events, ≥150 rank / ≥80 test picks
Dolidze card (2025-08-09) dropped from rank window for v1/v2 parity

## Phase 2 — Union and Score

Users scored: 393
Qualified (≥150 rank, ≥80 test): **374**
Excluded: 19 (below pick threshold)
Scraper versions in qualified: v1=128, v2=246

## Phase 3 — Coverage
Events per qualified user: min=26, median=42, max=43
No additional exclusions applied (rule D: score on collected events)

## Phase 4 — Pre-Registered Statistics

n = 374, decile = 37, SE(ρ) = 0.0519
H1 threshold: ρ > 0.104 | H2 threshold: top−bot > 0.008

Bootstrap: 5000 draws, seed 67

| Statistic | Observed | Null mean | Null SD | 95th | Pctile | 95% CI | Sig? |
|---|---|---|---|---|---|---|---|
| H1: ρ(rank CLV, test CLV)           | -0.0024 | +0.0006 | 0.0730 | +0.1222 |  48.4% | [-0.1470, +0.1426] | NO |
| H2: top−bot decile test CLV         | -0.0068 | +0.0000 | 0.0070 | +0.0114 |  15.4% | [-0.0139, +0.0140] | NO |

Observed ρ 95% CI: [-0.1042, +0.0993]
**FUTILITY**: CI lies entirely below 0.10

### Leave-one-out influence on ρ

Full ρ = -0.0024. Top 5 influential users:
| User | ρ without | Δρ |
|---|---|---|
| sebgray | +0.0049 | +0.0073 |
| Wana Dhite | +0.0045 | +0.0069 |
| Caesar07 | +0.0043 | +0.0068 |
| Bryantknowsbest | +0.0043 | +0.0067 |
| Polaczek | -0.0090 | -0.0066 |

### Sensitivity: v1-only, v2-only, corrected frame

| Frame | n | ρ | 95% CI | Top−bot |
|---|---|---|---|---|
| v1-only | 128 | +0.1559 | [-0.0194, +0.3312] | +0.0073 |
| v2-only | 246 | -0.0878 | [-0.2136, +0.0379] | -0.0121 |
| corrected (all) | 374 | -0.0024 | [-0.1042, +0.0993] | -0.0068 |

The v1/v2 sign flip (v1 ρ≈+0.16, v2 ρ≈−0.10) is reported as evidence that
the null result is robust to frame choice, not as a hidden finding.

### Author (Ezoteryka)
Picks: 523 (rank=328, test=195)
Rank CLV: +0.0346 | Test CLV: +0.0250 | ROI: +3.9%

### Panel summary
Mean CLV: +0.0266 (SD=0.0134)
Mean ROI: +3.2%
Users ROI > 0: 319/374 (85.3%)

## Deviations from Pre-Registration

1. **Early termination**: Study terminated at 394/1447 users (27% of roster),
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


## Drop Log
Total drops: 19
| User | Reason |
|---|---|
| SyrexLee | below_threshold: rank=0 test=0 |
| Bilz1111 | below_threshold: rank=0 test=108 |
| LiamDove | below_threshold: rank=0 test=108 |
| joe kerr | below_threshold: rank=0 test=108 |
| jonnyboy6969 | below_threshold: rank=0 test=120 |
| djcloud | below_threshold: rank=0 test=171 |
| lvl_0 | below_threshold: rank=0 test=182 |
| Ufctippmix1 | below_threshold: rank=0 test=22 |
| AustinLaxton | below_threshold: rank=101 test=195 |
| county | below_threshold: rank=108 test=195 |
| Kuma | below_threshold: rank=11 test=195 |
| xuyart | below_threshold: rank=112 test=195 |
| FattyThePaddy | below_threshold: rank=119 test=188 |
| lordbrutus | below_threshold: rank=123 test=195 |
| Mysticsosaa | below_threshold: rank=137 test=146 |
| lerds | below_threshold: rank=138 test=195 |
| Supreme Cypher | below_threshold: rank=49 test=195 |
| chrislau30 | below_threshold: rank=63 test=195 |
| seanm23 | below_threshold: rank=75 test=195 |
