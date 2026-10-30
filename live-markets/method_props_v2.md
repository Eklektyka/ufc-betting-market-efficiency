# Method Prop Audit — v2
Generated: 2026-10-12 19:09

> Audits qa/method_props.md findings. 7-point check.
> No orderbook data; fills are upper bounds on capacity.

Loaded: 496574 PM trades, 8539 ufcstats fights

Built 634 matched prop records
  gtd: 139
  ko_fight: 123
  ko_fighter: 260
  sub_fight: 112

## 1. Taker-Side Split & Three Price Measures

### GTD (n=130)
  Buy-initiated share: 79.6%, mean trades/market: 65
  Buyer P&L (gross):
    Last trade:          -0.02¢
    Last SELL-initiated: -0.05¢
    VWAP sell final 24h: +1.39¢

### KO fight-level (n=96)
  Buy-initiated share: 74.0%, mean trades/market: 50
  Buyer P&L (gross):
    Last trade:          -0.13¢
    Last SELL-initiated: -0.99¢
    VWAP sell final 24h: -0.40¢

### KO fighter-specific (n=223)
  Buy-initiated share: 87.8%, mean trades/market: 54
  Buyer P&L (gross):
    Last trade:          -0.30¢
    Last SELL-initiated: -1.93¢
    VWAP sell final 24h: -3.08¢

### SUB fight-level (n=85)
  Buy-initiated share: 82.6%, mean trades/market: 43
  Buyer P&L (gross):
    Last trade:          -0.24¢
    Last SELL-initiated: -1.65¢
    VWAP sell final 24h: -0.36¢

## 2. Pre-Fight Entry Price

Markets with pre-fight price (≥24h before last trade): 298/534

### GTD (n=82)
  Pre-fight gross P&L:  -3.43¢
  Last-trade gross P&L: -0.02¢
  Δ (pre-fight vs last): -3.41¢
  Mean pre-fight price: 0.449, mean last price: 0.415

### KO fight-level (n=51)
  Pre-fight gross P&L:  -7.01¢
  Last-trade gross P&L: -0.12¢
  Δ (pre-fight vs last): -6.89¢
  Mean pre-fight price: 0.462, mean last price: 0.393

### KO fighter-specific (n=129)
  Pre-fight gross P&L:  -9.99¢
  Last-trade gross P&L: -0.38¢
  Δ (pre-fight vs last): -9.62¢
  Mean pre-fight price: 0.348, mean last price: 0.252

### SUB fight-level (n=36)
  Pre-fight gross P&L:  -9.75¢
  Last-trade gross P&L: -0.19¢
  Δ (pre-fight vs last): -9.56¢
  Mean pre-fight price: 0.292, mean last price: 0.196

## 3. Fight-Clustered Bootstrap CIs

### GTD
  Markets: 130, fights: 128 (1.0 markets/fight)
  Gross P&L: -0.02¢, fight-clustered 95% CI: [-0.11¢, +0.05¢]
  → straddles zero

### KO fight-level
  Markets: 96, fights: 73 (1.3 markets/fight)
  Gross P&L: -0.13¢, fight-clustered 95% CI: [-0.22¢, -0.06¢]
  → SIGNIFICANT

### KO fighter-specific
  Markets: 223, fights: 139 (1.6 markets/fight)
  Gross P&L: -0.30¢, fight-clustered 95% CI: [-0.40¢, -0.20¢]
  → SIGNIFICANT

### SUB fight-level
  Markets: 85, fights: 82 (1.0 markets/fight)
  Gross P&L: -0.24¢, fight-clustered 95% CI: [-0.44¢, -0.07¢]
  → SIGNIFICANT

## 4. Resolution Verification (PM outcome vs UFCStats)

Markets with both PM and UFCStats resolution: 634
Disagreements: 29

