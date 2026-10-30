# Phase A — Per-Round UFCStats Scrape Report

Generated: 2026-10-11 (updating as scrape progresses)
Status: **IN PROGRESS**

## Step A0 — Pilot + Self-Validation

### Pilot selection (40 fights)
- 10 recent (2025–26)
- 10 old (2007–2010)
- 5 one-round finishes
- 5 five-round fights
- 5 women's fights
- 5 DQ/NC/Draw results

### Pilot results
- All 40 fights scraped successfully (ok=40, err=0)
- Runtime: 176s (live fetch), 81s (from cache re-parse)

### Validation results
- **Field-by-field sums**: 0 mismatches across all 10 fields (kd, sig_landed, sig_attempted, total_landed, total_attempted, td_landed, td_attempted, sub_attempts, reversals, control_time_sec)
- **Round count**: 0 mismatches (parsed n_rounds == fights.csv round field)
- **Duplicate check**: 0 duplicate (fight_id, fighter_idx, round) tuples
- **No-round-table fights**: 0 in pilot (old fights 2007–2010 all had tables)
- **Control time parsing**: "M:SS" → seconds correctly; "--" → empty string

**ALL 40 PILOT FIGHTS PASS VALIDATION**

### Parser fix log
No fixes needed — parser passed on first attempt.

## Step A1 — Full Run

### Configuration
- Input: 8,758 unique fights from fights.csv
- Rate: 1 req/s + Playwright overhead (~3.5s/page effective)
- HTML cache: ufcstats_raw/raw_html_rounds/{fight_id}.html
- Checkpoint: rounds_scrape_log.csv (resumable on kill)
- 40 fights pre-cached from pilot

### Progress — COMPLETE

| Metric | Value |
|--------|-------|
| Fights processed | 8,758 / 8,758 |
| Status: ok | 8,737 (99.76%) |
| Status: no_round_tables | 21 (all pre-2000 era) |
| Status: parse_error | 0 |
| Status: http_error | 0 |
| Round rows written (totals) | 41,186 |
| Sigstrike rows written | 41,186 |
| Effective rate | ~2.6s/page |
| Total runtime | ~7.5 hours (two runs, resumed from checkpoint) |

### Full validation (all 8,737 fights with round data)
- **Field-by-field sums vs fight totals**: 0 mismatches across 8,737 fights
- **Duplicate rows**: 0
- **no_round_tables**: 21 fights (all pre-2000 UFC events without stats)

## Verdict Line A

**8,758 fights scraped / 41,186 round-rows written / 0 fights failing
the totals check / 21 fights with no round tables** (all pre-2000).
Parser validated on pilot (40/40) and full run (8,737/8,737) with zero
field mismatches.

## Gate A→B

Threshold: ≥95% of fights from 2015 onward have status=ok.
**PASSED**: 5,710/5,710 post-2015 fights ok (100.0%).
