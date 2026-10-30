# OSF Pre-registration

## Study Information

**Title.** Persistence of forecasting skill against the closing line in a public MMA prediction panel (Tapology, UFC, Aug 2025–Aug 2026).

**Description.** We test whether public MMA prediction-market participants who beat the best available closing moneyline in one time period continue to do so in a later, disjoint period. Picks come from the Tapology platform's public prediction leaderboard for UFC events. Closing odds come from BestFightOdds event pages. The core test is whether rank-window CLV (closing-line value) predicts test-window CLV across users—a pattern consistent with genuine forecasting skill and inconsistent with luck.

**Existing data.** Odds data have been collected (see Data section). User picks have not yet been scraped. The user roster is frozen. The analysis plan, thresholds, and null simulation were developed using pilot data from one user (Ezoteryka, Platinum tier, rank 1,242) and one additional user (The Cilantro Guy, Legend tier, rank 1). Both are excluded from all inferential tests.

## Hypotheses

### Primary (one-sided, α = 0.05)

**H1.** Spearman ρ between rank-window CLV and test-window CLV across eligible users is greater than zero.

Decision rule: reject the null if ρ > 0.1036.

**H2.** The mean test-window CLV of the top decile of users (ranked by rank-window CLV) minus the mean test-window CLV of the bottom decile is greater than zero.

Decision rule: reject the null if the difference > 0.0079.

### Secondary

**S1.** Divergence strategy ROI in the test window is positive. On each test-window fight, compute the top-decile consensus share per side. Bet the side whose consensus share exceeds the fair probability by ≥ 10 percentage points. Flat stake at the best sportsbook closing line. The 10pp threshold is fixed.

Decision rule: reject the null if ROI > 0.1158 (11.58%).

**S2.** The mean test-window CLV of the top decile (by rank-window CLV) is positive.

Decision rule: reject the null if CLV > 0.0328.

### Descriptive (reported, not tested)

- Share of users with ROI > 0 overall and per window.
- Roster mean CLV overall and per window.
- Full rank-window and test-window CLV distributions (histograms).
- Fav/dog accuracy and ROI splits per window.
- Per-event match rate and coverage.

### Baselines

- Always-favourite ROI in the test window.
- Whole-roster divergence strategy ROI using the same 10pp rule.
- A positive S1 is attributed to selection by rank-window CLV only if it exceeds the whole-roster divergence strategy version.

### Control

Repeat H1 and H2 with the 100-user control sample pooled into the roster. Report whether the control group's test-window CLV differs from the main roster's after conditioning on rank-window CLV.

## Design Plan

**Study type.** Observational; archival data from a public prediction platform and a public odds-comparison site.

**Blinding.** The analyst has seen pilot results for two users (Ezoteryka, The Cilantro Guy). No user picks beyond those two have been examined. Thresholds and the analysis plan are locked before the remaining picks are scraped.

## Sampling Plan

**Existing data.** Odds: scraped from BestFightOdds event pages on 2026-08-20 (collected_at_utc range: 2026-08-20T15:29:11Z to 2026-08-20T19:28:33Z). Files frozen at git commit b2f036abc8702c4142f112b7aaa39faa72a4a177.

**User roster.** 1,447 users in final_users.csv (sha256: cfac1ea5965dc3cd214c4520f26841cf560db3521b7abda2d83e0c81d9379191). Selection rule:

- Tier: Platinum or higher (Legend, Grand Champ, Champion, Diamond, Platinum) on the Tapology all-time leaderboard as of August 2026.
- Total picks: ≥ 118 (98% completion rate across the 10-event leaderboard window).
- Activity: present on the August 9, 2025 (Dolidze vs. Hernandez) or August 16, 2025 (UFC 319) event leaderboard.

Plus 100 users sampled at random from leaderboard ranks 2,124–7,000 under the same participation rule (control group). Total roster: 1,547 users.

**Exclusions.** The author's own Tapology account (Ezoteryka) is excluded from all inferential tests and reported separately as a pilot. The Cilantro Guy is also reported separately as a pilot. Users entering inferential tests must have ≥ 150 rank-window and ≥ 80 test-window scored picks (picks matched to a BFO closing line).

**Data collection.** Picks will be scraped from public Tapology profile prediction pages using Playwright with residential proxy at ≤ 1 request per 4 seconds. Estimated runtime: ~131 hours for 1,547 users.

## Variables

**Independent variable.** Rank-window CLV: the user's mean CLV edge over all scored picks in the rank window.

**Dependent variable.** Test-window CLV: the user's mean CLV edge over all scored picks in the test window.