| Slug | Type | PM | UFC | Method | Fighter |
|------|------|----|-----|--------|---------|
| ufc-ale7-cha15-2026-01-24-johnson-win-by-ko-tko | ko_fight | 0 | 1 | KO/TKO | None |
| ufc-der-wal2-2026-01-24-win-by-ko-tko | ko_fight | 1 | 0 | Decision - Unanimous | None |
| ufc-and28-ate-2026-01-24-pulyaev-win-by-ko-tko | ko_fight | 0 | 1 | KO/TKO | None |
| ufc-der-wal2-2026-01-24-cortes-acosta-win-by-ko-tk | ko_fight | 1 | 0 | Decision - Unanimous | None |
| ufc-nik2-mod-2026-01-24-bukauskas-win-by-ko-tko | ko_fight | 0 | 1 | KO/TKO | None |
| ufc-jos52-den11-2026-01-24-freeman-win-by-ko-tko | ko_fight | 0 | 1 | KO/TKO | None |
| ufc-and28-ate-2026-01-24-win-by-ko-tko | ko_fight | 0 | 1 | KO/TKO | None |
| ufc-der-wal2-2026-01-24-go-the-distance | gtd | 0 | 1 | Decision - Unanimous | None |
| ufc-and28-ate-2026-01-24-go-the-distance | gtd | 1 | 0 | KO/TKO | None |
| ufc-and28-ate-2026-01-24-gautier-win-by-ko-tko | ko_fight | 0 | 1 | KO/TKO | None |
| ufc-ada7-tym-2026-01-24-fugitt-win-by-ko-tko | ko_fight | 0 | 1 | KO/TKO | None |
| ufc-jsiraj-joh41-2026-04-18-yannis-win-by-ko-tko | ko_fighter | 1 | 0 | Decision - Unanimous | John Yannis |
| ufc-ber1-tim15-2026-05-16-cuamba-win-by-ko-tko | ko_fighter | 0 | 1 | KO/TKO | Timmy Cuamba |
| ufc-ber1-tim15-2026-05-16-win-by-ko-tko | ko_fight | 0 | 1 | KO/TKO | None |
| ufc-max1-con-2026-07-11-win-by-ko-tko | ko_fight | 1 | 0 | Decision - Unanimous | None |
| ufc-cod2-ale35-2026-07-11-go-the-distance | gtd | 0 | 1 | Decision - Unanimous | None |
| ufc-cod1-adr-2026-07-11-yanez-win-by-ko-tko | ko_fighter | 1 | 0 | Decision - Majority | Adrian Yanez |
| ufc-kin-ter1-2026-07-11-mckinney-win-by-ko-tko | ko_fighter | 0 | 1 | KO/TKO | Terrance McKinney |
| ufc-bra6-lon-2026-07-11-go-the-distance | gtd | 0 | 1 | Decision - Unanimous | None |
| ufc-rob1-nik2-2026-07-11-whittaker-win-by-ko-tko | ko_fighter | 1 | 0 | KO/TKO | Robert Whittaker |

## 5. Era-Correct Fees & Maker vs Taker

**PM fee schedule** (verified Oct 2026):
- 2025: 0% taker fee
- Mar–Jun 2026: 3% → 0.03 × P × (1−P) per share
- Jul 2026+: 5% → 0.05 × P × (1−P) per share
- **Makers pay zero fee** (plus earn 15% rebate of taker fees collected)

Since the sell-side trade (posting the ask on NO) is a **maker** order,
the executable version of this trade pays **zero fee**. Taker fees only
apply to the counterparty hitting the posted ask.

### GTD (n=130)
  Era breakdown: 0%=11, 3%=113, 5%=6
  Buyer (taker) net: -0.03¢
  Seller (maker) net: +0.02¢ (zero fee)

### KO fight-level (n=96)
  Era breakdown: 0%=33, 3%=58, 5%=5
  Buyer (taker) net: -0.14¢
  Seller (maker) net: +0.13¢ (zero fee)

### KO fighter-specific (n=223)
  Era breakdown: 0%=0, 3%=201, 5%=22
  Buyer (taker) net: -0.31¢
  Seller (maker) net: +0.30¢ (zero fee)

### SUB fight-level (n=85)
  Era breakdown: 0%=11, 3%=70, 5%=4
  Buyer (taker) net: -0.25¢
  Seller (maker) net: +0.24¢ (zero fee)

## 6. BFO Benchmark

**DATA GAP**: `bfo_props_devig.csv` does not exist on disk.
BFO data (`bfo_raw/bfo_odds.csv`) contains moneyline odds only — no method props.
A BFO prop scraper would need to be built to extract method prop odds
(go-the-distance, KO, submission) per fight per book.

Without BFO prop odds, we cannot determine whether PM method prop prices
track book-raw implied or Shin-devigged consensus. This comparison is deferred.

## 7. Capacity

### GTD (n=130)
  Pre-fight volume: mean=1064, median=4 contracts
  Sell-YES P&L/contract: +0.0¢
  $/market (median vol): $0.00
  Annual estimate: $0 (128 fights across ~11 events)

### KO fight-level (n=96)
  Pre-fight volume: mean=254, median=0 contracts
  Sell-YES P&L/contract: +0.1¢
  $/market (median vol): $0.00
  Annual estimate: $0 (73 fights across ~6 events)

### KO fighter-specific (n=223)
  Pre-fight volume: mean=915, median=8 contracts
  Sell-YES P&L/contract: +0.3¢
  $/market (median vol): $0.02
  Annual estimate: $13 (139 fights across ~12 events)

### SUB fight-level (n=85)
  Pre-fight volume: mean=637, median=0 contracts
  Sell-YES P&L/contract: +0.2¢
  $/market (median vol): $0.00
  Annual estimate: $0 (82 fights across ~7 events)

---

## Verdict

**Fighter-KO sell-initiated P&L**: +1.93¢/contract, fight-clustered 95% CI [+0.98¢, +3.17¢] (SIGNIFICANT). Maker (zero fee) net = same. n=223 markets across 139 fights (1.6 markets/fight). 
Resolution disagreements: 9/223. 
**BFO benchmark**: deferred — no prop odds on disk. Cannot determine if PM tracks book-raw or Shin-fair.

Runtime: 47.9s