# Findings Ledger

| # | Hypothesis / Strategy | Data | Verdict | Key Number | Source File | Bugs Caught |
|---|----------------------|------|---------|------------|-------------|-------------|
| 1 | Open-to-close line movement carries information beyond the closing line | BFO odds N=8,112 fighter-fights, 2007–2026 | **CLOSED — null** | coef(g_close ~ move) = +0.038, p = 0.545; movement fully impounded at close | `line-movement/results/phase04_close_efficiency.txt` line 8 | Mech C sign flip in OOS (pre-2020 +0.119, 2020+ −0.064): REJECT |
| 2 | Revision magnitude departs from H0 = 1 (efficient) | Same panel | **CLOSED — null** | t vs H0=1 = +0.606, p = 0.545; cannot reject efficient revision | `line-movement/results/phase07_magnitude_test.txt` line 13 | — |
| 3 | Markets misprice opponent chin vulnerability (sapm_r_opp) — economic significance | BFO + UFCStats N=5,234, 2008–2026 | **CLOSED — null for P&L** | Top-decile OOS: +5.56 pp gross, +3.56 pp net; CI [−6.79, +18.54] crosses zero | `chin-durability/RESEARCH_NOTES.md` line 138 | L1 Glicko full-timeline leak; L9 pipeline reconstruction |
| 4 | sapm_r_opp statistical signal | Same panel | **CLOSED — positive** | OOS coef +0.00997 (p = 0.012); RW p = 0.0001; 288/288 specs significant | `chin-durability/RESEARCH_NOTES.md` lines 107, 130 | — |
| 5 | Tapology Platinum+ users who beat the closing line persist OOS | BFO closes + Tapology picks, 374 users | **CLOSED — null (futility)** | ρ(rank CLV, test CLV) = −0.0024; CI [−0.147, +0.143] | `clv-forecasters/RESULTS.md` line 28 | v1/v2 scraper sign flip (ρ = +0.16 vs −0.09) |
| 6 | UFC closing lines are inefficient against public fundamentals | BFO + UFCStats 4,633 bouts, 2007–2025 | **CLOSED — null** | Market Brier = 0.1971 (N=639 test); no model beats it | `mma-replication/paper/preregistration.md` "Current evidence" | 7 East Asian name-order inversions |
| 7 | Post-2022 ethnic-Russian sentiment mispricing | Wikidata nationality + BFO, N=35 post-war | **CLOSED — retracted** | Original +18.1 pp; retracted (Wikidata look-ahead artefact) | `mma-replication/CLOSURE.md` | Wikidata origin coding is present-day, not point-in-time |
| 8 | KO-effect study (Glicko-2, staggered DiD) | — | **Designed, not run** | — | — | — |
| 9 | Post-jump in-fight drift | Kalshi + PM UFC live trades, 272 fights | **CLOSED — null** | Best reversal (5 min) = 0.81¢ gross; sub-fee | `live-markets/infight_drift.md` line 158 | — |
| 10 | Round-break live patterns | Same live data | **CLOSED — null** | Permutation min-p: PM 0.226, Kalshi 0.272 | `live-markets/live_patterns.md` line 157 | — |
| 11 | Method prop mispricings | PM + UFCStats, method prop trades | **CLOSED — capacity-dead** | KO-seller +1.93¢/c significant; capacity ~$13/yr | `live-markets/method_props_v2.md` line 195 | 29/634 PM–UFCStats resolution disagreements |
