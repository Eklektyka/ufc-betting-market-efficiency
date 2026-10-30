# In-Fight Post-Jump Drift Study (UFC, Kalshi + Polymarket)

Generated: 2026-10-11 04:30 UTC
Runtime: 0.8m

> **Caveat**: No orderbook data. All fills are UPPER BOUNDS on executable
> size — true capacity is likely smaller.

## Step 0 — Coverage Gate

In-fight window := (close\_time − 60 min, last trade]

| Threshold | Kalshi | PM | Either |
|-----------|--------|----|--------|
| ≥20 in-fight trades | 265 | 265 | 272 |

**GATE PASSED**: 272 fights (need ≥80).

### Coverage detail (top 20 by Kalshi trade count)

| fight_id | K trades | K vol | PM trades | PM vol |
|----------|----------|-------|-----------|--------|
| 20260614_TOPGAE | 296811 | 50739968 | 3500 | 1638144 |
| 20260711_MCGHOL | 232464 | 49994936 | 2932 | 2778025 |
| 20260509_CHISTR | 154694 | 27699332 | 3500 | 3188924 |
| 20260614_PERGAN | 120272 | 19168760 | 3424 | 1907570 |
| 20260614_HOKLEW | 119589 | 12826153 | 1965 | 931662 |
| 20260711_SAIPIM | 117661 | 13797372 | 1520 | 1520768 |
| 20260711_SANBAU | 100541 | 7984191 | 1651 | 495488 |
| 20260711_ROYKAV | 86147 | 6335066 | 1401 | 385253 |
| 20260614_RUFCHA | 84633 | 9236167 | 1745 | 967580 |
| 20260509_VANTAI | 77975 | 9860631 | 2714 | 1303985 |
| 20260614_OMAZAH | 75015 | 8834503 | 1558 | 329249 |
| 20260614_LOPGAR | 66980 | 6039016 | 2297 | 1632350 |
| 20260614_NICDAU | 56433 | 5987623 | 1320 | 593781 |
| 20260711_KRYWHI | 50348 | 4116623 | 1183 | 628917 |
| 20260509_VOLCOR | 38897 | 3752991 | 1782 | 523055 |
| 20260509_BRABUC | 33494 | 3543288 | 1628 | 1074255 |
| 20260711_STEELL | 28815 | 3610204 | 537 | 520557 |
| 20260606_MUHBON | 25935 | 3476626 | 1277 | 1031514 |
| 20260711_CORWAN | 25516 | 1952435 | 648 | 255392 |
| 20260711_BASGAR | 24948 | 1564301 | 576 | 146760 |

## Fee Schedules

**Kalshi taker fee**: 0.07 × P × (1−P) per side. Round-trip = 2 × 0.07 × P × (1−P).

**Polymarket taker fee** (verified Oct 2026):
- 2025: 0% (no fees)
- Mar–Jun 2026: 3% → 0.03 × P × (1−P) per share
- Jul 2026+: 5% → 0.05 × P × (1−P) per share
- Maker rebate: 15% of taker fees

## Step 1 — Jumps

Jump := |Δ last price| ≥ 5¢ within ≤ 15s, same market.
First 2 min after in-fight window start excluded.
One ticker per Kalshi fight (avoid mirror double-count).

| Venue | Jumps | Fights |
|-------|-------|--------|
| Kalshi | 6592 | 257 |
| PM | 18016 | 244 |
| **Total** | **24608** | **259** |

Jump size: mean=0.319, median=0.210, max=0.998

## Step 2 — Drift (all jumps)

| Horizon | Mean | Median | 95% CI | N |
|---------|------|--------|--------|---|
| 10s | -0.0031 | 0.0000 | [-0.0068, 0.0006] | 22492 |
| 30s | -0.0043 | 0.0000 | [-0.0082, -0.0008] | 24253 |
| 60s | -0.0036 | -0.0000 | [-0.0073, 0.0000] | 24505 |
| 3m | -0.0026 | 0.0000 | [-0.0066, 0.0015] | 24597 |
| 5m | -0.0041 | 0.0000 | [-0.0085, 0.0002] | 24603 |

## Step 3 — Finish vs Non-Finish Split

Finish-sequence jumps (resolution within 5 min): 8533
Non-finish jumps: 16075

### Finish (uncapturable)

