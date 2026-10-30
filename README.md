# UFC Betting Market Efficiency

Six studies testing whether UFC betting and prediction markets are
informationally efficient. All but one produced null or economically
unexploitable results.

**Status:** Closed. See [FINDINGS.md](FINDINGS.md) for the ledger.

---

## Projects

### 1. Line Movement (Path to Efficiency) — Closed, null

Does open-to-close line movement carry information beyond the closing line?

- **Panel:** 8,112 fighter-fight observations (BFO odds, 2007–2026)
- **Result:** Movement is informative at the open (coef = +1.039, p < 0.0001)
  but fully impounded at close (coef = +0.038, p = 0.545). Revision magnitude
  cannot reject H0 = 1 (efficient). Markets are efficient with respect to
  their own revisions.
- **Pre-registered:** Yes (`line-movement/docs/PRE_REGISTRATION.md`)
- **Code:** `line-movement/code/`
- **Results:** `line-movement/results/`

### 2. Chin Durability (Highlight Bias) — Closed, null for P&L

Do markets misprice fighters based on opponent chin vulnerability (sapm_r_opp)?

- **Panel:** 5,234 fighter-fights (BFO + UFCStats, 2008–2026)
- **Result:** Statistically robust signal (RW p = 0.0001, 288/288 specs
  positive, OOS coef excludes zero). But P&L CI crosses zero: top-decile OOS
  +5.56 pp gross, +3.56 pp net, 95% CI [−6.79, +18.54]. Cannot confirm
  economic significance.
- **Pre-registered:** No (post-hoc; acknowledged in notes)
- **Code:** `chin-durability/code/`, `chin-durability/bfo_analysis/`
- **Notes:** `chin-durability/RESEARCH_NOTES.md`

### 3. CLV Forecasters — Closed, null (futility)

Do public Tapology users who beat the closing line persist out of sample?

- **Sample:** 374 qualified users (of 1,447 scraped); early-terminated at 27%
- **Result:** No skill persistence. rho = −0.0024, CI [−0.147, +0.143].
  Futility rule triggered.
- **Pre-registered:** Yes (`clv-forecasters/osf_prereg.md`)
- **Code:** `clv-forecasters/code/`
- **Results:** `clv-forecasters/RESULTS.md`

### 4. MMA Market Efficiency Replication — Closed, null

Are UFC closing lines efficient against public fighter fundamentals? Does the
2022 Russian invasion create a sentiment exception?

- **Sample:** 4,633 bouts (BFO + UFCStats, 2007–2025)
- **Result:** Market Brier = 0.1971 (test N=639); no model beats it. Closing
  line is a near-sufficient statistic. War-shock DiD (+18.1 pp, N=35)
  **retracted** — Wikidata look-ahead artefact (present-day nationality coding,
  not point-in-time).
- **Pre-registered:** Forward test registered 2 Sept 2026
  (`mma-replication/paper/preregistration.md`); test not actively planned
- **Code:** `mma-replication/analysis/`

### 5. UFC Live-Market Studies — Closed, all dead

Do Kalshi/Polymarket UFC live fight markets exhibit exploitable patterns?

- **In-fight drift:** Post-jump reversal 0.81c gross, sub-fee. Null.
- **Live patterns:** No spec survives permutation correction. Null.
- **Method props:** KO-seller +1.93c significant but capacity ~$13/yr. Dead.
- **Per-round scrape:** 8,758 fights, 41,186 round rows. Infrastructure only.
- **Reports:** `live-markets/`

### 6. KO-Effect Study — Designed, not run

Glicko-2 / staggered DiD approach to knockout effects. No standalone output
was produced; code fragments exist in other projects.

---

## What went wrong along the way

The MMA efficiency paper's war-shock finding is the most instructive failure.
The original DiD showed a +18.1 pp excess for ethnic-Russian fighters
post-invasion — statistically significant against a Caucasus placebo. The
effect was a look-ahead artefact: Wikidata's nationality field reflects
popularity, so better performing fighters have a higher chance of getting a Wikipedia article.

---

## Data

Raw data (BFO odds, UFCStats, Tapology picks) are not distributed. The code
documents all data sources and scraping procedures. Panels are rebuildable
from public sources.

## Reproduce

Each subfolder's pipeline is documented in its docs/ or CLOSURE.md. All
studies require BFO closing odds (scraped from bestfightodds.com) and UFCStats
fight outcomes (scraped from ufcstats.com).

## Licence

Code: [MIT](LICENSE). Text and figures: [CC BY 4.0](LICENSE).
