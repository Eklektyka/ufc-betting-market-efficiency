# Pre-Registration: Ethnic-Russian Sentiment Effect in MMA Betting Markets

**Date:** 2 September 2026
**Authors:** [Authors]
**Status:** Forward test, registered prior to accumulating confirmatory sample

---

## Hypothesis

Following the Russian invasion of Ukraine (24 February 2022), ethnic-Russian UFC fighters are systematically underpriced by the closing betting line, consistent with sentiment-driven neglect by a predominantly Western betting public. This effect is:

1. **Specific to ethnic Russians**, not Caucasus-origin fighters (Dagestan, Chechnya) from the same federation.
2. **Present in both existing roster fighters** (within-fighter fixed effect) **and new entrants** of normal quality (not positively selected by visa barriers).
3. **Persistent** through at least late 2025, not a transient spike.

## Frozen Forward Test

### Population
All UFC bouts involving at least one ethnic-Russian fighter (as classified by Wikidata nationality = Russia, birthplace outside the North Caucasus region, lat 41-45 / lon 43-49), from 1 January 2026 onward.

### Primary outcome
Market-adjusted excess win rate: actual win rate minus BFO de-vigged closing-line implied probability.

### Test specification
1. **Primary test:** Ethnic-Russian excess > 0 in the forward window (one-sided, alpha = 0.05), with fight-clustered bootstrap CI (2000 resamples, seed 67).
2. **Placebo:** Caucasus-origin fighter excess in the same window. The prediction is that Caucasus excess is zero or negative (no sentiment effect).
3. **Within-fighter:** Among ethnic Russians who fought both before and after Feb 2022, the post-war excess exceeds the pre-war excess (within-fighter swing > 0).

### Success criteria
- **Confirmed:** Ethnic-Russian excess > 0 with 95% CI excluding zero on N >= 60 post-war fights, AND Caucasus excess CI includes zero in the same window.
- **Partially confirmed:** Ethnic-Russian excess > 0 but CI includes zero; directionally consistent with prior estimate.
- **Falsified:** Ethnic-Russian excess <= 0, OR Caucasus shows equal or greater excess (indicating an era effect, not Russian-specific sentiment).

### Sample size target
Approximately 60+ ethnic-Russian post-war fights are needed for 80% power to detect a 10pp excess at alpha = 0.05. At current UFC scheduling rates (~8 ethnic-Russian fights per year), this target should be reached by late 2027.

### Data sources
- **Odds:** BestFightOdds.com closing lines, de-vigged using the Shin (1993) method.
- **Outcomes:** UFCStats.com official results.
- **Fighter origin:** Wikidata (property P27: country of citizenship; property P19: place of birth for Caucasus/ethnic-Russian classification).

### Analysis code
All code is frozen in this repository at the time of registration. The forward test will use the same classification and bootstrap procedures.

### Current evidence (as of registration)
- **Post-war ethnic-Russian excess:** +18.1pp (N=35 fights, 2022-2025). CI includes zero on this sample alone.
- **Caucasus placebo:** -15.6pp swing (opposite direction). Within-fighter DiD: +47.8pp [+3.9, +99.7], significant.
- **Within-fighter (5 fighters):** +11.8pp swing, directionally positive, CI includes zero.
- **Entrant quality:** Russian post-2022 entrants are priced at 52% (below non-Russian 56%), with 59% as underdogs. Not positively selected.
- **Interpretation:** Structural pattern supports sentiment over selection. Magnitude uncertain due to small N.

---

*This pre-registration is filed as part of "Efficient Markets, Behavioral Seams: Evidence from MMA Betting" and will be evaluated when the cumulative post-war ethnic-Russian fight count reaches N=60.*
