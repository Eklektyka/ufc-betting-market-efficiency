# UFC Betting Market Efficiency

Five studies testing whether UFC betting and prediction markets are
informationally efficient. One signal (chin durability) is statistically
significant in-sample but not exploitable out of sample; everything else
is null.

**Status:** Closed. See [FINDINGS.md](FINDINGS.md) for the ledger.

---

## Projects

### 1. Line Movement (Path to Efficiency) — Closed — null

Does open-to-close line movement carry information beyond the closing line?

- **Panel:** 8,112 fighter-fight observations (BFO odds, 2007–2026)
- **Result:** Movement is informative at the open (coef = +1.039, p < 0.0001)
  but fully impounded at close (coef = +0.038, p = 0.545). Revision magnitude
  cannot reject H0 = 1 (efficient). Markets are efficient with respect to
  their own revisions.
- **Pre-registered:** Yes ([`line-movement/docs/PRE_REGISTRATION.md`](line-movement/docs/PRE_REGISTRATION.md))
- **Code:** [`line-movement/code/`](line-movement/code/)
- **Results:** [`line-movement/results/`](line-movement/results/)
- **Closure:** [`line-movement/CLOSURE.md`](line-movement/CLOSURE.md)

### 2. Chin Durability (Highlight Bias) — Closed — null for P&L

Do markets misprice fighters based on opponent chin vulnerability (sapm_r_opp)?

- **Panel:** 5,234 fighter-fights (BFO + UFCStats, 2008–2026)
- **Result:** Statistically significant in-sample: Romano-Wolf p = 0.0001,
  288/288 specification-curve specs positive, OOS coefficient excludes zero
  ([`chin-durability/RESEARCH_NOTES.md`](chin-durability/RESEARCH_NOTES.md) lines 107, 130).
  But not exploitable out of sample: top-decile OOS +5.56 pp gross, +3.56 pp
  net, 95% CI [−6.79, +18.54] — crosses zero (same file, line 138).
- **Pre-registered:** No (post-hoc; acknowledged in notes)
- **Code:** [`chin-durability/code/`](chin-durability/code/), [`chin-durability/bfo_analysis/`](chin-durability/bfo_analysis/)
- **Notes:** [`chin-durability/RESEARCH_NOTES.md`](chin-durability/RESEARCH_NOTES.md)
- **Closure:** [`chin-durability/CLOSURE.md`](chin-durability/CLOSURE.md)

### 3. CLV Forecasters — Closed — null (futility)

Do public Tapology users who beat the closing line persist out of sample?

- **Sample:** 374 qualified users (of 1,447 scraped); early-terminated at 27%
- **Result:** No skill persistence. rho = −0.0024, CI [−0.147, +0.143].
  Futility rule triggered.
- **Pre-registered:** Yes ([`clv-forecasters/osf_prereg.md`](clv-forecasters/osf_prereg.md))
- **Code:** [`clv-forecasters/code/`](clv-forecasters/code/)
- **Results:** [`clv-forecasters/RESULTS.md`](clv-forecasters/RESULTS.md)
- **Closure:** [`clv-forecasters/CLOSURE.md`](clv-forecasters/CLOSURE.md)

### 4. MMA Market Efficiency Replication — Closed — null

Are UFC closing lines efficient against public fighter fundamentals?

- **Sample:** 4,633 bouts (BFO + UFCStats, 2007–2025)
- **Result:** Market Brier = 0.1971 (test N=639); no model beats it. Closing
  line is a near-sufficient statistic for public fundamentals
  ([`mma-replication/CLOSURE.md`](mma-replication/CLOSURE.md)).
- **Pre-registered:** Forward test registered 2 Sept 2026
  ([`mma-replication/paper/preregistration.md`](mma-replication/paper/preregistration.md)); not actively planned
- **Code:** [`mma-replication/analysis/`](mma-replication/analysis/)
- **Closure:** [`mma-replication/CLOSURE.md`](mma-replication/CLOSURE.md)

### 5. UFC Live-Market Studies — Closed — all dead

Do Kalshi/Polymarket UFC live fight markets exhibit exploitable patterns?

- **In-fight drift:** Post-jump reversal 0.81¢ gross, sub-fee. Null
  ([`live-markets/infight_drift.md`](live-markets/infight_drift.md)).
- **Live patterns:** No spec survives permutation correction. Null
  ([`live-markets/live_patterns.md`](live-markets/live_patterns.md)).
- **Method props:** KO-seller +1.93¢/c significant but capacity ~$13/yr. Dead
  ([`live-markets/method_props_v2.md`](live-markets/method_props_v2.md)).
- **Per-round scrape:** 8,758 fights, 41,186 round rows. Infrastructure only
  ([`live-markets/perround_scrape.md`](live-markets/perround_scrape.md)).
- **Closure:** [`live-markets/CLOSURE.md`](live-markets/CLOSURE.md)

*Note:* A KO-effect study (Glicko-2 / staggered DiD) was designed but never
run; no standalone output was produced.

---

## What went wrong along the way

The MMA efficiency paper's war-shock finding is the most instructive failure. The original DiD showed a +18.1 pp excess for ethnic-Russian fighters post-invasion — statistically significant against a Caucasus placebo. The effect was a look-ahead artefact: Wikidata's nationality field reflects popularity, so better performing fighters have a higher chance of getting a Wikipedia article.

---

## Data

Raw data (BFO odds, UFCStats, Tapology picks) are not distributed. The code
documents all data sources and scraping procedures. Panels are rebuildable
from public sources.

## Reproduce

Each subfolder's pipeline is documented in its docs/ or CLOSURE.md. All
studies require BFO closing odds (scraped from bestfightodds.com) and UFCStats
fight outcomes (scraped from ufcstats.com).

## License

Code: [MIT](LICENSE). Text and figures: [CC BY 4.0](LICENSE).
