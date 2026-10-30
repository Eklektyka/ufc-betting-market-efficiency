# Pass 2 — BFO Intraday Book Line vs PM

## Status: IN PROGRESS (pull running, analysis queued)

## Killed (Amendment 4)

The following are **not computed** due to 6–54h capture latency in the BFO
chart-XHR data:

- Event study (consensus ≥2¢ moves → PM response curve)
- Pre-drift classifier (BOOK-LED / BOOK-FOLLOWS-PM / CONTESTED) as primary
- A1/A2a/A2b verdict semantics
- Any minutes-scale lead-lag claim

**One-line finding:** Mechanism unidentifiable at 6–54h capture latency;
pass 1 = upper bound (look-ahead via book close), pass 2 = lower bound
(staleness of book signal at entry); truth bracketed.

## Capture-Mode Diagnostics (Amendment 3)

### (a) Duplicate-y rate
1–6% across books. Consistent with change-of-value storage with
occasional re-polls at the same price. Not a data quality problem.

### (b) Estimated polling cadence (median inter-point delta)

| Book | Median delta | Estimated cadence |
|---|---|---|
| DraftKings | 360 min (6h) | Densest |
| Unibet | 705 min (12h) | |
| FanDuel | 840 min (14h) | |
| Caesars | 1080 min (18h) | |
| BetRivers | 1800 min (30h) | |
| BetWay | 3240 min (54h) | Sparsest |

Cross-book timestamp collision rate: 14.8% (<60s tolerance). Independent
feeds or staggered polling, not batch.

### (c) Capture density drift

**DraftKings drives density.** ~20–25 pts/fighter in May–Jun 2025, drops
to 0–4 by Jul–Aug 2025 (DK absent from some events). Other books stable
at 2–10 pts/fighter throughout.

Linear trend: −0.63 pts/fighter/day. Any era-split claim must condition
on this.

### Reconciliation
- The 1,115-pt event (2025-05-11) is a full-card main event with 18
  fighters × 5 books including dense DraftKings. Not an outlier — the
  May events consistently have ~60 pts/fighter.
- The ~10 pts/fighter July events reflect DraftKings dropping out.
- May–Jul 2025 predates the forecaster-study window (Aug 16 2025) but
  is in the PM panel (starts May 2025). Not a mislabel.

## New Primary — Implementable-Feed Backtest

### Signal
- **(a) Primary:** DraftKings-only devigged last value. Densest feed
  (~3h median staleness when present). Available May–Aug 2025, spotty
  after.
- **(b) Sensitivity:** Freshest-across-books devigged value (lowest
  signal_age at entry across all real books).

### Entry
PM price < signal − 2¢ (either fighter via complement). Fill =
min($200, trailing-1h PM volume). ≥3-trades guard.

### Spread scenarios
- (ii) 2-tick each way
- (iii) Per-fight Roll effective-spread estimate (floor 1 tick;
  window −6h→−30m; logged per fight)

### Fees
- Kalshi: 0.07·P·(1−P) per side, entry and exit
- Polymarket: 0 taker fee

### Horizons
−48h, −24h, −6h, −2h, −1h, −30m (anchor = Kalshi close_time − 60 min)

### Inference
Fight-clustered bootstrap, 1,000 draws, seed 42. Leave-one-card-out.
Capacity line = n_entries/yr × mean_fill × net_ROI.

### Era
Early (May–Jun 2025, DK present) / late (Jul 2025+, DK sparse) split
reported **descriptively only** with capture-density covariate note.
No decay claims.

### Classifier sensitivity (Amendment 3)
If the BOOK-LED / BOOK-FOLLOWS-PM classifier is reported at all, the
pre-drift window = max(30 min, 2× estimated cadence for the books in
that event's consensus). A2b share under both windows; if
cadence-sensitive, verdict language = "unresolved: PM speed vs capture
latency."

## Verdict (pre-stated)

**STRATEGY-SIGNAL:** ROI CI>0 under BOTH spread scenarios (ii) and (iii)
at −48h or −24h (Kalshi), survives LOCO, capacity ≥ $150/yr, median
signal_age ≤ 12h on surviving rows. → Purchase trigger fires. Residual
adverse-selection risk noted as unmeasured.

**STRATEGY-DEAD:** ROI CI>0 fails under either spread scenario, or
capacity < $150/yr, or signal_age > 12h.

**DATA-DEAD:** Guards + staleness leave n too small for CIs. Report n at
each attrition step.

## Results (Amendment 4 backtest)

### Capture diagnostics (full 63-event sample)

| Book | Median cadence | Events present |
|---|---|---|
| BetMGM | 2 min | 19/63 (30%) |
| DraftKings | 360 min (6h) | ~35/63 |
| FanDuel | 614 min (10h) | ~60/63 |
| Caesars | 884 min (15h) | ~60/63 |

Density trend: −0.005 pts/fighter/day (no significant trend on full sample).
Cross-book collision rate: 4.0% — independent feeds.

### Backtest results

**DraftKings-only / BetMGM-only: DATA-DEAD.** Zero bets survived —
these books are absent from the panel-crosswalk intersection.

**Freshest-across-books:** No horizon × venue combination achieves
ROI CI>0. Median signal_age 78–533 min. Max capacity $93/yr.

### Verdict: STRATEGY-DEAD

Pre-stated criteria not met:
- ROI CI>0 at −48h or −24h (Kalshi): FAIL (CIs straddle zero)
- Capacity ≥ $150/yr: FAIL (max $93/yr)
- LOCO: N/A (no signal to test)

One-line: pass 1 (book close = look-ahead) showed +6–8% convergence ROI;
pass 2 (implementable signal with 5–9h staleness) shows ~0%.
The entire pass-1 edge was the information in the book's *final* move,
which is not observable at entry time.

"Mechanism unidentifiable at 6–54h capture latency; pass 1 = upper bound
(look-ahead), pass 2 = lower bound (staleness); truth bracketed."
