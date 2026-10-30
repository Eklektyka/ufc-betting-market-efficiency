"""
devig_shin.py
-------------
Applies Shin's (1993) method to devig odds for all fights in the imputed CSV.

Shin's method for binary markets (closed-form):
    Q  = q_a + q_b        (sum of raw implied probs from 1/decimal_odds)
    z  = 2*(Q-1)/Q        (Shin insider-proportion parameter)
    p_i = (q_i - (Q-1)) / (2-Q)   (true probability, sums to 1)

Derivation sketch: from Shin (1993), the bookmaker's quoted prob satisfies
    w_i = (1-z)*p_i + z/2   (for n=2)
Combined with the closed-form z estimate, p_i reduces to the formula above.

For each line type (open, close_lo, close_hi):
  - full match:    use both real odds
  - partial match: use real odds where available, imputed odds otherwise
  - no match:      leave empty

Output: merged/ufc_fights_shin.csv
"""

import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

IN_CSV  = Path("merged/ufc_fights_with_odds_imputed.csv")
OUT_CSV = Path("merged/ufc_fights_shin.csv")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def american_to_prob(american: str) -> float | None:
    """American odds string → raw implied probability (includes vig)."""
    try:
        v = float(american)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    return abs(v) / (abs(v) + 100) if v < 0 else 100 / (v + 100)


def shin_devig(q_a: float, q_b: float) -> tuple[float, float, float]:
    """
    Binary-market Shin devigging.
    Returns (p_a, p_b, z). Falls back to simple normalization if Q ≤ 1.
    """
    Q = q_a + q_b
    if Q <= 1.0:                          # no vig — just normalise
        return q_a / Q, q_b / Q, 0.0
    z  = 2 * (Q - 1) / Q
    denom = 2 - Q
    p_a = (q_a - (Q - 1)) / denom
    p_b = (q_b - (Q - 1)) / denom
    # Sanity: should never happen with real odds, but guard anyway
    if not (0 < p_a < 1 and 0 < p_b < 1):
        p_a, p_b = q_a / Q, q_b / Q      # fallback
        z = 0.0
    return round(p_a, 6), round(p_b, 6), round(z, 6)


def best_odds(real: str, imputed: str) -> float | None:
    """Return parsed real odds; fall back to imputed if real is missing."""
    v = american_to_prob(real)
    if v is not None:
        return v
    return american_to_prob(imputed)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
with IN_CSV.open(encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
    in_fields = list(rows[0].keys())

# ---------------------------------------------------------------------------
# Line-type config: (a_real, a_imp, b_real, b_imp, out_pa, out_pb, out_z)
# ---------------------------------------------------------------------------
LINES = [
    ("odds_open",     "odds_open_imp",     "odds_opp_open",     "odds_opp_open_imp",
     "p_open_a",     "p_open_b",     "shin_z_open"),
    ("odds_close_lo", "odds_close_lo_imp", "odds_opp_close_lo", "odds_opp_close_lo_imp",
     "p_close_lo_a", "p_close_lo_b", "shin_z_close_lo"),
    ("odds_close_hi", "odds_close_hi_imp", "odds_opp_close_hi", "odds_opp_close_hi_imp",
     "p_close_hi_a", "p_close_hi_b", "shin_z_close_hi"),
]

NEW_FIELDS = [f for *_, pa, pb, pz in LINES for f in (pa, pb, pz)]

# ---------------------------------------------------------------------------
# Apply Shin
# ---------------------------------------------------------------------------
stats = {name: {"ok": 0, "skip": 0} for *_, _, _, name in LINES}

for r in rows:
    for a_col, a_imp, b_col, b_imp, out_pa, out_pb, out_z in LINES:
        r[out_pa] = r[out_pb] = r[out_z] = ""

        q_a = best_odds(r.get(a_col, ""), r.get(a_imp, ""))
        q_b = best_odds(r.get(b_col, ""), r.get(b_imp, ""))

        if q_a is None or q_b is None:
            stats[out_z]["skip"] += 1
            continue

        p_a, p_b, z = shin_devig(q_a, q_b)
        r[out_pa] = p_a
        r[out_pb] = p_b
        r[out_z]  = z
        stats[out_z]["ok"] += 1

# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
out_fields = in_fields + NEW_FIELDS
with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=out_fields)
    w.writeheader()
    w.writerows(rows)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total = len(rows)
print(f"Total fights: {total}")
print()
print(f"{'Line':<14} {'Devigged':>10} {'Skipped':>10}")
print("-" * 36)
for *_, _, _, out_z in LINES:
    label = out_z.replace("shin_z_", "")
    ok, skip = stats[out_z]["ok"], stats[out_z]["skip"]
    print(f"{label:<14} {ok:>10} ({ok/total*100:.1f}%)  {skip:>6} ({skip/total*100:.1f}%)")

print(f"\nOutput: {OUT_CSV}")

# ---------------------------------------------------------------------------
# Spot-check: 10 random fully-matched fights — verify p_a + p_b ≈ 1
#             and Shin z matches expected vig
# ---------------------------------------------------------------------------
import random
random.seed(42)

full = [r for r in rows if r["odds_matched"] == "full"
        and r.get("p_close_lo_a") and r.get("p_close_lo_b")]
sample = random.sample(full, 10)

print("\n=== Spot-check: 10 random fights (close_lo line) ===")
print(f"{'Fighter A':<22} {'A_lo':>7} {'B_lo':>7} | "
      f"{'Q':>6} {'vig':>7} | "
      f"{'p_a':>7} {'p_b':>7} {'sum':>7} {'z':>7}")
print("-" * 88)

for r in sample:
    a_lo = r["odds_close_lo"]
    b_lo = r["odds_opp_close_lo"]
    q_a  = american_to_prob(a_lo)
    q_b  = american_to_prob(b_lo)
    Q    = q_a + q_b
    vig  = Q - 1
    p_a  = float(r["p_close_lo_a"])
    p_b  = float(r["p_close_lo_b"])
    z    = float(r["shin_z_close_lo"])
    name = r["fighter_a"][:21]
    print(f"{name:<22} {a_lo:>7} {b_lo:>7} | "
          f"{Q:>6.4f} {vig*100:>6.2f}pp | "
          f"{p_a:>7.4f} {p_b:>7.4f} {p_a+p_b:>7.4f} {z:>7.4f}")
