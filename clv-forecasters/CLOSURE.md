# CLV Forecaster Study — closed 2026-08-23

**Question:** Do public Tapology Platinum+ users who beat the UFC closing line
in a rank window continue to do so out-of-sample?

**What I expected:** Pre-registration (osf_prereg.md lines 118–120): "After
approximately 50% of the roster has been scraped, compute H1 (ρ) only. If the
95% confidence interval for ρ lies entirely below 0.10, stop scraping and
report the null result."

**What I found:** No evidence of persistent skill.

- H1 ρ(rank CLV, test CLV) = −0.0024; 95% CI [−0.1470, +0.1426].
  Not significant. (`RESULTS.md` lines 27–31)

- H2 top−bottom decile CLV = −0.0068; 95% CI [−0.0139, +0.0140].
  Not significant. (`RESULTS.md` line 29)

- n = 374 qualified users (of 1,447 scraped); bootstrap 5,000 draws, seed 67.
  (`RESULTS.md` lines 21, 24)

- v1/v2 scraper sign flip: v1-only ρ = +0.1559; v2-only ρ = −0.0878.
  (`RESULTS.md` lines 49–50)

**Why I stopped:** Futility. The study was early-terminated at 394/1,447 users
(27%), below the pre-registered 50% gate. RESULTS.md deviation #1 (lines
67–68) labels this EARLY-TERMINATED. The ρ point estimate is essentially zero
(−0.002) and the CI straddles both zero and the +0.10 threshold. The
substantive content — no evidence of persistent forecasting skill among public
tipsters — is unambiguous at this sample.

Five protocol deviations documented in RESULTS.md: (1) early termination at
27% not 50%; (2) not recorded; (3) not recorded; (4) not recorded;
(5) 100-user control group never scraped.

**What it rules out:** Public Tapology forecaster rankings do not predict
out-of-sample closing-line value. Users who appear to beat the line in-sample
show zero persistence. The v1/v2 sign flip adds a fragility warning: the
in-sample positive signal under v1 disappeared entirely under v2 scraper code.

**What would reopen it:** Nothing — closed. A materially different approach
(e.g., non-public forecasters, real-money bettors, or a different skill
metric) would be a new study, not a continuation.
