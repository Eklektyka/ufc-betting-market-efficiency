# Cross-Venue Convergence Backtest — Kalshi ↔ Polymarket, UFC

## Verdict: STRATEGY-DEAD

The cross-venue gap converges (gross +0.5% on Polymarket at 0-tick), but
trading friction exceeds the edge at any realistic spread assumption.

## Primary cell (B=Polymarket, pooled tiers)

| Spread | n | ROI | 95% CI | Cap $/yr |
|---|---|---|---|---|
| 0-tick (gross) | 97 | +0.5% | [+0.2, +1.0] | $163 |
| 2-tick RT | 97 | −3.7% | [−4.2, −3.1] | −$1,258 |
| Roll estimate | 97 | −5.7% | [−6.4, −5.1] | −$1,968 |

CI>0 under both spread scenarios: **NO** (only at 0-tick)
Capacity ≥$100/yr: only at 0-tick ($163/yr)
LOCO (0-tick): [+0.4%, +0.6%] — stable, no card drives it

## Secondary cell (B=Kalshi)

| Spread | n | ROI | 95% CI |
|---|---|---|---|
| 0-tick | 237 | −4.9% | [−5.6, −4.1] |
| 2-tick | 237 | −8.6% | [−9.6, −7.7] |

Kalshi's per-side fee (7%·P·(1−P)) kills the strategy even at 0-tick spread.

## Attrition

782 events → 334 after ≥3-trades guard → 97 PM / 237 Kalshi entries.
All events in 2026_collector era (panel coverage limitation).
Median convergence time: 60 min (PM), 135 min (Kalshi).

## Gate

−30m gap (K−PM): mean=+0.4¢, SD=2.1¢. Unimodal, centred near zero. PASS.

## Sanity note

Step 0 gap-closure did not reproduce the paper's 32-min main-event median
(got 195 min). Tier assignment is heuristic and differs from the paper's
frozen crosswalk. Does not affect the verdict — strategy fails uniformly.

## Metric Reconciliation (Step 0-Final)

Step 0 first-pass failure resolved: metric mismatch (M1 vs M2), not
measurement error. The first-pass "195 min" used a wrong tier heuristic
(card position instead of top-decile combined volume), mixing the 32-min
and 118-min populations.

### Machinery certified against paper definition

Paper's gap-closure (M1) reproduced inside the backtest data loaders:
- Main event: **32 min** [10, 90] (paper: 32 [10, 80]) — **PASS**
- Undercard: **118 min** [75, 200] (paper: 118 [82, 175]) — **PASS**

Same code logic, same thresholds (5¢ open, 2¢ close), same tier definition
(top-decile combined volume, 32 main events), same panel data.

### Three-metric table

| Metric | Close criterion | Main | Undercard | Why |
|---|---|---|---|---|
| M1 (paper) | ≤2¢ | 32 min | 118 min | Loosest close → fastest |
| M2 (full convergence) | ≤1¢ | 60 min | 280 min | Tightest close → slowest |
| M3 (trade sim) | ≤1¢ or T−30m cap | ~60 min (cens.) | ~60 min (cens.) | Cap truncates long tails |

M1 < M2 is mechanical (tighter threshold = longer). M3 ≤ M2 (cap truncates).
The ordering M1 < M3 < M2 is coherent for main events; for undercard, M3 < M1
because the T−30m cap fires before most 118-min episodes would naturally close.

## VERDICT CONFIRMED: STRATEGY-DEAD

Primary cell (B=Polymarket, pooled): −3.7% [−4.2, −3.1] at 2-tick spread.
Kill mechanism = spread cost at entry, independent of convergence clock.

### Certified knowledge residue

- Cross-venue gap converges: gross +0.5% [+0.2, +1.0], n=97 PM entries
- Paper gap-closure: 32 min main / 118 min undercard (reproduced exactly)
- Full convergence (≤1¢): 60 min main / 280 min undercard
- Event attrition: 782 events → 334 guarded → 97 PM filled
- $100/yr capacity trigger: not fired (max $163/yr at 0-tick, negative at 2-tick)
