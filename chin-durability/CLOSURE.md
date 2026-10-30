# Highlight Bias (sapm_r_opp) — closed 2026-07-07

**Question:** Do UFC betting markets systematically misprice fighters based on
opponent chin vulnerability (significant strikes absorbed per minute, opponent)?

**What I expected:** Not recorded. No formal pre-registration predates the
analysis. RESEARCH_NOTES.md §9 (lines 287–292): "No formal pre-registration
predates the analysis. The theoretical hypothesis preceded the data analysis,
but the specific operationalisation (sapm_r_opp) was confirmed through
exploration of a 41-variable family."

**What I found:** Statistical signal is robust but economically unexploitable.

- Full-sample OLS: sapm_r_opp coef = +0.01248 (SE 0.00288, p < 0.001).
  (`RESEARCH_NOTES.md` line 87)

- OOS (2020–2026, N=2,556): coef +0.00997 (p = 0.012), CI excludes zero.
  (`RESEARCH_NOTES.md` lines 130–132)

- Romano-Wolf family-adjusted (5-var family): RW p = 0.0001, rank 1 of 41
  candidates. (`RESEARCH_NOTES.md` line 107)

- Specification curve (288 specs): 100% positive, 100% significant.
  (`RESEARCH_NOTES.md` lines 95–97)

- Permutation test: 12.8σ above null.
  (`RESEARCH_NOTES.md` line 74)

- Top-decile OOS strategy: +5.56 pp gross / +3.56 pp net; **95% CI
  [−6.79, +18.54] — crosses zero.** Bootstrap p = 0.362.
  (`RESEARCH_NOTES.md` lines 138–140)

**Why I stopped:** The P&L confidence interval crosses zero. The signal is
statistically real (it survives every robustness test thrown at it) but the
sample is too small to confirm a tradeable edge. At N=256 top-decile bets
over 6 years, the CI is wide. The signal may be real and too small to trade,
or real and tradeable but undetectable at this sample size. Either way, the
result is null for economic significance.

**What it rules out:** Not recorded — without a pre-registration, the
interpretation is post-hoc. What the data show: a robust statistical
association between opponent chin vulnerability and fight outcomes that is not
priced into closing lines, but whose P&L impact cannot be distinguished from
zero at this sample size.

**What would reopen it:** A pre-registered forward test on new data (post-2026
fights) with a specified minimum effect size for the P&L CI. Without
pre-registration, further analysis risks p-hacking the strategy parameters.
