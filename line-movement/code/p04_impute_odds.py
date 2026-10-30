"""
impute_odds.py
--------------
1. Computes empirical vig distribution from fully-matched fights (both sides known).
2. Uses per-line-type median vig to impute missing odds for partial matches.
3. Adds imputed columns to merged CSV, flagged with odds_imputed = True/False.
4. Validates on 10 random fully-matched fights.
"""

import csv
import random
import sys
from pathlib import Path
from statistics import median, mean, stdev

sys.stdout.reconfigure(encoding="utf-8")

IN_CSV  = Path("merged/ufc_fights_with_odds.csv")
OUT_CSV = Path("merged/ufc_fights_with_odds_imputed.csv")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def to_prob(american: str) -> float | None:
    """American odds string → raw implied probability (includes vig)."""
    try:
        v = float(american)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    if v < 0:
        return abs(v) / (abs(v) + 100)
    else:
        return 100 / (v + 100)


def prob_to_american(p: float) -> float:
    """True/devigged probability → American odds (no vig)."""
    if p <= 0 or p >= 1:
        return None
    if p >= 0.5:
        return round(-(p / (1 - p)) * 100, 1)
    else:
        return round(((1 - p) / p) * 100, 1)


def impute_american(known_american: str, vig: float) -> float | None:
    """
    Given one side's American odds and the total overround (vig as decimal,
    e.g. 0.038), return the implied American odds for the other side.
    """
    p_known = to_prob(known_american)
    if p_known is None:
        return None
    p_other = (1 + vig) - p_known
    if p_other <= 0 or p_other >= 1:
        return None
    return prob_to_american(p_other / (1 + vig))   # devig before converting


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
with IN_CSV.open(encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys())

full    = [r for r in rows if r["odds_matched"] == "full"]
partial = [r for r in rows if r["odds_matched"] == "partial"]
none_   = [r for r in rows if r["odds_matched"] == "none"]

print(f"Full matches:    {len(full)}")
print(f"Partial matches: {len(partial)}")
print(f"No matches:      {len(none_)}")

# ---------------------------------------------------------------------------
# Step 1: Compute empirical vig distribution from fully-matched fights
# ---------------------------------------------------------------------------
LINE_PAIRS = [
    ("odds_open",     "odds_opp_open"),
    ("odds_close_lo", "odds_opp_close_lo"),
    ("odds_close_hi", "odds_opp_close_hi"),
]

vigs = {pair: [] for pair in LINE_PAIRS}

for r in full:
    for a_col, b_col in LINE_PAIRS:
        pa = to_prob(r[a_col])
        pb = to_prob(r[b_col])
        if pa is not None and pb is not None:
            v = pa + pb - 1
            if -0.05 < v < 0.20:   # sanity bounds
                vigs[(a_col, b_col)].append(v)

print("\n=== Empirical vig distribution (from fully-matched fights) ===")
vig_medians = {}
for (a_col, b_col), vals in vigs.items():
    label = a_col.replace("odds_", "")
    vig_medians[(a_col, b_col)] = median(vals)
    print(f"  {label:12s}: n={len(vals):5d}  "
          f"mean={mean(vals)*100:5.2f}pp  "
          f"median={median(vals)*100:5.2f}pp  "
          f"std={stdev(vals)*100:4.2f}pp")

# ---------------------------------------------------------------------------
# Step 2: Impute missing odds for partial matches
# ---------------------------------------------------------------------------
NEW_FIELDS = [
    "odds_open_imp", "odds_close_lo_imp", "odds_close_hi_imp",
    "odds_opp_open_imp", "odds_opp_close_lo_imp", "odds_opp_close_hi_imp",
    "odds_imputed",
]

IMPUTE_MAP = [
    # (missing col,        known col,          vig key)
    ("odds_open",         "odds_opp_open",         ("odds_open",     "odds_opp_open")),
    ("odds_close_lo",     "odds_opp_close_lo",     ("odds_close_lo", "odds_opp_close_lo")),
    ("odds_close_hi",     "odds_opp_close_hi",     ("odds_close_hi", "odds_opp_close_hi")),
    ("odds_opp_open",     "odds_open",             ("odds_open",     "odds_opp_open")),
    ("odds_opp_close_lo", "odds_close_lo",         ("odds_close_lo", "odds_opp_close_lo")),
    ("odds_opp_close_hi", "odds_close_hi",         ("odds_close_hi", "odds_opp_close_hi")),
]

IMP_COLS = {
    "odds_open":         "odds_open_imp",
    "odds_close_lo":     "odds_close_lo_imp",
    "odds_close_hi":     "odds_close_hi_imp",
    "odds_opp_open":     "odds_opp_open_imp",
    "odds_opp_close_lo": "odds_opp_close_lo_imp",
    "odds_opp_close_hi": "odds_opp_close_hi_imp",
}

imputed_count = 0
for r in rows:
    for col in NEW_FIELDS:
        r[col] = ""
    r["odds_imputed"] = "False"

    if r["odds_matched"] != "partial":
        continue

    did_impute = False
    for missing_col, known_col, vig_key in IMPUTE_MAP:
        if r.get(missing_col):        # already has a value
            continue
        known_val = r.get(known_col)
        if not known_val:             # known side also empty
            continue
        vig = vig_medians[vig_key]
        imp = impute_american(known_val, vig)
        if imp is not None:
            r[IMP_COLS[missing_col]] = imp
            did_impute = True

    if did_impute:
        r["odds_imputed"] = "True"
        imputed_count += 1

print(f"\nPartial matches successfully imputed: {imputed_count}/{len(partial)}")

# ---------------------------------------------------------------------------
# Step 3: Write output
# ---------------------------------------------------------------------------
out_fields = fieldnames + NEW_FIELDS
with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=out_fields)
    w.writeheader()
    w.writerows(rows)

print(f"Written: {OUT_CSV}")

# ---------------------------------------------------------------------------
# Step 4: Validation — 10 random fully-matched fights
# ---------------------------------------------------------------------------
print("\n=== Validation: 10 random fully-matched fights ===")
print("Check: imputed opp_close_lo from known close_lo vs actual opp_close_lo\n")

random.seed(7)
sample = random.sample(full, 10)

header = f"{'Fighter A':<22} {'Fighter B':<22} {'A_lo':>7} {'B_lo_actual':>12} {'B_lo_imputed':>13} {'vig_actual':>10} {'vig_imputed':>11}"
print(header)
print("-" * len(header))

vig_key = ("odds_close_lo", "odds_opp_close_lo")
vig_med = vig_medians[vig_key]

for r in sample:
    a_lo = r["odds_close_lo"]
    b_lo_actual = r["odds_opp_close_lo"]
    b_lo_imp = impute_american(a_lo, vig_med)

    pa = to_prob(a_lo)
    pb_actual = to_prob(b_lo_actual)
    pb_imp = to_prob(str(b_lo_imp)) if b_lo_imp else None

    vig_actual  = f"{(pa + pb_actual - 1)*100:+.2f}pp"  if pa and pb_actual else "N/A"
    vig_imputed = f"{(pa + pb_imp    - 1)*100:+.2f}pp"  if pa and pb_imp    else "N/A"

    a_name = r["fighter_a"][:21]
    b_name = r["fighter_b"][:21]
    print(f"{a_name:<22} {b_name:<22} {a_lo:>7} {b_lo_actual:>12} {str(b_lo_imp):>13} {vig_actual:>10} {vig_imputed:>11}")
