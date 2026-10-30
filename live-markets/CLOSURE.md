# UFC Live-Market Studies — closed October 2026

**Question:** Do Kalshi/Polymarket UFC live fight markets exhibit exploitable
post-jump drift, round-break patterns, or method prop mispricings?

**What I expected:** Not recorded (exploratory programme, no pre-registration).

**What I found:** All four sub-studies are dead.

1. **In-fight drift:** Post-jump reversal at best horizon (5 min) = 0.81¢
   gross; minimum round-trip = 2¢ (PM zero-fee era). Net negative at every
   horizon and venue. 272 fights, 24,608 jumps. Verdict: "No tradeable edge
   exists in post-jump in-fight drift."
   (`qa/infight_drift.md` line 158)

2. **Live patterns:** Permutation-adjusted min-p: PM 0.226, Kalshi 0.272.
   No specification survives multiple-testing correction. Both strategy
   sketches negative P&L (−1.7¢ and −2.8¢/trade). Verdict: "No tradeable
   edge."
   (`qa/live_patterns.md` line 157)

3. **Method props v2:** Fighter-KO sell-initiated P&L +1.93¢/contract,
   CI [+0.98¢, +3.17¢] — statistically significant. But capacity = ~$13/year
   on median volume. BFO prop benchmark deferred (no prop odds file available).
   (`qa/method_props_v2.md` line 195)

4. **Per-round scrape (infrastructure):** 8,758 fights, 41,186 round rows,
   0 parse errors. Gate A→B passed. Data served downstream studies.
   (`qa/perround_scrape.md` line 62)

**Why I stopped:** Sub-studies 1–2 are unambiguously dead (sub-fee or
permutation-killed). Sub-study 3 is statistically real but capacity-dead —
$13/year does not justify the infrastructure. Sub-study 4 is complete data
infrastructure that already served its purpose.

**What it rules out:** Post-event drift in UFC live markets is not tradeable
at retail. Round-break patterns do not survive correction. Method prop
mispricings exist but at de minimis capacity.

**What would reopen it:** A venue with zero fees and significantly higher
UFC live volume. Current Kalshi + Polymarket combined volume is insufficient
for any of the identified signals.