**CLV edge per pick.** outcome (1 if the user's picked fighter won, 0 otherwise) minus the fair probability of the picked side. Fair probability = implied probability from the best sportsbook closing line for that side, normalised so both sides sum to 1.

**ROI.** Total profit at flat $100 stake against the best sportsbook closing line, divided by total amount staked.

**Best line.** Maximum closing American odds across sportsbooks with is_book = 1 (Polymarket and Kalshi excluded). Sportsbooks in the test window: FanDuel, Caesars, BetRivers, BetWay, Unibet. Rank window: same five plus BetMGM on older cards. Differences between windows: ≤ 12 American odds points on overlap checks.

**Windows.** Rank window: UFC cards from 2025-08-09 (Dolidze vs. Hernandez) through 2026-04-17. Test window: 2026-04-18 (Burns vs. Malott) through 2026-08-15 (UFC 330). Disjoint by construction. 349 rank-window matchups, 200 test-window matchups in bfo_close_all.csv (549 total). No user is ranked on any test-window data.

**Manual entries.** Two bouts entered from user recall, flagged source = 'manual_recall' in bfo_close_manual.csv (sha256: 11f9bbf21ed0f9b6d3ad2d01de59f566840648ea2fde122dae55949e73888624):

1. Charles Johnson −115 / Eduardo Chapolin +100 (UFC 330).
2. Abdul Rakhman Yakhyaev −2000 / Raffael Cerqueira +950 (UFC Fight Night: Tsarukyan vs. Hooker).

All analyses are reported with and without these two bouts.

## Analysis Plan

**Statistical models.** No regression models. All inference is nonparametric.

**Primary tests (H1, H2).** Spearman rank correlation (H1) and top-minus-bottom decile difference (H2), each compared to a null distribution generated by fight-clustered bootstrap (see below).

**Null model.** For each of 5,000 bootstrap draws (seed 42): resample each fight's outcome independently from its fair probability (Bernoulli with p = p_fair_a for side A winning). Apply the same resampled outcome to every user's pick on that fight. Recompute all statistics. The decision threshold for each statistic is the 95th percentile of its null distribution. This ensures exact 5% size under the null for each test individually.

**Thresholds (from current simulation with 1,547 users, 549 fights, 500 draws, seed 67; to be re-derived with the final roster size and fight count before unblinding, test choice fixed).**

| Test | Statistic | Null 95th pctile | Null SD |
|------|-----------|-----------------|---------|
| H1 | ρ(rank CLV, test CLV) | 0.1036 | 0.0636 |
| H2 | Top − bottom decile CLV | 0.0079 | 0.0054 |
| S1 | Divergence consensus ROI | 0.1158 | 0.0853 |
| S2 | Top-decile test CLV | 0.0328 | 0.0211 |

**Multiple comparisons.** Two primary tests; no family-wise correction applied (both must reject for the overall conclusion "skill persists"). Secondary tests are labelled as such. No correction across S1/S2.

**Leave-one-card-out.** For S1 (divergence consensus ROI), repeat the analysis dropping each test-window card in turn. Report the range of ROI estimates.

**Sensitivity.** All analyses reported with and without the two manual-recall bouts. All analyses reported with and without the 100-user control group.

**Inference criteria.** One-sided tests at α = 0.05. A statistic exceeding the null 95th percentile is declared significant. Confidence intervals are the 2.5th–97.5th percentile of the null bootstrap.

**Interim analysis.** Users are scraped in a random order. After approximately 50% of the roster has been scraped, compute H1 (ρ) only. If the 95% confidence interval for ρ lies entirely below 0.10, stop scraping and report the null result. Otherwise, continue to the full roster without examining any other statistic. No other interim looks are planned.

**10% look.** At approximately 10% of the roster scraped (~150 users), report descriptive statistics only: match rate, coverage, mean CLV, share ROI > 0, accuracy by window. No hypothesis tests, no stopping rule, no threshold changes.

## Other

### Known limitations

1. **Survivorship bias in roster.** The roster is selected on tier as of August 2026, which reflects test-window performance. Whole-roster statistics versus the null are biased upward. H1 and H2 compare users selected under the same rule against each other and are the primary tests for that reason.

2. **Participation rule.** The ≥ 118 pick requirement and event-leaderboard activity filter exclude selective pickers. Results generalise only to high-participation Platinum+ users.

3. **Best-line benchmark.** The test window uses 5 sportsbooks; older rank-window cards have up to 6. Overlap checks show differences ≤ 12 American odds points. BetMGM and DraftKings columns exist on BFO pages but carry no odds in the test window.

4. **One-year sample.** Individual-level skill is not identifiable (SE ≈ 2 percentage points of CLV per user over ~500 picks). All inference is at the panel level (cross-sectional persistence of CLV across users).

5. **Exploratory analyses.** Any analysis not specified above will be labelled as exploratory.

### Pilot results (not part of inferential tests)

**Ezoteryka** (Platinum, rank 1,242): 535 picks. Rank CLV = +0.040, test CLV = +0.025. Overall ROI = +4.6% (resampling p = 0.042). Test ROI = +2.5% (p = 0.237).

**The Cilantro Guy** (Legend, rank 1): 522 picks. Rank CLV = +0.035, test CLV = +0.092. Overall ROI = +8.4% (resampling p = 0.002). Test ROI = +16.2% (p = 0.0002).

### Code and data manifest

All analysis code and frozen data files are in the git repository at C:\Research\ufc\odds\, commit b2f036abc8702c4142f112b7aaa39faa72a4a177. See prereg_manifest.json for file checksums.
