# MMA Efficiency Paper — closed 2026-09-02

**Question:** Are UFC closing lines informationally efficient against public
fighter fundamentals, and does the 2022 Russian invasion create a
sentiment-driven exception?

**What I expected:** Pre-registration (paper/preregistration.md, filed
2 September 2026): "Ethnic-Russian excess > 0 with 95% CI excluding zero on
N >= 60 post-war fights, AND Caucasus excess CI includes zero in the same
window." Success criteria defined for confirmed, partially confirmed, and
falsified outcomes.

**What I found:**

Efficiency half — confirmed null:
- Market Brier score = 0.1971 (test 2024–2025, N=639). No model beats it.
  Best challenger (SAPM): 0.2443. LightGBM ceiling: 0.2430.
  (`paper/manuscript.md` line 61 — manuscript excluded from repo)

War-shock half — retracted:
- In-sample DiD: +18.1 pp (N=35, 2022–2025). Within-fighter: +47.8 pp
  [+3.9, +99.7]. Caucasus placebo: −15.6 pp.
  (`paper/preregistration.md` "Current evidence" section)
- **Retracted:** The original effect was a look-ahead artefact of Wikidata
  origin coding. Wikidata nationality fields reflect present-day citizenship,
  not citizenship at fight time. Fighters coded as "Russian" post-2022 may
  have been assigned that nationality retroactively. The effect cannot be
  cleanly attributed to post-invasion sentiment.

**Why I stopped:** The efficiency result is a clean null — closing lines are
sufficient statistics for public fundamentals. The war-shock result, the only
candidate exception, was retracted after discovering the Wikidata look-ahead
artefact. The pre-registration for a forward test exists but the forward test
is not planned (no data collection is set up and N = 60 would require ~2027).

**What it rules out:** UFC closing lines are efficient against age, travel
distance, women's favourite bias, fight-style fundamentals, and nationality
effects (all null on 2007–2025 data with temporal validation). The war-shock
finding, if real, is below the detection threshold of this sample.

**What would reopen it:** Nothing — closed. The pre-registration is on file
but the forward test is not actively planned. A researcher with access to
point-in-time nationality data (not Wikidata) could attempt the war-shock
test properly.