| Horizon | Mean | Median | 95% CI | N |
|---------|------|--------|--------|---|
| 10s | 0.0016 | -0.0000 | [-0.0064, 0.0092] | 7976 |
| 30s | -0.0004 | 0.0000 | [-0.0069, 0.0061] | 8433 |
| 60s | 0.0012 | 0.0000 | [-0.0061, 0.0086] | 8510 |
| 3m | 0.0059 | -0.0000 | [-0.0024, 0.0138] | 8532 |
| 5m | 0.0035 | 0.0019 | [-0.0047, 0.0116] | 8533 |

### Non-finish (tradeable)

| Horizon | Mean | Median | 95% CI | N |
|---------|------|--------|--------|---|
| 10s | -0.0056 | 0.0000 | [-0.0094, -0.0018] | 14516 |
| 30s | -0.0063 | 0.0000 | [-0.0107, -0.0024] | 15820 |
| 60s | -0.0061 | 0.0000 | [-0.0106, -0.0017] | 15995 |
| 3m | -0.0071 | 0.0000 | [-0.0113, -0.0030] | 16065 |
| 5m | -0.0081 | -0.0000 | [-0.0125, -0.0037] | 16070 |

## Step 4 — Net of Costs

**Roll effective spread**: The Roll (1984) estimator measures sqrt(−autocovariance of price
changes). In-fight UFC markets are highly volatile, so the autocovariance is dominated by
mean-reverting price swings, NOT bid-ask bounce. The raw estimates (Kalshi: 21.1¢, PM: 13.1¢)
are unusable — they measure volatility, not spread. We instead use:

- **Kalshi effective spread**: 1¢ (tick size), consistent with typical 1¢ inside spread
  on liquid KXUFCFIGHT markets.
- **PM effective spread**: 1¢ (CLOB minimum tick on Polymarket sports).

Round-trip cost at median entry price (p ≈ 0.45):

| Venue | Taker fee RT | Spread RT | Total RT |
|-------|-------------|-----------|----------|
| Kalshi | 2 × 0.07 × 0.45 × 0.55 = 3.47¢ | 2 × 1¢ = 2¢ | 5.47¢ |
| PM (2025, 0% fee) | 0¢ | 2¢ | 2.00¢ |
| PM (2026 Jul+, 5%) | 2 × 0.05 × 0.45 × 0.55 = 2.48¢ | 2¢ | 4.48¢ |

### Non-finish net drift (direction = FADE the jump)

The non-finish gross drift is *negative* (price reverts). A fade trade
(sell after up-jump, buy after down-jump) would earn the reversal. But:

| Horizon | Gross reversal | − Kalshi RT | − PM RT (2025) |
|---------|---------------|-------------|----------------|
| 10s | 0.56¢ | −4.91¢ | −1.44¢ |
| 30s | 0.63¢ | −4.84¢ | −1.37¢ |
| 60s | 0.61¢ | −4.86¢ | −1.39¢ |
| 3m | 0.71¢ | −4.76¢ | −1.29¢ |
| 5m | 0.81¢ | −4.66¢ | −1.19¢ |

Even on zero-fee PM (2025), net reversal is **negative at all horizons**.
On Kalshi or fee-era PM the loss widens further.

## Step 5 — Capacity

Fill cap (volume in 60s after each non-finish jump):
- Mean: 13,954 contracts
- Median: 4,135 contracts

Capacity is moot: there is no positive net drift to scale.

---

## Verdict

**Non-finish split** — gross drift at 30s: −0.63¢ (CI [−1.07¢, −0.24¢], significantly
negative), 60s: −0.61¢ (CI [−1.05¢, −0.19¢]). Price REVERTS after in-fight jumps,
consistent with the prior Track B OFI reversal (−1.13¢). The reversal is
real but sub-fee: at best 0.81¢ of mean reversion at 5 min, vs 2¢ minimum
round-trip spread and 0–3.5¢ taker fee, yielding a negative net at every
horizon and on every venue. The finish-sequence split (8,533 jumps) shows
zero drift (CI straddles zero at all horizons), confirming that the modest
all-sample reversal is an artefact of non-finish flow, not finish-sequence
continuation. **No tradeable edge exists in post-jump in-fight drift.**

Runtime: 1.3m (Lychee scan cached; 272 fights, 24,608 jumps, 5,000-draw bootstrap).